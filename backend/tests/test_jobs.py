"""Queue lifecycle: cancellation, interruptions, recovery and artifact reuse."""
from __future__ import annotations

import json
import uuid

import pytest

from app.core.config import config
from app.core.errors import CancelledError, MediaError
from app.database.repository import JobsRepo, SegmentsRepo
from app.schemas.api import JobSettings
from app.workers import queue as queue_module
from app.workers.pipeline import JobContext, Pipeline
from app.workers.queue import queue_manager


def make_project(upload_project) -> dict:
    return upload_project()


def make_job(project_id: str, *, settings: dict | None = None) -> str:
    job_id = uuid.uuid4().hex
    payload = JobSettings().model_dump()
    payload.update(settings or {})
    JobsRepo.create(job_id, project_id, payload)
    return job_id


def test_cancel_queued_job_marks_stages():
    # A queued job that never started is cancelled immediately.
    project_id = _project()
    job_id = make_job(project_id)
    result = queue_manager.cancel(job_id)
    assert result["status"] == "cancelled"
    assert all(stage["status"] == "cancelled" for stage in result["stages"])
    assert result["message"] == "Cancelado antes de iniciar"


def test_cancel_finished_job_is_a_noop():
    project_id = _project()
    job_id = make_job(project_id)
    JobsRepo.update(job_id, status="completed")
    result = queue_manager.cancel(job_id)
    assert result["status"] == "completed"
    assert result["cancel_requested"] is False


def test_mark_interrupted_only_touches_live_jobs():
    project_id = _project()
    running = make_job(project_id)
    cancelled = make_job(project_id)
    queued = make_job(project_id)
    JobsRepo.update(running, status="running")
    JobsRepo.update(cancelled, status="cancelling")
    JobsRepo.update(queued, status="queued")
    JobsRepo.set_stage(running, "asr", "running", 0.4, "Transcribiendo")

    assert JobsRepo.mark_interrupted() == 2
    assert JobsRepo.get(running)["status"] == "interrupted"
    assert JobsRepo.get(cancelled)["status"] == "interrupted"
    assert JobsRepo.get(queued)["status"] == "queued"
    assert JobsRepo.get(running)["finished_at"] is not None
    stages = {stage["stage"]: stage["status"] for stage in JobsRepo.get(running)["stages"]}
    assert stages["asr"] == "interrupted"


def test_interrupted_job_can_resume_after_restart(client):
    project = upload_project_for_job(client)
    job_id = make_job(project["id"])
    JobsRepo.update(job_id, status="running")
    JobsRepo.set_stage(job_id, "analysis", "completed", 1.0, "Listo")
    JobsRepo.set_stage(job_id, "extraction", "running", 0.3, "Cortando")
    JobsRepo.mark_interrupted()

    response = client.post(f"/api/jobs/{job_id}/resume")
    assert response.status_code == 202
    job = response.json()
    assert job["settings"]["resume"] is True
    stages = {stage["stage"]: stage["status"] for stage in job["stages"]}
    assert stages["analysis"] == "completed"
    assert stages["extraction"] == "pending"


def test_context_exposes_resume_flag(upload_project):
    project = upload_project()
    job_id = make_job(project["id"], settings={"resume": True})
    ctx = JobContext(job_id)
    assert ctx.resume is True
    assert ctx.job_dir.exists()
    assert ctx.project["id"] == project["id"]
    assert ctx.threads >= 1


def test_cancel_request_is_seen_by_pipeline(upload_project):
    project = upload_project()
    job_id = make_job(project["id"])
    ctx = JobContext(job_id)
    JobsRepo.update(job_id, cancel_requested=1)
    with pytest.raises(CancelledError):
        ctx.check_cancel()


