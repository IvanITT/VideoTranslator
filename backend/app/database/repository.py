"""Data access helpers used by the API and the worker."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from app.database.db import get_conn, row_to_dict

STAGES = [
    "analysis",
    "extraction",
    "asr",
    "translation",
    "separation",
    "tts",
    "sync",
    "mix",
    "render",
]

STAGE_LABELS = {
    "analysis": "Análisis del video",
    "extraction": "Extracción de audio",
    "asr": "Reconocimiento de voz",
    "translation": "Traducción al español",
    "separation": "Separación de voz y fondo",
    "tts": "Generación de voz",
    "sync": "Sincronización de audio",
    "mix": "Mezcla de audio",
    "render": "Renderizado final",
    "validate": "Validación y exportación",
}

ACTIVE_STATUSES = ("queued", "running", "cancelling")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _project(row) -> dict | None:
    data = row_to_dict(row)
    if not data:
        return None
    data["has_audio"] = bool(data.get("has_audio"))
    return data


class ProjectsRepo:
    @staticmethod
    def create(project_id: str, name: str, original_filename: str, source_path: str,
               size_bytes: int, probe: dict) -> dict:
        now = utcnow()
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO projects (id, name, original_filename, source_path, size_bytes,
                   duration, width, height, fps, video_codec, audio_codec, has_audio,
                   created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (project_id, name, original_filename, source_path, size_bytes,
                 probe.get("duration"), probe.get("width"), probe.get("height"),
                 probe.get("fps"), probe.get("video_codec"), probe.get("audio_codec"),
                 1 if probe.get("has_audio") else 0, now, now),
            )
        return ProjectsRepo.get(project_id)  # type: ignore[return-value]

    @staticmethod
    def get(project_id: str) -> dict | None:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return _project(row)

    @staticmethod
    def list(limit: int = 50) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT p.*, (SELECT j.id FROM jobs j WHERE j.project_id=p.id
                   ORDER BY j.created_at DESC LIMIT 1) AS latest_job_id,
                   (SELECT j.status FROM jobs j WHERE j.project_id=p.id
                   ORDER BY j.created_at DESC LIMIT 1) AS latest_job_status,
                   (SELECT j.output_path FROM jobs j WHERE j.project_id=p.id
                   ORDER BY j.created_at DESC LIMIT 1) AS output_path,
                   EXISTS(SELECT 1 FROM jobs j WHERE j.project_id=p.id
                   AND j.status IN ('queued','running','cancelling')) AS has_active_job
                   FROM projects p ORDER BY p.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            data = _project(row) or {}
            data["has_output"] = bool(data.pop("output_path", None))
            data["active_job"] = bool(data.pop("has_active_job", 0))
            out.append(data)
        return out

    @staticmethod
    def delete(project_id: str) -> None:
        with get_conn() as conn:
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))


class JobsRepo:
    @staticmethod
    def create(job_id: str, project_id: str, settings: dict) -> dict:
        now = utcnow()
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO jobs (id, project_id, status, progress, settings, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (job_id, project_id, "queued", 0, json.dumps(settings), now),
            )
            for stage in STAGES:
                conn.execute(
                    "INSERT INTO job_stages (job_id, stage, status) VALUES (?,?,?)",
                    (job_id, stage, "pending"),
                )
        return JobsRepo.get(job_id)  # type: ignore[return-value]

    @staticmethod
    def get(job_id: str) -> dict | None:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            stages = conn.execute(
                "SELECT * FROM job_stages WHERE job_id=? ORDER BY rowid", (job_id,)
            ).fetchall()
            project = conn.execute(
                "SELECT * FROM projects WHERE id=(SELECT project_id FROM jobs WHERE id=?)",
                (job_id,),
            ).fetchone()
        data = row_to_dict(row)
        if not data:
            return None
        data["settings"] = _loads(data.get("settings"), {})
        data["stats"] = _loads(data.get("stats"), {})
        data["warnings"] = _loads(data.get("warnings"), [])
        data["cancel_requested"] = bool(data.get("cancel_requested"))
        data["stages"] = [
            {**dict(s), "label": STAGE_LABELS.get(s["stage"], s["stage"])} for s in stages
        ]
        data["project"] = _project(project) if project else None
        return data

    @staticmethod
    def list(limit: int = 30, active_only: bool = False) -> list[dict]:
        query = """SELECT j.*, p.name AS project_name FROM jobs j
                   JOIN projects p ON p.id=j.project_id"""
        params: tuple = ()
        if active_only:
            query += " WHERE j.status IN ('queued','running','cancelling')"
        query += " ORDER BY j.created_at DESC LIMIT ?"
        params = (limit,)
        with get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["settings"] = _loads(data.get("settings"), {})
            data["stats"] = _loads(data.get("stats"), {})
            data["warnings"] = _loads(data.get("warnings"), [])
            data.pop("project_name", None)
            data["project_name"] = row["project_name"]
            out.append(data)
        return out

    @staticmethod
    def list_for_project(project_id: str, limit: int = 30) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT j.*, p.name AS project_name FROM jobs j
                   JOIN projects p ON p.id=j.project_id
                   WHERE j.project_id=? ORDER BY j.created_at DESC LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["settings"] = _loads(data.get("settings"), {})
            data["stats"] = _loads(data.get("stats"), {})
            data["warnings"] = _loads(data.get("warnings"), [])
            data.pop("project_name", None)
            out.append(data)
        return out

    @staticmethod
    def update(job_id: str, **fields) -> None:
        if not fields:
            return
        for key in ("settings", "stats", "warnings"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        cols = ", ".join(f"{key}=?" for key in fields)
        with get_conn() as conn:
            conn.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))

    @staticmethod
    def set_stage(job_id: str, stage: str, status: str, progress: float | None = None,
                  detail: str | None = None) -> None:
        now = utcnow()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM job_stages WHERE job_id=? AND stage=?", (job_id, stage)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO job_stages (job_id, stage, status) VALUES (?,?,?)",
                    (job_id, stage, status),
                )
            sets = ["status=?"]
            values: list[Any] = [status]
            if progress is not None:
                sets.append("progress=?")
                values.append(progress)
            if detail is not None:
                sets.append("detail=?")
                values.append(detail)
            if status == "running" and (row is None or row["status"] != "running"):
                sets.append("started_at=?")
                values.append(now)
            if status in ("completed", "failed", "skipped", "cancelled"):
                sets.append("finished_at=?")
                values.append(now)
            values.extend([job_id, stage])
            conn.execute(
                f"UPDATE job_stages SET {', '.join(sets)} WHERE job_id=? AND stage=?",
                values,
            )

    @staticmethod
    def add_event(job_id: str, message: str, level: str = "info") -> None:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO events (job_id, ts, level, message) VALUES (?,?,?,?)",
                (job_id, utcnow(), level, message[:2000]),
            )

    @staticmethod
    def get_events(job_id: str, limit: int = 200) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    @staticmethod
    def mark_interrupted() -> int:
        """Called at startup: jobs left running cannot be alive after a restart."""
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status IN ('running','cancelling')"
            ).fetchall()
            for row in rows:
                conn.execute(
                    """UPDATE jobs SET status='interrupted', message=?,
                       finished_at=? WHERE id=?""",
                    ("La aplicación se cerró durante el procesamiento.", utcnow(), row["id"]),
                )
                conn.execute(
                    """UPDATE job_stages SET status='interrupted'
                       WHERE job_id=? AND status='running'""",
                    (row["id"],),
                )
        return len(rows)


class SegmentsRepo:
    @staticmethod
    def replace_all(job_id: str, segments: Iterable[dict]) -> None:
        with get_conn() as conn:
            conn.execute("DELETE FROM segments WHERE job_id=?", (job_id,))
            for idx, seg in enumerate(segments):
                conn.execute(
                    """INSERT INTO segments (job_id, idx, start, "end", text_src, text_es,
                       tts_path, tts_duration, status, warning)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (job_id, idx, float(seg.get("start", 0)), float(seg.get("end", 0)),
                     seg.get("text_src", ""), seg.get("text_es", ""),
                     seg.get("tts_path"), seg.get("tts_duration"),
                     seg.get("status", "pending"), seg.get("warning")),
                )

    @staticmethod
    def list(job_id: str) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                'SELECT * FROM segments WHERE job_id=? ORDER BY idx', (job_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def update(job_id: str, idx: int, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f'"{k}"=?' if k == "end" else f"{k}=?" for k in fields)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE segments SET {cols} WHERE job_id=? AND idx=?",
                (*fields.values(), job_id, idx),
            )

    @staticmethod
    def get(job_id: str, idx: int) -> dict | None:
        with get_conn() as conn:
            row = conn.execute(
                'SELECT * FROM segments WHERE job_id=? AND idx=?', (job_id, idx)
            ).fetchone()
        return row_to_dict(row)

    @staticmethod
    def reset_tts(job_id: str) -> None:
        with get_conn() as conn:
            conn.execute(
                """UPDATE segments SET tts_path=NULL, tts_duration=NULL,
                   status='pending', warning=NULL WHERE job_id=? AND text_es<>''""",
                (job_id,),
            )


