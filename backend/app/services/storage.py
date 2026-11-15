"""Disk lifecycle: orphan cleanup, old intermediates and export copies."""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import config
from app.core.errors import SecurityError
from app.core.security import ensure_within
from app.database.db import get_conn

ACTIVE = ("queued", "running", "cancelling")
INTERMEDIATES = ("audio", "tts", "stems", "dub.wav", "mix.wav")


def _path_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())
    except OSError:
        return 0


def _remove_path(path: Path) -> tuple[int, int]:
    """Remove a file or directory. Returns (top-level entries, bytes)."""
    if not path.exists():
        return 0, 0
    size = _path_size(path)
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError:
        return 0, 0
    return 1, size


def _is_old(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


def _parse_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _job_settings(job: dict) -> dict:
    settings = job.get("settings") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except ValueError:
            settings = {}
    return settings if isinstance(settings, dict) else {}


def remove_export_copy(job: dict) -> int:
    """Delete the export copy associated with a job. Returns freed bytes."""
    stats = job.get("stats") or {}
    if isinstance(stats, str):
        try:
            stats = json.loads(stats)
        except ValueError:
            stats = {}
    paths: list[Path] = []
    if isinstance(stats, dict) and stats.get("export_path"):
        paths.append(Path(str(stats["export_path"])))
    job_id = str(job.get("id") or "")
    if job_id and config.exports_dir.exists():
        paths.extend(config.exports_dir.glob(f"*_{job_id[:8]}.mp4"))

    freed = 0
    seen: set[str] = set()
    for path in paths:
        try:
            target = ensure_within(path, config.exports_dir)
        except SecurityError:
            continue
        key = str(target)
        if key in seen or not target.is_file():
            continue
        seen.add(key)
        try:
            freed += target.stat().st_size
            target.unlink()
        except OSError:
            continue
    return freed


def cleanup(days: int = 7) -> dict:
    """Remove old scratch data, exports and orphaned project/job folders.

    Completed/failed jobs older than ``days`` lose their regenerable
    intermediates (audio, TTS, stems, dub and mix), but keep ``output.mp4``,
    subtitles and the transcript. Jobs with ``keep_temp`` enabled are skipped.
    """
    days = max(1, min(365, int(days)))
    cutoff = time.time() - days * 86400
    result: dict = {"removed": 0, "freed": 0, "days": days, "categories": {}}

    def record(category: str, count: int, freed: int) -> None:
        bucket = result["categories"].setdefault(category, {"removed": 0, "freed": 0})
        bucket["removed"] += count
        bucket["freed"] += freed
        result["removed"] += count
        result["freed"] += freed

    for folder, category in ((config.temp_dir, "temporary"),
                             (config.uploads_dir, "uploads")):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if _is_old(path, cutoff):
                record(category, *_remove_path(path))

    if config.exports_dir.exists():
        for path in config.exports_dir.iterdir():
            if path.is_file() and _is_old(path, cutoff):
                record("exports", *_remove_path(path))

    with get_conn() as conn:
        project_ids = {
            row["id"] for row in conn.execute("SELECT id FROM projects")
        }
        jobs = [dict(row) for row in conn.execute(
            "SELECT id, project_id, status, finished_at, created_at, settings FROM jobs"
        )]
    jobs_by_project: dict[str, set[str]] = {}
    for job in jobs:
        jobs_by_project.setdefault(job["project_id"], set()).add(job["id"])

    if config.projects_dir.exists():
        for project_dir in config.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            if project_dir.name not in project_ids:
                if _is_old(project_dir, cutoff):
                    record("orphan_projects", *_remove_path(project_dir))
                continue
            known_jobs = jobs_by_project.get(project_dir.name, set())
            for job_dir in project_dir.glob("job_*"):
                if not job_dir.is_dir():
                    continue
                if job_dir.name[4:] not in known_jobs and _is_old(job_dir, cutoff):
                    record("orphan_jobs", *_remove_path(job_dir))

    for job in jobs:
        if job["status"] in ACTIVE:
            continue
        if _job_settings(job).get("keep_temp"):
            continue
        finished = _parse_timestamp(job.get("finished_at") or job.get("created_at"))
        if finished is None or finished >= cutoff:
            continue
        job_dir = config.projects_dir / job["project_id"] / f"job_{job['id']}"
        if not job_dir.is_dir():
            continue
        for name in INTERMEDIATES:
            child = job_dir / name
            if child.exists():
                record("job_artifacts", *_remove_path(child))

    result["freed_mb"] = round(result["freed"] / (1024 ** 2), 1)
    for bucket in result["categories"].values():
        bucket["freed_mb"] = round(bucket["freed"] / (1024 ** 2), 1)
    return result
