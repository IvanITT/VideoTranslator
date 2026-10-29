"""Local text-to-speech adapters.

Piper is the primary engine (ONNX Runtime, CPU-friendly). Windows SAPI is a
last-resort fallback for machines without a Piper binary; the UI marks the
engine that was actually used.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from app.core.config import SUBPROCESS_FLAGS, config
from app.core.errors import AppError, CancelledError, ModelMissingError, ValidationError
from app.services import ffmpeg

CancelCheck = Callable[[], bool]
ProgressCb = Callable[[float, str], None]

_lock = threading.Lock()


class TTSError(AppError):
    code = "tts_error"
    status_code = 500


def clean_text(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", text or "")  # annotations
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def available_voice_files(model: dict) -> tuple[Path, Path]:
    directory = config.models_dir / model["local_dir"]
    onnx_files = list(directory.glob("*.onnx"))
    if not onnx_files:
        raise ModelMissingError(
            "La voz seleccionada no está instalada.",
            "Abre «Modelos» y descarga una voz en español.",
        )
    onnx = onnx_files[0]
    conf = Path(str(onnx) + ".json")
    return onnx, conf


def engine_available() -> dict:
    return {
        "piper": bool(config.piper and Path(config.piper).exists()),
        "sapi": os.name == "nt",
        "espeak": bool(__import__("shutil").which("espeak-ng")),
    }


def synthesize(text: str, output: str, *, model: dict, rate: float = 1.0,
               volume: float = 1.0, cancel_check: CancelCheck | None = None) -> dict:
    """Generate one WAV segment at 48 kHz mono. Returns metadata."""
    text = clean_text(text)
    if not text:
        raise ValidationError("El segmento no tiene texto para sintetizar.",
                              "Escribe una traducción antes de regenerar el audio.")
    output = str(output)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    rate = min(1.8, max(0.6, float(rate or 1.0)))
    volume = min(2.0, max(0.0, float(volume if volume is not None else 1.0)))

    if model.get("engine") == "piper" and config.piper and Path(config.piper).exists():
        engine = _piper(text, output, model=model, rate=rate, volume=volume,
                        cancel_check=cancel_check)
    elif os.name == "nt":
        engine = _sapi(text, output, rate=rate, volume=volume, cancel_check=cancel_check)
    else:
        raise TTSError(
            "No hay un motor de voz local disponible.",
            "Ejecuta scripts/setup.ps1 para instalar Piper (incluido en tools/piper).",
        )
    duration = ffmpeg.wav_duration(output)
    if duration <= 0:
        raise TTSError("La voz generada está vacía.",
                       "Prueba a regenerar el segmento o cambia de voz.")
    return {"path": output, "duration": round(duration, 3), "engine": engine,
            "rate": rate, "volume": volume}


def _piper(text: str, output: str, *, model: dict, rate: float, volume: float,
           cancel_check: CancelCheck | None) -> str:
    onnx, conf = available_voice_files(model)
    with tempfile.TemporaryDirectory(prefix="piper_") as tmp:
        raw = str(Path(tmp) / "raw.wav")
        cmd = [
            str(config.piper), "--model", str(onnx), "--config", str(conf),
            "--output_file", raw, "--length_scale", f"{1.0 / rate:.4f}",
            "--sentence_silence", "0.12", "--quiet",
        ]
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=SUBPROCESS_FLAGS,
        )
        try:
            _, err = proc.communicate(text, timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise TTSError("La síntesis de voz excedió el tiempo máximo.",
                           "Acorta el texto del segmento o usa una voz más ligera.")
        if cancel_check and cancel_check():
            raise CancelledError("Trabajo cancelado durante la generación de voz.")
        if proc.returncode != 0 or not Path(raw).exists():
            raise TTSError(
                "Piper no pudo generar el audio del segmento.",
                f"Revisa la instalación de Piper y la voz. Detalle: {(err or '')[-500:]}",
            )
        gain = f"volume={volume:.2f},aresample=48000" if volume != 1.0 else "aresample=48000"
        ffmpeg.run_command([
            ffmpeg.ffmpeg_path(), "-nostdin", "-y", "-v", "error", "-i", raw,
            "-af", gain, "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", output,
        ], timeout=300, cancel_check=cancel_check)
    return "piper"


def _sapi(text: str, output: str, *, rate: float, volume: float,
          cancel_check: CancelCheck | None) -> str:
    """Windows built-in voices. Offline, but less natural than Piper."""
    import shutil

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise TTSError("No se encontró PowerShell para la voz SAPI.",
                       "Instala Piper desde scripts/setup.ps1.")
    with tempfile.TemporaryDirectory(prefix="sapi_") as tmp:
        raw = str(Path(tmp) / "raw.wav")
        script = str(Path(tmp) / "speak.ps1")
        text_file = str(Path(tmp) / "text.txt")
        Path(text_file).write_text(text, encoding="utf-8")
        sapi_rate = int(round((rate - 1.0) * 4))
        sapi_volume = int(round(volume * 100))
        Path(script).write_text(
            "Add-Type -AssemblyName System.Speech\n"
            f"$text = [IO.File]::ReadAllText('{text_file}', [Text.Encoding]::UTF8)\n"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            "$es = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } | Select-Object -First 1\n"
            "if ($es) { $s.SelectVoice($es.VoiceInfo.Name) }\n"
            f"$s.Rate = {sapi_rate}\n$s.Volume = {sapi_volume}\n"
            f"$s.SetOutputToWaveFile('{raw}')\n$s.Speak($text)\n$s.Dispose()\n",
            encoding="utf-8",
        )
        proc = subprocess.Popen(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=SUBPROCESS_FLAGS,
        )
        try:
            _, err = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise TTSError("La voz SAPI excedió el tiempo máximo.",
                           "Acorta el segmento o instala Piper.")
        if cancel_check and cancel_check():
            raise CancelledError("Trabajo cancelado durante la generación de voz.")
        if proc.returncode != 0 or not Path(raw).exists():
            raise TTSError("Windows SAPI no pudo generar la voz.",
                           f"Detalle: {(err or '')[-400:]}")
        ffmpeg.run_command([
            ffmpeg.ffmpeg_path(), "-nostdin", "-y", "-v", "error", "-i", raw,
            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", output,
        ], timeout=300)
    return "sapi"


def list_sapi_voices() -> list[str]:
    if os.name != "nt":
        return []
    try:
        import shutil

        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return []
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command",
             "Add-Type -AssemblyName System.Speech; "
             "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() "
             "| ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }"],
            capture_output=True, text=True, timeout=20, creationflags=SUBPROCESS_FLAGS,
        )
        return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []
