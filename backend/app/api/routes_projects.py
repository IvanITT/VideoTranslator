"""Project creation, listing and upload validation."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from app.core.config import config
from app.core.errors import AppError, ConflictError, MediaError, NotFoundError, ValidationError
from app.core.security import ensure_within, sanitize_filename
from app.database.repository import JobsRepo, ProjectsRepo, SettingsRepo
from app.services import ffmpeg, models_manager
from app.workers.queue import queue_manager

router = APIRouter(tags=["projects"])

CHUNK = 1024 * 1024


@router.post("/projects", status_code=201)
async def create_project(request: Request, file: UploadFile = File(...),
                         name: str | None = Form(default=None)) -> dict:
    filename = sanitize_filename(file.filename or "video.mp4")
    if Path(filename).suffix.lower() not in {".mp4", ".m4v"}:
        raise ValidationError(
            "Formato no soportado. Sube un archivo MP4.",
            "Exporta el video como MP4 (H.264 + AAC) e inténtalo de nuevo.",
        )
    settings = SettingsRepo.all()
    max_bytes = int(settings.get("max_upload_mb") or config.max_upload_mb) * 1024 * 1024
    project_id = uuid.uuid4().hex
    temp_path = config.uploads_dir / f"{project_id}.part"
    project_dir = config.projects_dir / project_id
    size = 0
    try:
        with open(temp_path, "wb") as out:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValidationError(
                        f"El archivo supera el límite de {max_bytes // (1024 * 1024)} MB.",
                        "Aumenta el límite en Ajustes o comprime el video.",
                    )
                out.write(chunk)
        if size == 0:
            raise ValidationError("El archivo está vacío.",
                                  "Selecciona un video MP4 válido.")
        probe = ffmpeg.probe(str(temp_path))
        if "mp4" not in (probe.get("format") or "") and "mov" not in (probe.get("format") or ""):
            raise ValidationError(
                "El archivo no es un MP4/MOV válido.",
                "Vuelve a exportar el video en formato MP4.",
            )
        max_duration = int(settings.get("max_duration_s") or config.max_duration_s)
        if probe["duration"] > max_duration:
            raise ValidationError(
                f"El video dura {probe['duration'] / 60:.1f} min y el máximo es "
                f"{max_duration / 60:.0f} min.",
                "Acorta el video o aumenta el límite en Ajustes.",
            )
        if probe["duration"] < 0.5:
            raise ValidationError("El video es demasiado corto.",
                                  "Sube un video de al menos un segundo.")
        if not probe.get("has_audio"):
            raise MediaError(
                "El video no tiene pista de audio.",
                "Este sistema necesita diálogo para transcribir y doblar. Sube un video con audio.",
            )
        project_dir.mkdir(parents=True, exist_ok=True)
        source_path = project_dir / "source.mp4"
        shutil.move(str(temp_path), source_path)

        display_name = sanitize_filename(name or Path(filename).stem, fallback=Path(filename).stem)
        if not display_name:
            display_name = Path(filename).stem or "Proyecto"
        project = ProjectsRepo.create(
            project_id=project_id, name=display_name[:120], original_filename=filename,
            source_path=str(source_path), size_bytes=size, probe=probe,
        )
        thumbnail = project_dir / "thumbnail.jpg"
        ffmpeg.make_thumbnail(str(source_path), str(thumbnail),
                              at_seconds=min(1.0, probe["duration"] / 4))
        return {**project, "thumbnail": thumbnail.exists()}
    except Exception:
        temp_path.unlink(missing_ok=True)
        if project_dir.exists() and not ProjectsRepo.get(project_id):
            shutil.rmtree(project_dir, ignore_errors=True)
        raise
    finally:
        await file.close()


@router.get("/projects")
def list_projects(limit: int = 50) -> dict:
    projects = ProjectsRepo.list(limit=max(1, min(200, limit)))
    for project in projects:
        project["thumbnail"] = (config.projects_dir / project["id"] / "thumbnail.jpg").exists()
    return {"projects": projects}


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    project = ProjectsRepo.get(project_id)
    if not project:
        raise NotFoundError("Proyecto no encontrado.", "Actualiza la lista de proyectos.")
    source = ensure_within(project["source_path"], config.data_dir)
    project["source_exists"] = source.exists()
    project["thumbnail"] = (config.projects_dir / project["id"] / "thumbnail.jpg").exists()
    project["jobs"] = JobsRepo.list_for_project(project_id, limit=30)
    return project


@router.get("/projects/{project_id}/thumbnail")
def project_thumbnail(project_id: str):
    project = ProjectsRepo.get(project_id)
    if not project:
        raise NotFoundError("Proyecto no encontrado.", "Actualiza la lista de proyectos.")
    path = ensure_within(config.projects_dir / project_id / "thumbnail.jpg", config.projects_dir)
    if not path.exists():
        raise NotFoundError("Sin miniatura.", "La miniatura se genera al subir el video.")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/projects/{project_id}/video")
def project_video(project_id: str):
    project = ProjectsRepo.get(project_id)
    if not project:
        raise NotFoundError("Proyecto no encontrado.", "Actualiza la lista de proyectos.")
    path = ensure_within(project["source_path"], config.data_dir)
    if not path.exists():
        raise NotFoundError("El video original ya no está disponible.",
                            "Vuelve a subir el archivo.")
    return FileResponse(path, media_type="video/mp4")


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str):
    project = ProjectsRepo.get(project_id)
    if not project:
        raise NotFoundError("Proyecto no encontrado.", "Actualiza la lista de proyectos.")
    jobs = JobsRepo.list_for_project(project_id, limit=200)
    if any(j["status"] in ("queued", "running", "cancelling") for j in jobs):
        raise ConflictError(
            "No se puede eliminar un proyecto con un trabajo en curso.",
            "Cancela el trabajo y espera a que termine antes de borrar el proyecto.",
        )
    directory = ensure_within(config.projects_dir / project_id, config.projects_dir)
    ProjectsRepo.delete(project_id)
    shutil.rmtree(directory, ignore_errors=True)


@router.get("/options")
def options() -> dict:
    from app.schemas.api import LANGUAGES, MODES, PRESETS, TARGET_VARIANTS
    from app.services import separation

    return {
        "languages": [{"value": k, "label": v} for k, v in LANGUAGES.items()],
        "targets": [{"value": k, "label": v} for k, v in TARGET_VARIANTS.items()],
        "modes": [{"value": k, "label": v} for k, v in MODES.items()],
        "presets": [{"value": k, "label": v} for k, v in PRESETS.items()],
        "voices": models_manager.voice_choices(),
        "separation": separation.capability(),
        "max_upload_mb": SettingsRepo.all()["max_upload_mb"],
    }
