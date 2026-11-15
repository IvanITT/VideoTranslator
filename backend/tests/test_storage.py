"""Storage lifecycle: old intermediates, exports, orphans and migrations."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import config
from app.database.db import SCHEMA_VERSION, get_conn, init_db
from app.database.repository import JobsRepo, ProjectsRepo
from app.schemas.api import JobSettings
from app.services import storage


def make_project() -> str:
    project_id = uuid.uuid4().hex
    directory = config.projects_dir / project_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "source.mp4").write_bytes(b"source")
    ProjectsRepo.create(
        project_id=project_id, name="Proyecto", original_filename="v.mp4",
        source_path=str(directory / "source.mp4"), size_bytes=6,
        probe={"duration": 3.0, "width": 320, "height": 180, "fps": 25.0,
               "video_codec": "h264", "audio_codec": "aac", "has_audio": True},
    )
    return project_id


def make_job(project_id: str, *, status: str = "completed", days_old: int = 30,
             keep_temp: bool = False) -> str:
    job_id = uuid.uuid4().hex
    payload = JobSettings(keep_temp=keep_temp).model_dump()
    JobsRepo.create(job_id, project_id, payload)
    finished = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat(
        timespec="seconds"
    )
    JobsRepo.update(job_id, status=status, finished_at=finished)
    return job_id


def write_tree(root: Path) -> None:
    for name in ("audio", "tts", "stems"):
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "part.wav").write_bytes(b"x" * 2048)
    for name in ("dub.wav", "mix.wav", "output.mp4"):
        (root / name).write_bytes(b"x" * 2048)
    subtitles = root / "subtitles"
    subtitles.mkdir(parents=True, exist_ok=True)
    (subtitles / "es.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHola\n",
                                      encoding="utf-8")
    (root / "transcript.txt").write_text("Hola", encoding="utf-8")


def age_tree(root: Path, days: int = 30) -> None:
    stamp = time.time() - days * 86400
    for path in [root, *root.rglob("*")]:
        os.utime(path, (stamp, stamp))


def test_cleanup_removes_old_intermediates_and_exports_but_keeps_output():
    project_id = make_project()
    job_id = make_job(project_id)
    job_dir = config.projects_dir / project_id / f"job_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    write_tree(job_dir)

    export = config.exports_dir / f"clip_{job_id[:8]}.mp4"
    export.write_bytes(b"export" * 100)
    age_tree(job_dir)
    os.utime(export, (time.time() - 30 * 86400,) * 2)

    result = storage.cleanup(days=7)

    assert not (job_dir / "audio").exists()
    assert not (job_dir / "tts").exists()
    assert not (job_dir / "stems").exists()
    assert not (job_dir / "dub.wav").exists()
    assert not (job_dir / "mix.wav").exists()
    assert (job_dir / "output.mp4").exists()
    assert (job_dir / "subtitles" / "es.srt").exists()
    assert (job_dir / "transcript.txt").exists()
    assert not export.exists()
    assert result["removed"] >= 6
    assert result["freed"] > 0
    assert "job_artifacts" in result["categories"]
    assert "exports" in result["categories"]


def test_cleanup_respects_active_jobs_and_keep_temp():
    project_id = make_project()
    active_job = make_job(project_id, status="running")
    keep_job = make_job(project_id, keep_temp=True)
    for job_id in (active_job, keep_job):
        job_dir = config.projects_dir / project_id / f"job_{job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        write_tree(job_dir)
        age_tree(job_dir)

    storage.cleanup(days=7)

    for job_id in (active_job, keep_job):
        job_dir = config.projects_dir / project_id / f"job_{job_id}"
        assert (job_dir / "audio").exists()
        assert (job_dir / "mix.wav").exists()


def test_cleanup_removes_orphan_project_and_job_dirs():
    project_id = make_project()
    orphan_project = config.projects_dir / "orphan-project"
    orphan_project.mkdir(parents=True)
    (orphan_project / "old.bin").write_bytes(b"x" * 1024)
    age_tree(orphan_project)

    orphan_job = config.projects_dir / project_id / "job_deadbeef"
    orphan_job.mkdir(parents=True)
    (orphan_job / "old.bin").write_bytes(b"x" * 1024)
    age_tree(orphan_job)

    result = storage.cleanup(days=7)

    assert not orphan_project.exists()
    assert not orphan_job.exists()
    assert result["categories"]["orphan_projects"]["removed"] == 1
    assert result["categories"]["orphan_jobs"]["removed"] == 1


def test_cleanup_removes_old_temp_and_uploads_but_keeps_recent_files():
    old_temp = config.temp_dir / "old.tmp"
    new_temp = config.temp_dir / "new.tmp"
    old_upload = config.uploads_dir / "old.part"
    new_upload = config.uploads_dir / "new.part"
    for path in (old_temp, new_temp, old_upload, new_upload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 128)
    old_stamp = time.time() - 30 * 86400
    os.utime(old_temp, (old_stamp, old_stamp))
    os.utime(old_upload, (old_stamp, old_stamp))

    result = storage.cleanup(days=7)

    assert not old_temp.exists()
    assert not old_upload.exists()
    assert new_temp.exists()
    assert new_upload.exists()
    assert result["categories"]["temporary"]["removed"] == 1
    assert result["categories"]["uploads"]["removed"] == 1


def test_remove_export_copy_deletes_only_the_job_copy():
    project_id = make_project()
    job_id = make_job(project_id)
    export = config.exports_dir / f"clip_{job_id[:8]}.mp4"
    other = config.exports_dir / "keep.mp4"
    export.write_bytes(b"x" * 1024)
    other.write_bytes(b"y" * 512)
    job = JobsRepo.get(job_id)
    job["stats"]["export_path"] = str(export)

    freed = storage.remove_export_copy(job)

    assert freed == 1024
    assert not export.exists()
    assert other.exists()


def test_init_db_tracks_schema_version():
    init_db()
    with get_conn() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION


def test_init_db_applies_legacy_migrations():
    init_db()
    with get_conn() as conn:
        conn.execute("DROP INDEX IF EXISTS idx_jobs_finished")
        conn.execute("PRAGMA user_version=0")

    init_db()

    with get_conn() as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        index = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_jobs_finished'"
        ).fetchone()
    assert version == SCHEMA_VERSION
    assert index is not None