class SettingsRepo:
    DEFAULTS: dict[str, Any] = {
        "cpu_threads": 0,  # 0 = auto
        "preset": "balanced",
        "asr_model": "auto",
        "translation_engine": "auto",
        "voice": "es_MX-ald-medium",
        "target_variant": "es-MX",
        "source_language": "auto",
        "mode": "dub_plus_background",
        "separation": False,
        "keep_temp": False,
        "max_upload_mb": 2048,
        "max_duration_s": 3600,
        "speech_rate": 1.0,
        "volume": 1.0,
        "max_speedup": 1.18,
        "gap_ms": 80,
        "loudness_lufs": -16.0,
        "ducking": True,
        "parallel_jobs": 1,
        "device": "auto",
        "compute_type": "int8",
        "cleanup_days": 7,
        "quantize_translation": False,
    }

    @staticmethod
    def all() -> dict[str, Any]:
        merged = dict(SettingsRepo.DEFAULTS)
        with get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for row in rows:
            try:
                merged[row["key"]] = json.loads(row["value"])
            except ValueError:
                merged[row["key"]] = row["value"]
        return merged

    @staticmethod
    def update(values: dict[str, Any]) -> dict[str, Any]:
        with get_conn() as conn:
            for key, value in values.items():
                if key not in SettingsRepo.DEFAULTS:
                    continue
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
        return SettingsRepo.all()


class ModelDownloadsRepo:
    @staticmethod
    def upsert(model_id: str, status: str, progress: float = 0,
               message: str = "", total_bytes: int = 0, downloaded_bytes: int = 0) -> None:
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO model_downloads (id, status, progress, message, total_bytes,
                   downloaded_bytes, updated_at) VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                   progress=excluded.progress, message=excluded.message,
                   total_bytes=excluded.total_bytes, downloaded_bytes=excluded.downloaded_bytes,
                   updated_at=excluded.updated_at""",
                (model_id, status, progress, message, total_bytes, downloaded_bytes, utcnow()),
            )

    @staticmethod
    def get_all() -> dict[str, dict]:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM model_downloads").fetchall()
        return {r["id"]: dict(r) for r in rows}
