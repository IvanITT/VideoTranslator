"""Settings, options and local maintenance."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.core.config import config
from app.core.errors import ValidationError
from app.database.repository import SettingsRepo
from app.schemas.api import SettingsUpdate
from app.services import hardware, models_manager, storage, tts

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings() -> dict:
    settings = SettingsRepo.all()
    return {
        "settings": settings,
        "defaults": SettingsRepo.DEFAULTS,
        "recommendation": hardware.recommend_profile(),
        "paths": {
            "data_dir": str(config.data_dir),
            "models_dir": str(config.models_dir),
            "exports_dir": str(config.exports_dir),
            "temporary_dir": str(config.temp_dir),
        },
        "voices": models_manager.voice_choices(),
        "capabilities": {
            "piper": bool(config.piper and Path(config.piper).exists()),
            "sapi_voices": tts.list_sapi_voices(),
            "gpu": hardware.get_hardware()["gpu"],
        },
    }


@router.put("/settings")
def update_settings(body: SettingsUpdate) -> dict:
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    if not values:
        return get_settings()
    if "device" in values and values["device"] not in ("auto", "cpu", "cuda"):
        raise ValidationError("Dispositivo no válido.", "Usa auto, cpu o cuda.")
    if "voice" in values:
        name = values["voice"]
        model = models_manager.find_by_voice(name)
        if not model:
            raise ValidationError("Voz desconocida.", "Elige una voz de la lista.")
        if not models_manager.is_installed(model):
            raise ValidationError(
                f"La voz «{model['name']}» no está descargada.",
                "Descárgala desde «Modelos» antes de seleccionarla.",
            )
    updated = SettingsRepo.update(values)
    return {"settings": updated, "defaults": SettingsRepo.DEFAULTS}


@router.post("/maintenance/cleanup")
def cleanup(days: int = 7) -> dict:
    """Remove old scratch data, exports and orphaned project/job folders."""
    return storage.cleanup(days)
