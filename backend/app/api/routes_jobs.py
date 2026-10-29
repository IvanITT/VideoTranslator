"""Job lifecycle, transcript editing and media delivery."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, PlainTextResponse

from app.core.config import config
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import ensure_within, safe_slug
from app.database.repository import JobsRepo, ProjectsRepo, SegmentsRepo, SettingsRepo, STAGES
from app.schemas.api import JobSettings, SegmentRegenerate, SegmentUpdate
from app.services import ffmpeg, models_manager, subtitles
from app.workers.queue import queue_manager

router = APIRouter(tags=["jobs"])

JOB_SETTING_KEYS = set(JobSettings.model_fields.keys())
ACTIVE = ("queued", "running", "cancelling")


@router.post("/projects/{project_id}/jobs", status_code=202)
def create_job(project_id: str, body: JobSettings | None = None) -> dict:
    project = ProjectsRepo.get(project_id)
    if not project:
        raise NotFoundError("Proyecto no encontrado.", "Vuelve a subir el video.")
    active = [j for j in JobsRepo.list_for_project(project_id, limit=200)
              if j["status"] in ACTIVE]
    if active:
        raise ConflictError(
            "Ya hay un trabajo en curso para este proyecto.",
            "Espera a que termine o cancélalo antes de iniciar otro.",
        )
    defaults = SettingsRepo.all()
    payload = body or JobSettings()
    merged = {k: defaults[k] for k in JOB_SETTING_KEYS if k in defaults}
    merged.update(payload.model_dump())
    merged["threads"] = merged.get("threads") or defaults.get("cpu_threads") or 0
    merged["resume"] = False
    settings = JobSettings(**merged)

    _preflight_models(settings)

    import uuid

    job_id = uuid.uuid4().hex
    job = JobsRepo.create(job_id, project_id, settings.model_dump())
    queue_manager.submit(job_id)
    return job


def _preflight_models(settings: JobSettings) -> None:
    missing: list[str] = []
    if not any(m["stage"] == "asr" and models_manager.is_installed(m)
               for m in models_manager.all_models()):
        missing.append("reconocimiento de voz (Whisper)")
    if settings.source_language in ("auto", None, ""):
        if not any(m["stage"] == "translation" and models_manager.is_installed(m)
                   for m in models_manager.all_models()):
            missing.append("traducción (MarianMT o NLLB)")
    else:
        try:
            models_manager.resolve_translation_model(settings.source_language, settings.preset)
        except Exception:
            missing.append(f"traducción para «{settings.source_language}» → español")
    voice = models_manager.find_by_voice(settings.voice)
    if not voice or not models_manager.is_installed(voice):
        if not any(m["stage"] == "tts" and models_manager.is_installed(m)
                   for m in models_manager.all_models()):
            missing.append("voz en español (Piper)")
    if missing:
        from app.core.errors import ModelMissingError

        raise ModelMissingError(
            "Faltan modelos para iniciar el doblaje: " + ", ".join(missing) + ".",
            "Abre «Modelos» y descarga los modelos marcados como esenciales. "
            "Solo se descargan cuando tú lo pides.",
        )


@router.get("/jobs")
def list_jobs(limit: int = 30, active_only: bool = False) -> dict:
    return {"jobs": JobsRepo.list(limit=max(1, min(100, limit)), active_only=active_only)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = JobsRepo.get(job_id)
    if not job:
        raise NotFoundError("Trabajo no encontrado.", "Actualiza la lista de proyectos.")
    job["queue"] = {"current": queue_manager.current(), "pending": queue_manager.pending()}
    job["elapsed_s"] = _elapsed(job)
    return job


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, limit: int = 200) -> dict:
    _require_job(job_id)
    return {"events": JobsRepo.get_events(job_id, limit=max(1, min(500, limit)))}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    return queue_manager.cancel(job_id)


@router.post("/jobs/{job_id}/resume", status_code=202)
def resume_job(job_id: str) -> dict:
    job = _require_job(job_id)
    if job["status"] in ACTIVE:
        raise ConflictError("El trabajo ya está activo o en cola.",
                            "Espera a que termine o cancélalo primero.")
    if job["status"] == "completed":
        raise ConflictError(
            "Este trabajo ya está completado.",
            "Para volver a procesarlo, crea un nuevo trabajo desde el proyecto.",
        )
    _requeue(job_id)
    return JobsRepo.get(job_id) or job


def _requeue(job_id: str) -> None:
    job = JobsRepo.get(job_id)
    if not job:
        raise NotFoundError("Trabajo no encontrado.", "Actualiza la lista.")
    settings = dict(job.get("settings") or {})
    settings["resume"] = True
    JobsRepo.update(
        job_id, status="queued", message="En cola para reanudar", error=None,
        error_hint=None, cancel_requested=0, finished_at=None, settings=settings,
    )
    for stage in job["stages"]:
        if stage["status"] not in ("completed", "skipped"):
            JobsRepo.set_stage(job_id, stage["stage"], "pending", 0.0, None)
    queue_manager.submit(job_id)


@router.post("/jobs/{job_id}/rerender", status_code=202)
def rerender_job(job_id: str) -> dict:
    """Re-run TTS for edited segments and re-render a completed job."""
    job = _require_job(job_id)
    if job["status"] in ACTIVE:
        raise ConflictError("El trabajo ya está en curso.",
                            "Espera a que termine antes de volver a renderizar.")
    _requeue(job_id)
    return JobsRepo.get(job_id) or job


@router.get("/jobs/{job_id}/segments")
def job_segments(job_id: str) -> dict:
    job = _require_job(job_id)
    segments = SegmentsRepo.list(job_id)
    return {"segments": segments, "duration": (job.get("project") or {}).get("duration")}


@router.patch("/jobs/{job_id}/segments/{idx}")
def update_segment(job_id: str, idx: int, body: SegmentUpdate) -> dict:
    job = _require_job(job_id)
    if job["status"] in ("running", "queued", "cancelling"):
        raise ConflictError(
            "No se puede editar mientras el trabajo está activo.",
            "Espera a que termine el procesamiento.",
        )
    segment = SegmentsRepo.get(job_id, idx)
    if not segment:
        raise NotFoundError("Segmento no encontrado.", "Actualiza la transcripción.")
    fields: dict = {}
    if body.text_es is not None:
        text = body.text_es.strip()
        fields["text_es"] = text
        if text != segment.get("text_es"):
            fields["tts_path"] = None
            fields["tts_duration"] = None
            fields["status"] = "edited"
            old = segment.get("tts_path")
            if old:
                try:
                    ensure_within(old, config.data_dir).unlink(missing_ok=True)
                except (OSError, Exception):
                    pass
    if body.start is not None:
        fields["start"] = max(0.0, body.start)
    if body.end is not None:
        fields["end"] = max(0.0, body.end)
    start = fields.get("start", segment["start"])
    end = fields.get("end", segment["end"])
    if end <= start:
        raise ValidationError("El fin del segmento debe ser posterior al inicio.",
                              "Ajusta los tiempos del segmento.")
    SegmentsRepo.update(job_id, idx, **fields)
    return SegmentsRepo.get(job_id, idx) or {}


@router.post("/jobs/{job_id}/segments/{idx}/regenerate", status_code=202)
def regenerate_segment(job_id: str, idx: int, body: SegmentRegenerate | None = None) -> dict:
    job = _require_job(job_id)
    if job["status"] in ("running", "queued", "cancelling"):
        raise ConflictError("El trabajo está activo.",
                            "Espera a que termine antes de regenerar un segmento.")
    segment = SegmentsRepo.get(job_id, idx)
    if not segment:
        raise NotFoundError("Segmento no encontrado.", "Actualiza la transcripción.")
    if body and body.text_es is not None:
        text = body.text_es.strip()
        if not text:
            raise ValidationError("La traducción no puede quedar vacía.",
                                  "Escribe el texto en español para este segmento.")
        SegmentsRepo.update(job_id, idx, text_es=text)
    old = segment.get("tts_path")
    if old:
        try:
            ensure_within(old, config.data_dir).unlink(missing_ok=True)
        except (OSError, Exception):
            pass
    SegmentsRepo.update(job_id, idx, tts_path=None, tts_duration=None, status="pending")
    _sync_translation_artifact(job_id)
    _requeue(job_id)
    return {"status": "queued", "job_id": job_id, "segment": idx}


def _sync_translation_artifact(job_id: str) -> None:
    job = _require_job(job_id)
    job_dir = config.projects_dir / (job.get("project") or {}).get("id", "") / f"job_{job_id}"
    path = job_dir / "translation.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["segments"] = SegmentsRepo.list(job_id)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass


@router.get("/jobs/{job_id}/segments/{idx}/audio")
def segment_audio(job_id: str, idx: int):
    segment = SegmentsRepo.get(job_id, idx)
    if not segment or not segment.get("tts_path"):
        raise NotFoundError(
            "Este segmento aún no tiene audio generado.",
            "Genera la voz del segmento o procesa el trabajo completo.",
        )
    path = ensure_within(segment["tts_path"], config.data_dir)
    if not path.exists():
        raise NotFoundError("El audio del segmento ya no existe.",
                            "Regenera el segmento para volver a crearlo.")
    return FileResponse(path, media_type="audio/wav",
                        filename=f"segmento_{idx + 1}.wav")


MEDIA_KINDS = {
    "original": ("source.mp4", "video/mp4"),
    "output": ("output.mp4", "video/mp4"),
    "dub": ("dub.wav", "audio/wav"),
    "mix": ("mix.wav", "audio/wav"),
    "background": ("stems/background.wav", "audio/wav"),
}


@router.get("/jobs/{job_id}/media/{kind}")
def job_media(job_id: str, kind: str):
    job = _require_job(job_id)
    if kind not in MEDIA_KINDS:
        raise NotFoundError("Tipo de archivo no válido.", "Revisa la URL.")
    project = job.get("project") or {}
    if kind == "original":
        path = Path(project.get("source_path", ""))
    else:
        path = config.projects_dir / project.get("id", "") / f"job_{job_id}" / MEDIA_KINDS[kind][0]
    path = ensure_within(path, config.data_dir)
    if not path.exists():
        raise NotFoundError(
            "El archivo solicitado no está disponible.",
            "Procesa el trabajo o vuelve a renderizar para generarlo.",
        )
    return FileResponse(path, media_type=MEDIA_KINDS[kind][1])


@router.get("/jobs/{job_id}/download")
def download_output(job_id: str):
    job = _require_job(job_id)
    if not job.get("output_path"):
        raise NotFoundError("El video final aún no está listo.",
                            "Espera a que termine el renderizado.")
    path = ensure_within(job["output_path"], config.data_dir)
    if not path.exists():
        raise NotFoundError("El archivo final ya no existe.",
                            "Vuelve a renderizar el proyecto.")
    name = safe_slug((job.get("project") or {}).get("name", "video"))
    return FileResponse(path, media_type="video/mp4",
                        filename=f"{name}_espanol.mp4")


@router.get("/jobs/{job_id}/subtitles/{fmt}")
def download_subtitles(job_id: str, fmt: str):
    job = _require_job(job_id)
    segments = SegmentsRepo.list(job_id)
    if not segments:
        raise NotFoundError("No hay transcripción disponible.",
                            "Procesa el video primero.")
    name = safe_slug((job.get("project") or {}).get("name", "video"))
    if fmt == "srt":
        content = subtitles.to_srt(segments)
        return PlainTextResponse(content, media_type="application/x-subrip", headers={
            "Content-Disposition": f'attachment; filename="{name}_es.srt"'
        })
    if fmt == "vtt":
        content = subtitles.to_vtt(segments)
        return PlainTextResponse(content, media_type="text/vtt", headers={
            "Content-Disposition": f'attachment; filename="{name}_es.vtt"'
        })
    if fmt == "txt":
        content = subtitles.to_transcript(segments)
        return PlainTextResponse(content, media_type="text/plain; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="{name}_transcripcion.txt"'
        })
    raise NotFoundError("Formato de subtítulos no soportado.", "Usa srt, vtt o txt.")


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str):
    job = _require_job(job_id)
    if job["status"] in ACTIVE:
        raise ConflictError("Cancela el trabajo antes de eliminarlo.",
                            "Pulsa «Cancelar» y espera unos segundos.")
    project = job.get("project") or {}
    directory = ensure_within(config.projects_dir / project.get("id", "") / f"job_{job_id}",
                              config.projects_dir)
    from app.database.db import get_conn

    with get_conn() as conn:
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    shutil.rmtree(directory, ignore_errors=True)


def _require_job(job_id: str) -> dict:
    job = JobsRepo.get(job_id)
    if not job:
        raise NotFoundError("Trabajo no encontrado.", "Actualiza la lista de proyectos.")
    return job


def _elapsed(job: dict) -> float:
    from datetime import datetime, timezone

    started = job.get("started_at")
    if not started:
        return 0.0
    try:
        start = datetime.fromisoformat(started)
        end = datetime.fromisoformat(job["finished_at"]) if job.get("finished_at") else \
            datetime.now(timezone.utc)
        return max(0.0, round((end - start).total_seconds(), 1))
    except (ValueError, TypeError):
        return 0.0