def test_recovery_reuses_persisted_artifacts(upload_project):
    """analysis/extraction/ASR must be skipped when their files already exist."""
    project = upload_project()
    job_id = make_job(project["id"], settings={"resume": True})
    ctx = JobContext(job_id)

    ctx.write_json("analysis.json", {"duration": 3.0, "has_audio": True})
    (ctx.job_dir / "audio").mkdir(parents=True, exist_ok=True)
    (ctx.job_dir / "audio" / "original.wav").write_bytes(b"RIFF")
    (ctx.job_dir / "audio" / "asr.wav").write_bytes(b"RIFF")
    SegmentsRepo.replace_all(job_id, [
        {"start": 0.0, "end": 1.0, "text_src": "Hello", "text_es": "", "status": "transcribed"},
    ])
    ctx.write_json("transcript.json", {
        "info": {"language": "en", "language_probability": 0.9,
                 "model": "whisper-base", "elapsed_s": 1.0},
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
    })
    for stage in ("analysis", "extraction", "asr"):
        JobsRepo.set_stage(job_id, stage, "completed", 1.0, "hecho")
    ctx.stage_status.update({"analysis": "completed", "extraction": "completed",
                             "asr": "completed"})

    pipeline = Pipeline(ctx)
    pipeline._stage_analysis()
    pipeline._stage_extraction()
    pipeline._stage_asr()

    job = JobsRepo.get(job_id)
    statuses = {stage["stage"]: stage["status"] for stage in job["stages"]}
    assert statuses["analysis"] == "skipped"
    assert statuses["extraction"] == "skipped"
    assert statuses["asr"] == "skipped"
    assert pipeline.segments[0]["text_src"] == "Hello"
    events = [event["message"] for event in JobsRepo.get_events(job_id)]
    assert any("reutiliz" in message.lower() for message in events)


def test_pipeline_rejects_missing_source(upload_project):
    project = upload_project()
    job_id = make_job(project["id"])
    ctx = JobContext(job_id)
    Pipeline(ctx)._validate_inputs()  # source exists: no error
    from pathlib import Path

    Path(project["source_path"]).unlink()
    with pytest.raises(MediaError):
        Pipeline(ctx)._validate_inputs()


def test_worker_marks_cancelled(monkeypatch, upload_project):
    project = upload_project()
    job_id = make_job(project["id"])
    JobsRepo.set_stage(job_id, "asr", "running")

    def boom(self):
        raise CancelledError("cancelado en prueba")

    monkeypatch.setattr(queue_module, "Pipeline", boom_pipeline(boom))
    queue_manager._run(job_id)
    job = JobsRepo.get(job_id)
    assert job["status"] == "cancelled"
    assert job["cancel_requested"] is False
    stages = {stage["stage"]: stage["status"] for stage in job["stages"]}
    assert stages["asr"] == "cancelled"


def test_worker_marks_failed_on_app_error(monkeypatch, upload_project):
    project = upload_project()
    job_id = make_job(project["id"])

    def boom(self):
        raise MediaError("audio roto", "usa otro archivo")

    monkeypatch.setattr(queue_module, "Pipeline", boom_pipeline(boom))
    queue_manager._run(job_id)
    job = JobsRepo.get(job_id)
    assert job["status"] == "failed"
    assert "audio roto" in job["error"]
    assert job["error_hint"] == "usa otro archivo"


def test_worker_hides_unexpected_exceptions(monkeypatch, upload_project):
    project = upload_project()
    job_id = make_job(project["id"])

    def boom(self):
        raise RuntimeError("secret/stacktrace")

    monkeypatch.setattr(queue_module, "Pipeline", boom_pipeline(boom))
    queue_manager._run(job_id)
    job = JobsRepo.get(job_id)
    assert job["status"] == "failed"
    assert "RuntimeError" in job["error"]
    assert "secret/stacktrace" not in job["error"]


def test_worker_skips_job_cancelled_before_start(upload_project):
    project = upload_project()
    job_id = make_job(project["id"])
    JobsRepo.update(job_id, status="cancelling", cancel_requested=1)
    queue_manager._run(job_id)
    assert JobsRepo.get(job_id)["status"] == "cancelled"


# --------------------------------------------------------------------- helpers
def boom_pipeline(boom):
    class FakePipeline:
        def __init__(self, ctx):
            self.ctx = ctx

        def run(self):
            return boom(self)

        def cleanup(self):
            return None

    return FakePipeline


def _project() -> str:
    """Create a minimal project row without going through HTTP."""
    from app.database.repository import ProjectsRepo

    project_id = uuid.uuid4().hex
    ProjectsRepo.create(
        project_id=project_id, name="Recuperación", original_filename="v.mp4",
        source_path=str(config.projects_dir / project_id / "source.mp4"),
        size_bytes=10,
        probe={"duration": 3.0, "width": 320, "height": 180, "fps": 25.0,
               "video_codec": "h264", "audio_codec": "aac", "has_audio": True},
    )
    return project_id


def upload_project_for_job(client):
    from pathlib import Path

    sample = Path(__file__).resolve().parents[2] / "samples" / "sample_en.mp4"
    if not sample.exists():
        pytest.skip("sample_en.mp4 is not available")
    with open(sample, "rb") as handle:
        response = client.post("/api/projects",
                               files={"file": ("sample.mp4", handle, "video/mp4")})
    assert response.status_code == 201, response.text
    return response.json()
