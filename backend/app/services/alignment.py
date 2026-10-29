"""Dialogue timing: speed limits, gaps, overlap detection and dub assembly.

The dub track is written sequentially to disk (never a full-length array in
RAM), preserving the video duration.
"""
from __future__ import annotations

import math
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from app.core.errors import CancelledError, MediaError
from app.services import ffmpeg
from app.services.translation import shorten_for_fit

CancelCheck = Callable[[], bool] | None
ProgressCb = Callable[[float, str], None] | None

SAMPLE_RATE = 48000


class AlignmentError(MediaError):
    code = "alignment_error"


@dataclass
class Placement:
    index: int
    original_start: float
    original_end: float
    start: float
    end: float
    speech_duration: float
    speed: float
    text: str
    warning: str | None = None


@dataclass
class DubResult:
    path: str
    duration: float
    placements: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    max_speed: float = 1.0
    overlong: int = 0
    trimmed: int = 0


def plan_timeline(segments: list[dict], total_duration: float, *, gap_ms: int = 80,
                  max_speedup: float = 1.18) -> tuple[list[Placement], list[str]]:
    """Compute non-overlapping placements inside the original video duration.

    ``segments`` items need ``start``, ``end``, ``speech_duration`` (measured
    after synthesis) and optionally ``text``/``index``.
    """
    gap = max(0.0, gap_ms / 1000.0)
    cursor = 0.0
    placements: list[Placement] = []
    warnings: list[str] = []
    ordered = sorted(segments, key=lambda s: float(s.get("start", 0)))

    for i, seg in enumerate(ordered):
        start = max(float(seg.get("start", 0)), cursor, 0.0)
        if start >= total_duration:
            start = max(0.0, total_duration - 0.25)
        speech = float(seg.get("speech_duration") or 0.0)
        if speech <= 0:
            continue
        next_start = None
        for candidate in ordered[i + 1:]:
            next_start = float(candidate.get("start", total_duration))
            if next_start > start:
                break
        window_end = total_duration if next_start is None else min(
            total_duration, max(start + 0.3, next_start - gap)
        )
        available = max(0.2, window_end - start)
        speed = 1.0
        warning = None
        if speech > available:
            speed = min(max_speedup, speech / available)
            if speech / speed > available + 0.02:
                warning = (
                    f"El doblaje dura {speech:.1f}s y solo caben {available:.1f}s; "
                    "se acelera al límite seguro. Edita el texto para acortarlo."
                )
        final_duration = speech / speed
        end = start + final_duration

        # Never exceed the video: apply extra (documented) compression for the tail.
        if end > total_duration:
            overflow = end - total_duration
            speed = speech / max(0.2, total_duration - start)
            final_duration = speech / speed
            end = total_duration
            warning = (warning + " " if warning else "") + (
                f"El último segmento se recortó {overflow:.1f}s para conservar la duración del video."
            )
        if speed > 1.001:
            if speed >= max_speedup * 0.995:
                warning = (
                    (warning + " " if warning else "")
                    + f"Se alcanzó el límite de velocidad x{speed:.2f}. Revisa el texto si "
                      "suena acelerado."
                )
        placements.append(Placement(
            index=int(seg.get("index", i)),
            original_start=round(float(seg.get("start", 0)), 3),
            original_end=round(float(seg.get("end", 0)), 3),
            start=round(start, 3), end=round(end, 3),
            speech_duration=round(speech, 3), speed=round(speed, 3),
            text=seg.get("text", ""), warning=warning,
        ))
        if warning:
            warnings.append(f"Segmento {i + 1}: {warning}")
        cursor = end + gap
    return placements, warnings


