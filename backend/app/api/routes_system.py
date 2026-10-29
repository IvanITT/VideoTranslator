"""Health and environment endpoints."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter

from app.core.config import config
from app.database.db import db_path
from app.services import hardware, models_manager
from app.services.ffmpeg import available_disk_gb
from app.workers.queue import queue_manager

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    checks: list[dict] = []

    checks.append({"id": "backend", "status": "ok", "label": "Backend FastAPI",
                   "detail": f"v{config.version}"})

    ffmpeg_ok = bool(config.ffmpeg and Path(config.ffmpeg).exists())
    checks.append({
        "id": "ffmpeg",
        "status": "ok" if ffmpeg_ok else "error",
        "label": "FFmpeg / FFprobe",
        "detail": hardware.get_hardware().get("ffmpeg_version") if ffmpeg_ok else
        "No instalado. Ejecuta scripts/setup.ps1.",
    })

    piper_ok = bool(config.piper and Path(config.piper).exists())
    checks.append({
        "id": "tts",
        "status": "ok" if piper_ok else "warn",
        "label": "Motor de voz (Piper)",
        "detail": "Disponible" if piper_ok else "No encontrado; se usará la voz SAPI de Windows.",
    })

    storage_ok = True
    try:
        for folder in (config.uploads_dir, config.projects_dir, config.exports_dir,
                       config.temp_dir):
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
    except OSError as exc:
        storage_ok = False
        checks.append({"id": "storage", "status": "error", "label": "Almacenamiento",
                       "detail": f"No se puede escribir: {exc}"})
    if storage_ok:
        checks.append({"id": "storage", "status": "ok", "label": "Almacenamiento",
                       "detail": f"{available_disk_gb(config.data_dir)} GB libres · {config.data_dir}"})

    try:
        with sqlite3.connect(db_path()) as conn:
            conn.execute("SELECT 1")
        db_status = ("ok", "Base de datos SQLite operativa")
    except sqlite3.Error as exc:
        db_status = ("error", f"SQLite: {exc}")
    checks.append({"id": "database", "status": db_status[0], "label": "Base de datos",
                   "detail": db_status[1]})

    installed = models_manager.installed_models()
    asr_ready = any(m["stage"] == "asr" for m in installed)
    tts_ready = any(m["stage"] == "tts" for m in installed)
    tr_ready = any(m["stage"] == "translation" for m in installed)
    checks.append({
        "id": "models",
        "status": "ok" if (asr_ready and tts_ready and tr_ready) else "warn",
        "label": "Modelos de IA",
        "detail": f"{len(installed)} instalados · ASR {'sí' if asr_ready else 'no'} · "
                  f"traducción {'sí' if tr_ready else 'no'} · voz {'sí' if tts_ready else 'no'}",
    })

    hw = hardware.get_hardware()
    checks.append({
        "id": "hardware",
        "status": "ok",
        "label": "Hardware",
        "detail": f"{hw['physical_cores']} núcleos · {hw['ram_total_gb']} GB RAM · "
                  f"{'GPU: ' + str(hw['gpu']['name']) if hw['gpu']['available'] else 'CPU only'}",
    })

    overall = "error" if any(c["status"] == "error" for c in checks) else (
        "degraded" if any(c["status"] == "warn" for c in checks) else "ok"
    )
    return {
        "status": overall,
        "version": config.version,
        "offline_ready": asr_ready and tts_ready and tr_ready and ffmpeg_ok,
        "checks": checks,
        "queue": {"current": queue_manager.current(), "pending": queue_manager.pending()},
    }


@router.get("/system")
def system_info() -> dict:
    hw = hardware.get_hardware()
    installed = models_manager.describe_models()
    models_size = sum(
        sum(f.stat().st_size for f in Path(m["local_path"]).rglob("*") if f.is_file())
        for m in installed if m["installed"]
    )
    try:
        usage = shutil.disk_usage(config.data_dir)
        storage = {"free_gb": round(usage.free / 1024 ** 3, 1),
                   "total_gb": round(usage.total / 1024 ** 3, 1)}
    except OSError:
        storage = {"free_gb": 0, "total_gb": 0}
    return {
        "app": {"name": "Spanish Dubbing Studio", "version": config.version,
                "offline": config.offline},
        "hardware": hardware.resource_snapshot(),
        "recommendation": hardware.recommend_profile(hw),
        "models": {
            "installed": sum(1 for m in installed if m["installed"]),
            "total": len(installed),
            "disk_gb": round(models_size / 1024 ** 3, 2),
            "missing_required": [
                stage for stage, ready in (
                    ("asr", any(m["stage"] == "asr" and m["installed"] for m in installed)),
                    ("translation", any(m["stage"] == "translation" and m["installed"] for m in installed)),
                    ("tts", any(m["stage"] == "tts" and m["installed"] for m in installed)),
                ) if not ready
            ],
        },
        "storage": storage,
        "queue": {"current": queue_manager.current(),
                  "pending": queue_manager.pending()},
        "capabilities": {
            "separation": __import__("app.services.separation", fromlist=["capability"]).capability(),
            "tts": __import__("app.services.tts", fromlist=["engine_available"]).engine_available(),
            "cuda": bool(hw["gpu"]["available"]),
        },
        "privacy": (
            "Todo el procesamiento ocurre en este equipo. No se envían videos, audios, "
            "transcripciones ni datos a servicios externos. La única conexión a internet "
            "posible es la descarga manual de modelos desde Hugging Face."
        ),
    }
