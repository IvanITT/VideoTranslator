"""Speech recognition adapter (faster-whisper / CTranslate2).

Models are loaded lazily, cached between jobs and can be unloaded explicitly.
"""
from __future__ import annotations

import gc
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from app.core.errors import AppError, CancelledError, MediaError, ModelMissingError
from app.services import ffmpeg

CancelCheck = Callable[[], bool]
ProgressCb = Callable[[float, str], None]

_cache: dict[tuple, object] = {}
_lock = threading.Lock()


class ASRError(AppError):
    code = "asr_error"
    status_code = 500


@dataclass
class ASRResult:
    segments: list[dict]
    language: str
    language_probability: float
    duration: float
    elapsed_s: float


def _model_key(model_dir: str, device: str, compute_type: str, threads: int) -> tuple:
    return (str(Path(model_dir).resolve()), device, compute_type, threads)


def load_model(model_dir: str, *, device: str = "cpu", compute_type: str = "int8",
               threads: int = 2):
    from faster_whisper import WhisperModel

    key = _model_key(model_dir, device, compute_type, threads)
    with _lock:
        model = _cache.get(key)
        if model is None:
            if not Path(model_dir).exists():
                raise ModelMissingError(
                    "El modelo de reconocimiento de voz no está instalado.",
                    "Abre «Modelos» y descarga Whisper Base o Tiny.",
                )
            try:
                model = WhisperModel(
                    str(model_dir),
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=max(1, threads),
                    num_workers=1,
                    local_files_only=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise ASRError(
                    "No se pudo cargar el modelo de reconocimiento de voz.",
                    f"Comprueba que los archivos estén completos y que haya RAM libre. Detalle: {exc}",
                ) from exc
            _cache[key] = model
        return model


def unload_all() -> None:
    with _lock:
        _cache.clear()
    gc.collect()


def available_languages() -> dict[str, str]:
    return {
        "en": "Inglés", "es": "Español", "fr": "Francés", "de": "Alemán",
        "pt": "Portugués", "it": "Italiano", "ja": "Japonés", "ko": "Coreano",
        "zh": "Chino", "ru": "Ruso", "ar": "Árabe", "hi": "Hindi",
        "nl": "Neerlandés", "pl": "Polaco", "tr": "Turco", "sv": "Sueco",
        "uk": "Ucraniano", "id": "Indonesio",
    }


def transcribe(audio_path: str, *, model_dir: str, model_name: str = "base",
               language: str | None = None, threads: int = 2, device: str = "cpu",
               compute_type: str = "int8", beam_size: int = 5,
               word_timestamps: bool = False, vad: bool = True,
               duration: float | None = None, cancel_check: CancelCheck | None = None,
               progress: ProgressCb | None = None) -> ASRResult:
    started = time.monotonic()
    model = load_model(model_dir, device=device, compute_type=compute_type, threads=threads)
    audio_duration = duration or ffmpeg.wav_duration(audio_path)

    try:
        segment_iter, info = model.transcribe(
            audio_path,
            language=language or None,
            beam_size=max(1, beam_size),
            vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 500} if vad else None,
            word_timestamps=word_timestamps,
            condition_on_previous_text=False,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        raise ASRError(
            "Falló el reconocimiento de voz.",
            f"Prueba con otro modelo o revisa el audio extraído. Detalle: {exc}",
        ) from exc

    raw: list[dict] = []
    try:
        for seg in segment_iter:
            if cancel_check and cancel_check():
                raise CancelledError("Trabajo cancelado durante el reconocimiento de voz.")
            text = (seg.text or "").strip()
            if text:
                raw.append({
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "text": text,
                })
            if progress and audio_duration:
                progress(min(0.99, max(0.0, float(seg.end) / audio_duration)),
                         "Transcribiendo audio")
    except CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ASRError(
            "El reconocimiento de voz se interrumpió.",
            f"El audio puede estar dañado o el modelo no pudo procesarlo. Detalle: {exc}",
        ) from exc

    if not raw:
        raise MediaError(
            "No se detectó voz en el audio del video.",
            "Comprueba que el video tenga diálogo audible. Si la voz es muy tenue, "
            "prueba a subir el volumen del archivo original.",
        )

    segments = merge_and_split(raw, audio_duration)
    elapsed = round(time.monotonic() - started, 1)
    if progress:
        progress(1.0, "Transcripción lista")
    return ASRResult(
        segments=segments,
        language=info.language or (language or "en"),
        language_probability=round(float(getattr(info, "language_probability", 1.0)), 3),
        duration=audio_duration,
        elapsed_s=elapsed,
    )


def merge_and_split(raw: Iterable[dict], total_duration: float,
                    min_gap: float = 0.02, max_len: float = 14.0) -> list[dict]:
    """Normalize Whisper output: sort, clamp, split long lines.

    Whisper emits contiguous segments; merging them would destroy the timing
    metadata used for dubbing, so only literal duplicates/overlaps are merged.
    """
    items = sorted((s for s in raw if s.get("text")), key=lambda s: s["start"])
    merged: list[dict] = []
    for seg in items:
        start = max(0.0, float(seg["start"]))
        end = min(max(start + 0.2, float(seg["end"])), total_duration or start + 0.2)
        if merged and start < merged[-1]["end"] - 0.05:
            # Overlapping segments: keep the later start, extend the earlier end.
            merged[-1]["end"] = max(merged[-1]["end"], end)
            if seg["text"].strip() and seg["text"].strip() not in merged[-1]["text"]:
                merged[-1]["text"] = f"{merged[-1]['text'].rstrip()} {seg['text'].lstrip()}".strip()
        else:
            merged.append({"start": round(start, 3), "end": round(end, 3),
                           "text": str(seg["text"]).strip()})

    result: list[dict] = []
    for seg in merged:
        dur = seg["end"] - seg["start"]
        text = seg["text"]
        words = text.split()
        if dur > max_len and len(words) > 12:
            parts = max(2, round(dur / max_len))
            per = len(words) / parts
            span = dur / parts
            for i in range(parts):
                chunk = words[round(i * per):round((i + 1) * per)]
                if not chunk:
                    continue
                result.append({
                    "start": round(seg["start"] + i * span, 3),
                    "end": round(seg["start"] + (i + 1) * span, 3),
                    "text": " ".join(chunk),
                })
        else:
            result.append(seg)
    return result
