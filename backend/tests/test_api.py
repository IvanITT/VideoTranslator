"""HTTP API: uploads, projects, jobs, editing, media and settings."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core.config import config
from app.database.repository import JobsRepo, SegmentsRepo
from app.schemas.api import JobSettings
from app.services import models_manager


def make_job(project_id: str, *, settings: dict | None = None,
             status: str | None = None) -> str:
    job_id = uuid.uuid4().hex
    payload = JobSettings().model_dump()
    payload.update(settings or {})
    JobsRepo.create(job_id, project_id, payload)
    if status:
        JobsRepo.update(job_id, status=status)
    return job_id


def add_segments(job_id: str, segments: list[dict] | None = None) -> None:
    SegmentsRepo.replace_all(job_id, segments or [
        {"start": 0.0, "end": 1.0, "text_src": "Hello", "text_es": "Hola",
         "status": "ready"},
        {"start": 1.2, "end": 2.0, "text_src": "World", "text_es": "Mundo",
         "status": "ready"},
    ])


# --------------------------------------------------------------------- uploads
def test_upload_creates_project_and_media(client, upload_project, sample_video):
    project = upload_project()
    assert project["id"]
    assert project["duration"] == pytest.approx(3.0, abs=0.2)
    assert project["width"] == 320 and project["height"] == 180
    assert project["has_audio"] is True
    assert project["thumbnail"] is True
    source = Path(project["source_path"])
    assert source.exists()

    listing = client.get("/api/projects")
    assert listing.status_code == 200
    assert any(p["id"] == project["id"] for p in listing.json()["projects"])

    detail = client.get(f"/api/projects/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["source_exists"] is True

    thumbnail = client.get(f"/api/projects/{project['id']}/thumbnail")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"].startswith("image/jpeg")
    assert thumbnail.content[:2] == b"\xff\xd8"

    video = client.get(f"/api/projects/{project['id']}/video")
    assert video.status_code == 200
    assert video.headers["content-type"].startswith("video/mp4")
    assert len(video.content) == source.stat().st_size


def test_project_list_reports_active_job(client, upload_project):
    first = upload_project(name="Con trabajo")
    second = upload_project(name="Sin trabajo")
    job_id = make_job(first["id"], status="running")

    listing = client.get("/api/projects").json()["projects"]
    by_id = {project["id"]: project for project in listing}
    assert by_id[first["id"]]["active_job"] is True
    assert by_id[second["id"]]["active_job"] is False

    detail = client.get(f"/api/projects/{first['id']}").json()
    assert [job["id"] for job in detail["jobs"]] == [job_id]


def test_upload_rejects_wrong_extension(client):
    response = client.post(
        "/api/projects",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/api/projects",
        files={"file": ("empty.mp4", b"", "video/mp4")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_upload_rejects_fake_mp4(client):
    response = client.post(
        "/api/projects",
        files={"file": ("fake.mp4", b"not a video" * 100, "video/mp4")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] in ("media_error", "validation_error")


def test_upload_rejects_video_without_audio(client, silent_video):
    with open(silent_video, "rb") as handle:
        response = client.post(
            "/api/projects",
            files={"file": ("silent.mp4", handle, "video/mp4")},
        )
    assert response.status_code == 422
    assert "audio" in response.json()["error"]["message"].lower()


def test_upload_requires_csrf_header(sample_video):
    from fastapi.testclient import TestClient

    from app.main import app

    bare = TestClient(app, base_url="http://127.0.0.1:8765")
    with open(sample_video, "rb") as handle:
        response = bare.post("/api/projects",
                             files={"file": ("clip.mp4", handle, "video/mp4")})
    assert response.status_code == 403


def test_missing_project_endpoints(client):
    missing = "0" * 32
    assert client.get(f"/api/projects/{missing}").status_code == 404
    assert client.get(f"/api/projects/{missing}/thumbnail").status_code == 404
    assert client.get(f"/api/projects/{missing}/video").status_code == 404
    assert client.post(f"/api/projects/{missing}/jobs", json={}).status_code == 404
    assert client.delete(f"/api/projects/{missing}").status_code == 404


def test_delete_project_removes_files(client, upload_project):
    project = upload_project()
    directory = config.projects_dir / project["id"]
    assert directory.exists()
    response = client.delete(f"/api/projects/{project['id']}")
    assert response.status_code == 204
    assert not directory.exists()
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_delete_project_with_active_job_is_blocked(client, upload_project):
    project = upload_project()
    make_job(project["id"], status="running")
    response = client.delete(f"/api/projects/{project['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


# -------------------------------------------------------------------- settings
def test_get_options(client):
    response = client.get("/api/options")
    assert response.status_code == 200
    body = response.json()
    assert {"languages", "targets", "modes", "presets", "voices",
            "separation", "max_upload_mb"} <= set(body)
    assert any(target["value"] == "es-MX" for target in body["targets"])


def test_update_settings(client):
    response = client.put("/api/settings", json={"gap_ms": 120,
                                                  "max_speedup": 1.25})
    assert response.status_code == 200
    assert response.json()["settings"]["gap_ms"] == 120
    assert response.json()["settings"]["max_speedup"] == 1.25

    invalid = client.put("/api/settings", json={"gap_ms": 5000})
    assert invalid.status_code == 422


def test_update_settings_rejects_unknown_voice(client):
    response = client.put("/api/settings", json={"voice": "not-a-voice"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------- system
def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded", "error")
    ids = {check["id"] for check in body["checks"]}
    assert {"backend", "ffmpeg", "storage", "database", "models"} <= ids
    assert body["offline_ready"] is True


def test_system_endpoint(client):
    response = client.get("/api/system")
    assert response.status_code == 200
    body = response.json()
    assert body["app"]["name"] == "Spanish Dubbing Studio"
    assert "hardware" in body and "storage" in body
    assert body["privacy"]


def test_models_endpoints(client):
    listing = client.get("/api/models")
    assert listing.status_code == 200
    body = listing.json()
    assert len(body["models"]) >= 8
    assert all("installed" in model for model in body["models"])

    base = client.get("/api/models/whisper-base")
    assert base.status_code == 200
    assert base.json()["installed"] is True
    assert client.get("/api/models/nope").status_code == 404


# ------------------------------------------------------------------------ jobs
def test_create_job_requires_models(client, upload_project, monkeypatch):
    project = upload_project()
    monkeypatch.setattr(models_manager, "is_installed", lambda model: False)
    response = client.post(f"/api/projects/{project['id']}/jobs", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "model_missing"


def test_create_job_validates_body(client, upload_project):
    project = upload_project()
    response = client.post(f"/api/projects/{project['id']}/jobs",
                           json={"source_language": "klingon"})
    assert response.status_code == 422


def test_create_and_cancel_queued_job(client, upload_project):
    project = upload_project()
    created = client.post(f"/api/projects/{project['id']}/jobs",
                          json={"mode": "dub_only", "preset": "low"})
    assert created.status_code == 202
    job = created.json()
    assert job["status"] == "queued"
    assert job["settings"]["mode"] == "dub_only"
    assert len(job["stages"]) == 9

    conflicts = client.post(f"/api/projects/{project['id']}/jobs", json={})
    assert conflicts.status_code == 409

    cancelled = client.post(f"/api/jobs/{job['id']}/cancel")
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert all(stage["status"] == "cancelled" for stage in body["stages"])

    job_detail = client.get(f"/api/jobs/{job['id']}")
    assert job_detail.status_code == 200
    assert "queue" in job_detail.json()


def test_resume_preserves_completed_stages(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="failed")
    JobsRepo.set_stage(job_id, "asr", "completed", 1.0, "Hecho")
    JobsRepo.set_stage(job_id, "translation", "failed", 0.2, "Error")

    response = client.post(f"/api/jobs/{job_id}/resume")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["settings"]["resume"] is True
    stages = {stage["stage"]: stage["status"] for stage in body["stages"]}
    assert stages["asr"] == "completed"
    assert stages["translation"] == "pending"


def test_resume_rejects_completed_job(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="completed")
    response = client.post(f"/api/jobs/{job_id}/resume")
    assert response.status_code == 409


def test_segments_are_listed_and_editable(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="failed")
    add_segments(job_id)

    listing = client.get(f"/api/jobs/{job_id}/segments")
    assert listing.status_code == 200
    assert len(listing.json()["segments"]) == 2

    invalid = client.patch(f"/api/jobs/{job_id}/segments/0",
                           json={"end": 0.0})
    assert invalid.status_code == 422

    updated = client.patch(f"/api/jobs/{job_id}/segments/0",
                           json={"text_es": "  Hola de nuevo  "})
    assert updated.status_code == 200
    segment = updated.json()
    assert segment["text_es"] == "Hola de nuevo"
    assert segment["tts_path"] is None
    assert segment["status"] == "edited"

    assert client.patch(f"/api/jobs/{job_id}/segments/99",
                        json={"text_es": "x"}).status_code == 404


def test_segment_editing_blocked_while_running(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="running")
    add_segments(job_id)
    response = client.patch(f"/api/jobs/{job_id}/segments/0",
                            json={"text_es": "x"})
    assert response.status_code == 409


def test_regenerate_segment_requeues(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="failed")
    add_segments(job_id)
    SegmentsRepo.update(job_id, 0, tts_path="old.wav", tts_duration=1.0,
                        status="voiced")

    response = client.post(f"/api/jobs/{job_id}/segments/0/regenerate",
                           json={"text_es": "Texto nuevo"})
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "queued"
    segment = SegmentsRepo.get(job_id, 0)
    assert segment["text_es"] == "Texto nuevo"
    assert segment["tts_path"] is None
    assert segment["status"] == "pending"


def test_subtitle_exports(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="completed")
    add_segments(job_id)

    srt = client.get(f"/api/jobs/{job_id}/subtitles/srt")
    assert srt.status_code == 200
    assert "00:00:00,000 --> 00:00:01,000" in srt.text
    assert "Hola" in srt.text
    assert "attachment" in srt.headers["content-disposition"]

    vtt = client.get(f"/api/jobs/{job_id}/subtitles/vtt")
    assert vtt.status_code == 200
    assert vtt.text.startswith("WEBVTT")

    txt = client.get(f"/api/jobs/{job_id}/subtitles/txt")
    assert txt.status_code == 200
    assert "Original: Hello" in txt.text
    assert "Español:  Hola" in txt.text

    assert client.get(f"/api/jobs/{job_id}/subtitles/ass").status_code == 404


def test_job_events(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="failed")
    JobsRepo.add_event(job_id, "Primer evento")
    JobsRepo.add_event(job_id, "Segundo evento", "warning")
    response = client.get(f"/api/jobs/{job_id}/events")
    assert response.status_code == 200
    messages = [event["message"] for event in response.json()["events"]]
    assert messages == ["Primer evento", "Segundo evento"]


def test_media_and_download_missing(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="completed")
    assert client.get(f"/api/jobs/{job_id}/download").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/media/output").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/media/unknown").status_code == 404


def test_download_completed_output(client, upload_project, sample_video):
    project = upload_project()
    job_id = make_job(project["id"], status="completed")
    job_dir = config.projects_dir / project["id"] / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    output = job_dir / "output.mp4"
    output.write_bytes(Path(sample_video).read_bytes())
    JobsRepo.update(job_id, output_path=str(output))

    response = client.get(f"/api/jobs/{job_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")
    assert "espanol" in response.headers["content-disposition"]
    assert len(response.content) == output.stat().st_size


def test_delete_active_job_is_blocked(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="queued")
    assert client.delete(f"/api/jobs/{job_id}").status_code == 409

    JobsRepo.update(job_id, status="failed")
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_jobs_listing(client, upload_project):
    project = upload_project()
    make_job(project["id"], status="completed")
    make_job(project["id"], status="running")
    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 2
    active = client.get("/api/jobs?active_only=true").json()["jobs"]
    assert [job["status"] for job in active] == ["running"]


def test_rerender_requeues_job(client, upload_project):
    project = upload_project()
    job_id = make_job(project["id"], status="completed")
    response = client.post(f"/api/jobs/{job_id}/rerender")
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
