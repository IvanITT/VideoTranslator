"""Hardware detection and preset recommendation (CPU-first)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from functools import lru_cache

import psutil

from app.core.config import SUBPROCESS_FLAGS, config
from app.services import ffmpeg


def _physical_cores() -> int:
    try:
        return psutil.cpu_count(logical=False) or (os.cpu_count() or 2) // 2
    except Exception:
        return max(1, (os.cpu_count() or 2) // 2)


def _gpu_info() -> dict:
    """Detect NVIDIA GPUs and VRAM without assuming CUDA is installed."""
    info = {"available": False, "name": None, "vram_gb": None, "backend": None}
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            result = subprocess.run(
                [nvidia, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
                creationflags=SUBPROCESS_FLAGS,
            )
            if result.returncode == 0 and result.stdout.strip():
                first = result.stdout.strip().splitlines()[0]
                name, _, vram = first.partition(",")
                info.update({
                    "available": True,
                    "name": name.strip(),
                    "vram_gb": round(float(vram.strip()) / 1024, 1),
                    "backend": "cuda",
                })
                return info
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            info.update({
                "available": True,
                "name": props.name,
                "vram_gb": round(props.total_memory / (1024 ** 3), 1),
                "backend": "cuda",
            })
    except Exception:
        pass
    return info


def _ffmpeg_version() -> str | None:
    if not config.ffmpeg:
        return None
    try:
        result = subprocess.run(
            [config.ffmpeg, "-version"], capture_output=True, text=True, timeout=10,
            creationflags=SUBPROCESS_FLAGS,
        )
        first = (result.stdout or "").splitlines()[0] if result.stdout else ""
        return first.replace("ffmpeg version ", "").split(" Copyright")[0].strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


@lru_cache(maxsize=1)
def get_hardware() -> dict:
    mem = psutil.virtual_memory()
    total_gb = round(mem.total / (1024 ** 3), 1)
    available_gb = round(mem.available / (1024 ** 3), 1)
    cores = _physical_cores()
    logical = os.cpu_count() or cores
    gpu = _gpu_info()
    free_disk = ffmpeg.available_disk_gb(config.data_dir)
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or "Desconocido",
        "physical_cores": cores,
        "logical_cores": logical,
        "ram_total_gb": total_gb,
        "ram_available_gb": available_gb,
        "gpu": gpu,
        "recommended_threads": max(1, min(4, cores)),
        "disk_free_gb": free_disk,
        "ffmpeg": bool(config.ffmpeg and shutil.which(config.ffmpeg) or config.ffmpeg),
        "ffmpeg_version": _ffmpeg_version(),
        "ffmpeg_path": config.ffmpeg,
        "piper": bool(config.piper),
        "python": platform.python_version(),
    }


def recommend_profile(hw: dict | None = None) -> dict:
    hw = hw or get_hardware()
    ram = hw["ram_total_gb"]
    gpu = hw.get("gpu", {})
    if ram >= 16 and gpu.get("available"):
        profile = "high"
        reason = "RAM suficiente y GPU compatible detectada."
        asr = "whisper-small"
    elif ram >= 7.5:
        profile = "balanced"
        reason = f"{ram} GB de RAM y {hw['physical_cores']} núcleos: equilibrio entre calidad y velocidad."
        asr = "whisper-base"
    else:
        profile = "low"
        reason = f"Solo {ram} GB de RAM: se prioriza velocidad y bajo consumo."
        asr = "whisper-tiny"
    if hw.get("disk_free_gb", 0) < 3:
        reason += " Poco espacio libre en disco: descarga solo los modelos esenciales."
    return {
        "profile": profile,
        "asr_model": asr,
        "translation_engine": "marian" if score_translation(ram) else "marian",
        "voice": "es_MX-ald-medium",
        "separation": bool(gpu.get("available") and ram >= 16),
        "reason": reason,
    }


def score_translation(ram_gb: float) -> str:
    return "marian"


def resource_snapshot() -> dict:
    mem = psutil.virtual_memory()
    hw = get_hardware()
    return {
        **hw,
        "ram_used_gb": round((mem.total - mem.available) / (1024 ** 3), 1),
        "ram_percent": mem.percent,
        "cpu_percent": psutil.cpu_percent(interval=0.15),
    }
