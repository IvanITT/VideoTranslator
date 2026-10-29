"""FFmpeg / FFprobe wrappers.

Every subprocess call uses an argument list (never a shell), runs with
``-nostdin`` and can be cancelled cooperatively. Media paths are resolved by
the caller and validated before reaching this module.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from app.core.config import SUBPROCESS_FLAGS, config
from app.core.errors import CancelledError, MediaError

CancelCheck = Callable[[], bool] | None
ProgressCb = Callable[[float, str], None] | None


class FFmpegError(MediaError):
    code = "ffmpeg_error"


def ffmpeg_path() -> str:
    if not config.ffmpeg or not Path(config.ffmpeg).exists():
        raise FFmpegError(
            "No se encontró FFmpeg.",
            "Ejecuta scripts/setup.ps1 o define VTS_FFMPEG con la ruta completa a ffmpeg.exe.",
        )
    return config.ffmpeg


def ffprobe_path() -> str:
    if not config.ffprobe or not Path(config.ffprobe).exists():
        raise FFmpegError(
            "No se encontró FFprobe.",
            "Ejecuta scripts/setup.ps1 o define VTS_FFPROBE con la ruta completa a ffprobe.exe.",
        )
    return config.ffprobe


def _tail(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    return text[-limit:]


def run_command(cmd: list[str], *, timeout: float | None = None,
                cancel_check: CancelCheck = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a process and abort it if ``cancel_check`` becomes true."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        creationflags=SUBPROCESS_FLAGS,
    )
    started = time.monotonic()
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=0.25)
            break
        except subprocess.TimeoutExpired:
            if cancel_check and cancel_check():
                proc.kill()
                proc.communicate()
                raise CancelledError("Trabajo cancelado por el usuario.")
            if timeout and time.monotonic() - started > timeout:
                proc.kill()
                proc.communicate()
                raise FFmpegError(
                    "La operación de FFmpeg excedió el tiempo máximo.",
                    "Prueba con un video más corto o revisa el archivo de entrada.",
                )
    if proc.returncode != 0:
        raise FFmpegError(
            f"FFmpeg falló (código {proc.returncode}).",
            "Revisa el registro de la etapa. El archivo puede estar dañado o usar un "
            "códec no soportado. Detalle: " + _tail(stderr or ""),
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def probe(path: str | Path) -> dict:
    """Return normalized metadata for a media file."""
    path = str(path)
    if not Path(path).exists():
        raise MediaError("El archivo de video no existe.",
                         "Vuelve a subir el archivo.")
    cmd = [
        ffprobe_path(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    try:
        result = run_command(cmd, timeout=120)
    except FFmpegError as exc:
        raise MediaError(
            "No se pudo leer el archivo multimedia. Puede estar dañado o no ser un video válido.",
            "Prueba con otro MP4 (H.264/AAC) o revisa el archivo con un reproductor.",
        ) from exc
    try:
        data = json.loads(result.stdout or "{}")
    except ValueError as exc:
        raise MediaError("FFprobe devolvió información inválida.",
                         "Verifica que el archivo sea un video válido.") from exc

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = 0.0
    for candidate in (fmt.get("duration"), (video or {}).get("duration"), (audio or {}).get("duration")):
        try:
            duration = float(candidate)
            if duration > 0:
                break
        except (TypeError, ValueError):
            continue

    fps = None
    if video:
        raw = video.get("avg_frame_rate") or video.get("r_frame_rate") or ""
        if raw and raw not in ("0/0", "N/A"):
            try:
                num, den = raw.split("/")
                fps = round(float(num) / float(den), 3) if float(den) else None
            except (ValueError, ZeroDivisionError):
                fps = None

    rotation = 0
    for side in video.get("side_data_list", []) if video else []:
        if "rotation" in side:
            try:
                rotation = int(float(side["rotation"]))
            except (TypeError, ValueError):
                pass

    if not video:
        raise MediaError(
            "El archivo no contiene una pista de video.",
            "Sube un archivo MP4 con video (H.264 recomendado).",
        )
    if duration <= 0:
        raise MediaError(
            "No se pudo determinar la duración del video.",
            "El archivo puede estar incompleto o dañado. Intenta con otra copia.",
        )

    return {
        "duration": round(duration, 3),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": fps,
        "video_codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "audio_codec": (audio or {}).get("codec_name"),
        "audio_channels": int((audio or {}).get("channels") or 0),
        "audio_sample_rate": int((audio or {}).get("sample_rate") or 0),
        "has_audio": audio is not None,
        "format": fmt.get("format_name"),
        "bit_rate": int(fmt.get("bit_rate") or 0),
        "rotation": rotation,
        "size_bytes": int(fmt.get("size") or 0),
    }


def _run_with_progress(cmd: list[str], *, duration: float | None,
                       progress_cb: ProgressCb, cancel_check: CancelCheck,
                       label: str = "Procesando") -> None:
    """Run FFmpeg with ``-progress pipe:1`` and translate it into 0..1."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=SUBPROCESS_FLAGS,
    )
    lines: queue.Queue[str | None] = queue.Queue()
    err_lines: list[str] = []

    def read_stdout() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    def read_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            err_lines.append(line)
            if len(err_lines) > 200:
                del err_lines[:100]

    t_out = threading.Thread(target=read_stdout, daemon=True)
    t_err = threading.Thread(target=read_stderr, daemon=True)
    t_out.start()
    t_err.start()

    started = time.monotonic()
    last_update = 0.0
    while True:
        if cancel_check and cancel_check():
            proc.kill()
            proc.wait()
            raise CancelledError("Trabajo cancelado por el usuario.")
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            if proc.poll() is not None and not t_out.is_alive():
                break
            continue
        if line is None:
            break
        match = re.match(r"out_time_(?:us|ms)=(\d+)", line.strip())
        if match and duration and progress_cb:
            now = time.monotonic()
            if now - last_update > 0.4:
                seconds = int(match.group(1)) / (1_000_000 if "us" in line else 1000)
                progress_cb(min(0.99, max(0.0, seconds / duration)), label)
                last_update = now

    proc.wait()
    t_err.join(timeout=2)
    if proc.returncode != 0:
        raise FFmpegError(
            f"FFmpeg falló durante {label.lower()} (código {proc.returncode}).",
            "Detalle técnico: " + _tail("".join(err_lines)),
        )
    if progress_cb:
        progress_cb(1.0, label)


