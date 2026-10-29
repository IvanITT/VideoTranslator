"""Model manager endpoints. Downloads are always explicit user actions."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import config
from app.core.errors import NotFoundError
from app.database.repository import ModelDownloadsRepo
from app.services import asr, hardware, models_manager, translation

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models() -> dict:
    described = models_manager.describe_models()
    return {
        "models": described,
        "downloads": ModelDownloadsRepo.get_all(),
        "recommendation": hardware.recommend_profile(),
        "storage": str(config.models_dir),
    }


@router.post("/models/{model_id}/download", status_code=202)
def download(model_id: str) -> dict:
    model = models_manager.get_model(model_id)
    result = models_manager.download_model(model["id"], background=True)
    return {**result, "model_id": model_id}


@router.delete("/models/{model_id}", status_code=202)
def remove(model_id: str) -> dict:
    models_manager.remove_model(model_id)
    return {"status": "removed", "model_id": model_id}


@router.post("/models/unload")
def unload() -> dict:
    asr.unload_all()
    translation.unload_all()
    return {"status": "unloaded", "message": "Modelos liberados de la memoria RAM."}


@router.get("/models/{model_id}")
def get_model(model_id: str) -> dict:
    try:
        model = models_manager.get_model(model_id)
    except NotFoundError:
        raise
    return {
        **model,
        "installed": models_manager.is_installed(model),
        "download": ModelDownloadsRepo.get_all().get(model_id),
    }
