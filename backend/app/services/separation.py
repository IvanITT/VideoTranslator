"""Optional dialogue/background separation.

Two real, local methods are supported:

* ``demucs`` (optional, only if installed) - neural source separation.
* ``center_cancel`` - dependency-free stereo center-channel cancellation,
  a rough fallback for music/effects. It is NOT a vocal isolator and can
  remove or mangle audio; the UI warns about artifacts.

When neither is usable the pipeline keeps the original track and ducks it
under the Spanish dub (no separation).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from app.core.config import SUBPROCESS_FLAGS, config
from app.core.errors import CancelledError, MediaError
from app.services import ffmpeg

CancelCheck = Callable[[], bool] | None
ProgressCb = Callable[[float, str], None] | None


class SeparationError(MediaError):
    code = "separation_error"


def demucs_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("demucs") is not None
    except (ImportError, ValueError):
        return False


def capability() -> dict:
    return {
        "demucs": demucs_available(),
        "center_cancel": True,
        "recommended": "demucs" if demucs_available() else "center_cancel",
        "note": (
            "Demucs ofrece la mejor separación pero requiere GPU o varios minutos por "
            "minuto de audio en CPU. La cancelación de canal central es instantánea "
            "pero solo atenúa sonidos centrados y puede introducir artefactos."
        ),
    }


def separate(audio_path: str, out_dir: str, *, method: str = "auto",
             cancel_check: CancelCheck = None, progress: ProgressCb = None) -> dict:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    background = str(Path(out_dir) / "background.wav")
    info = ffmpeg.probe(audio_path)
    channels = info.get("audio_channels") or 0
    if channels < 2:
        raise SeparationError(
            "La separación necesita audio estéreo; este video es mono.",
            "Desactiva la separación para este proyecto: se conservará el audio original "
            "atenuado bajo el doblaje.",
        )

    use_demucs = method == "demucs" or (method == "auto" and demucs_available())
    if use_demucs:
        if not demucs_available():
            raise SeparationError(
                "Demucs no está instalado.",
                "Instálalo con «pip install demucs» o desactiva la separación para usar "
                "la conservación del fondo con atenuación.",
            )
        _run_demucs(audio_path, out_dir, cancel_check=cancel_check, progress=progress)
        stems = list(Path(out_dir).rglob("no_vocals.wav"))
        if not stems:
            raise SeparationError("Demucs no produjo la pista de fondo.",
                                  "Revisa el registro o desactiva la separación.")
        ffmpeg.normalize_audio(str(stems[0]), background, sample_rate=48000,
                               channels=2, cancel_check=cancel_check)
        used = "demucs"
        note = ("Separación neuronal aplicada. Aun así pueden quedar restos de voz o "
                "sonidos perdidos; revisa el resultado.")
    else:
        if progress:
            progress(0.2, "Separando canal central")
        cmd = [
            ffmpeg.ffmpeg_path(), "-nostdin", "-y", "-v", "error", "-i", audio_path,
            "-af", "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0,aresample=48000",
            "-c:a", "pcm_s16le", background,
        ]
        ffmpeg.run_command(cmd, cancel_check=cancel_check, timeout=3600)
        used = "center_cancel"
        note = ("Se usó cancelación de canal central (sin IA): conserva mejor la música "
                "estéreo, pero puede eliminar sonidos centrados y dejar artefactos. "
                "Para mayor calidad instala Demucs.")

    if not _has_signal(background):
        try:
            Path(background).unlink()
        except OSError:
            pass
        raise SeparationError(
            "El fondo separado quedó en silencio.",
            "Desactiva la separación; el doblaje usará el audio original atenuado.",
        )
    if progress:
        progress(1.0, "Fondo separado")
    return {"background": background, "method": used, "warning": note}


def _run_demucs(audio_path: str, out_dir: str, *, cancel_check: CancelCheck,
                progress: ProgressCb) -> None:
    with tempfile.TemporaryDirectory(prefix="demucs_") as tmp:
        cmd = [
            sys.executable, "-m", "demucs", "--two-stems", "vocals",
            "-n", "htdemucs", "-o", tmp, audio_path,
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, creationflags=SUBPROCESS_FLAGS)
        while proc.poll() is None:
            if cancel_check and cancel_check():
                proc.kill()
                raise CancelledError("Trabajo cancelado durante la separación.")
            try:
                _, err = proc.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                continue
        if proc.returncode != 0:
            raise SeparationError(
                "Demucs falló al separar el audio.",
                f"Puede faltar memoria o el modelo. Detalle: {(err or '')[-500:]}",
            )
        for stem in Path(tmp).rglob("*.wav"):
            shutil.copy2(stem, Path(out_dir) / stem.name)
    if progress:
        progress(0.9, "Separación completada")


def _has_signal(path: str) -> bool:
    try:
        data, _ = sf.read(path, dtype="float32", always_2d=True,
                          frames=48000 * 30)
        return bool(np.sqrt(np.mean(np.square(data))) > 0.0008)
    except Exception:
        return Path(path).exists() and Path(path).stat().st_size > 1000