def extract_audio(video: str, output: str, *, sample_rate: int = 16000,
                  channels: int = 1, duration: float | None = None,
                  progress_cb: ProgressCb = None, cancel_check: CancelCheck = None) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_path(), "-nostdin", "-y", "-v", "error",
        "-i", video, "-vn", "-sn", "-dn",
        "-ac", str(channels), "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", "-progress", "pipe:1", "-nostats", output,
    ]
    _run_with_progress(cmd, duration=duration, progress_cb=progress_cb,
                       cancel_check=cancel_check, label="Extrayendo audio")


def normalize_audio(source: str, output: str, *, sample_rate: int = 48000,
                    channels: int = 2, duration: float | None = None,
                    cancel_check: CancelCheck = None) -> None:
    cmd = [
        ffmpeg_path(), "-nostdin", "-y", "-v", "error", "-i", source,
        "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le", output,
    ]
    run_command(cmd, cancel_check=cancel_check, timeout=1800 if cancel_check else None)


def make_thumbnail(video: str, output: str, at_seconds: float = 1.0) -> bool:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_path(), "-nostdin", "-y", "-v", "error", "-ss", f"{max(0, at_seconds):.2f}",
        "-i", video, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", output,
    ]
    try:
        run_command(cmd, timeout=60)
        return Path(output).exists()
    except (FFmpegError, OSError):
        return False


def wav_duration(path: str | Path) -> float:
    try:
        import soundfile as sf

        info = sf.info(str(path))
        return round(float(info.frames) / float(info.samplerate), 3)
    except Exception:
        pass
    try:
        return float(probe_audio_duration(str(path)))
    except Exception:
        return 0.0


def probe_audio_duration(path: str) -> float:
    cmd = [ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
           "-of", "default=nw=1:nk=1", path]
    result = run_command(cmd, timeout=60)
    try:
        return float((result.stdout or "0").strip() or 0)
    except ValueError:
        return 0.0


def concat_wavs(parts: list[str], output: str, *, list_file: str | None = None,
                cancel_check: CancelCheck = None) -> None:
    """Concatenate WAV parts with identical format using the concat demuxer."""
    if not parts:
        raise MediaError("No hay fragmentos de audio para unir.",
                         "Vuelve a ejecutar la generación de voz.")
    list_path = list_file or str(Path(output).with_suffix(".txt"))
    with open(list_path, "w", encoding="utf-8") as handle:
        for part in parts:
            escaped = str(Path(part).resolve()).replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    cmd = [
        ffmpeg_path(), "-nostdin", "-y", "-v", "error", "-f", "concat",
        "-safe", "0", "-i", list_path, "-c:a", "pcm_s16le", output,
    ]
    run_command(cmd, cancel_check=cancel_check)
    try:
        os.remove(list_path)
    except OSError:
        pass


def silence(duration: float, output: str, *, sample_rate: int = 48000,
            channels: int = 2) -> None:
    cmd = [
        ffmpeg_path(), "-nostdin", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl={'stereo' if channels == 2 else 'mono'}",
        "-t", f"{max(0.01, duration):.3f}", "-c:a", "pcm_s16le", output,
    ]
    run_command(cmd, timeout=120)


def copy_file(source: str | Path, destination: str | Path) -> None:
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def available_disk_gb(path: str | Path) -> float:
    try:
        return round(shutil.disk_usage(str(path)).free / (1024 ** 3), 1)
    except OSError:
        return 0.0