def build_dub(segments: list[dict], output: str, *, total_duration: float,
              gap_ms: int = 80, max_speedup: float = 1.18,
              cancel_check: CancelCheck = None, progress: ProgressCb = None,
              shorten: bool = False) -> DubResult:
    """Assemble the Spanish dub WAV (48 kHz stereo) from per-segment audio."""
    if not segments:
        raise AlignmentError("No hay segmentos de voz para sincronizar.",
                             "Revisa la traducción antes de continuar.")
    prepared: dict[int, dict] = {}
    for i, seg in enumerate(segments):
        path = seg.get("tts_path")
        speech_duration = float(seg.get("tts_duration") or 0)
        if path and Path(path).exists():
            if not speech_duration:
                speech_duration = ffmpeg.wav_duration(path)
            index = int(seg["idx"]) if "idx" in seg else int(seg.get("index", i))
            prepared[index] = {
                "index": index, "start": seg.get("start", 0), "end": seg.get("end", 0),
                "speech_duration": speech_duration,
                "text": seg.get("text_es") or seg.get("text", ""),
                "tts_path": path,
            }
    if not prepared:
        raise AlignmentError("Ningún segmento tiene audio generado.",
                             "Vuelve a ejecutar la etapa de generación de voz.")

    placements, warnings = plan_timeline(list(prepared.values()), total_duration,
                                         gap_ms=gap_ms, max_speedup=max_speedup)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="dub_", dir=str(out_path.parent))
    written = 0.0
    overlong = 0
    trimmed = 0
    max_speed = 1.0

    try:
        with sf.SoundFile(str(out_path), mode="w", samplerate=SAMPLE_RATE,
                          channels=2, subtype="PCM_16") as out:
            for i, place in enumerate(placements):
                if cancel_check and cancel_check():
                    raise CancelledError("Trabajo cancelado durante la sincronización.")
                source = Path(prepared[place.index]["tts_path"])
                gap_samples = max(0, int(round((place.start - written) * SAMPLE_RATE)))
                if gap_samples:
                    out.write(np.zeros((gap_samples, 2), dtype="float32"))
                    written += gap_samples / SAMPLE_RATE

                audio_path = str(source)
                if place.speed > 1.001:
                    adjusted = str(Path(tmpdir) / f"seg_{i:05d}.wav")
                    atempo = place.speed
                    filters = []
                    while atempo > 2.0:
                        filters.append("atempo=2.0")
                        atempo /= 2.0
                    filters.append(f"atempo={atempo:.5f}")
                    ffmpeg.run_command([
                        ffmpeg.ffmpeg_path(), "-nostdin", "-y", "-v", "error",
                        "-i", str(source), "-af", ",".join(filters),
                        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", adjusted,
                    ], cancel_check=cancel_check, timeout=300)
                    audio_path = adjusted

                data, rate = sf.read(audio_path, dtype="float32", always_2d=True)
                if rate != SAMPLE_RATE:
                    raise AlignmentError("Frecuencia de muestreo inesperada en el audio generado.",
                                         "Vuelve a generar la voz del segmento.")
                if data.shape[1] == 1:
                    data = np.repeat(data, 2, axis=1)
                elif data.shape[1] > 2:
                    data = data[:, :2]
                frame_limit = int(round(place.end * SAMPLE_RATE)) - int(round(written * SAMPLE_RATE))
                if frame_limit <= 0:
                    continue
                if len(data) > frame_limit:
                    data = data[:frame_limit]
                    trimmed += 1
                    if not place.warning:
                        place.warning = "Se recortaron milisegundos finales para no invadir el siguiente segmento."
                        warnings.append(f"Segmento {place.index + 1}: {place.warning}")
                out.write(data)
                written += len(data) / SAMPLE_RATE
                if place.warning:
                    overlong += 1
                max_speed = max(max_speed, place.speed)
                if progress:
                    progress(min(0.99, (i + 1) / len(placements)), "Sincronizando segmentos")

            remaining = int(round(total_duration * SAMPLE_RATE)) - int(round(written * SAMPLE_RATE))
            if remaining > 0:
                out.write(np.zeros((remaining, 2), dtype="float32"))
    finally:
        for child in Path(tmpdir).glob("*"):
            try:
                child.unlink()
            except OSError:
                pass
        try:
            Path(tmpdir).rmdir()
        except OSError:
            pass

    duration = ffmpeg.wav_duration(out_path)
    if progress:
        progress(1.0, "Audio sincronizado")
    return DubResult(
        path=str(out_path),
        duration=duration,
        placements=[asdict(p) for p in placements],
        warnings=warnings,
        max_speed=round(max_speed, 3),
        overlong=overlong,
        trimmed=trimmed,
    )


def estimate_duration(text: str, chars_per_second: float = 14.5) -> float:
    """Rough Spanish speech duration estimate (used for planning UI only)."""
    words = max(1, len(text.split()))
    return max(0.6, words / 2.6, len(text) / chars_per_second / 1.0)


def fit_text_to_window(text: str, window: float, max_speedup: float = 1.18) -> tuple[str, bool]:
    """Trim fillers when a line cannot fit even at the maximum speaking rate."""
    estimate = estimate_duration(text)
    if window <= 0 or estimate / max_speedup <= window:
        return text, False
    target_chars = max(12, int(len(text) * window / max(estimate / max_speedup, 0.1)))
    trimmed = shorten_for_fit(text, target_chars)
    return trimmed, trimmed != text


def clamp_gap(gap_ms: int) -> int:
    try:
        value = int(gap_ms)
    except (TypeError, ValueError):
        return 80
    return int(max(0, min(1000, value)))


def seconds_to_srt(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - math.floor(seconds)) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
