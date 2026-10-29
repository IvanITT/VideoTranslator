"""Single-worker local job queue with cancellation and crash recovery."""
from __future__ import annotations

import logging
import queue
import threading
import time
import traceback

from app.core.config import config
from app.core.errors import AppError, CancelledError
from app.database.repository import JobsRepo, utcnow
from app.workers.pipeline import JobContext, Pipeline

log = logging.getLogger("vts.queue")


class JobQueue:
    def __init__(self) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=20)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._current: str | None = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- public
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="vts-worker", daemon=True)
        self._thread.start()
        log.info("Worker iniciado (1 trabajo a la vez)")

    def stop(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def submit(self, job_id: str) -> None:
        try:
            self._queue.put_nowait(job_id)
        except queue.Full:
            raise AppError(
                "La cola de procesamiento está llena.",
                "Espera a que terminen los trabajos actuales (máximo 20).",
            )

    def cancel(self, job_id: str) -> dict:
        job = JobsRepo.get(job_id)
        if not job:
            raise AppError("El trabajo no existe.", "Actualiza la lista de proyectos.")
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        JobsRepo.update(job_id, cancel_requested=1, status="cancelling",
                        message="Cancelando…")
        JobsRepo.add_event(job_id, "Cancelación solicitada por el usuario.", "warning")
        if job["status"] == "queued":
            JobsRepo.update(job_id, status="cancelled", finished_at=utcnow(),
                            message="Cancelado antes de iniciar")
            for stage in job["stages"]:
                if stage["status"] in ("pending", "running"):
                    JobsRepo.set_stage(job_id, stage["stage"], "cancelled",
                                       detail="Cancelado")
        return JobsRepo.get(job_id) or job

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            return self._current == job_id

    def current(self) -> str | None:
        with self._lock:
            return self._current

    def pending(self) -> int:
        return self._queue.qsize()

    # ---------------------------------------------------------------- worker
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if job_id is None:
                break
            if self._stop.is_set():
                break
            self._run(job_id)

    def _run(self, job_id: str) -> None:
        job = JobsRepo.get(job_id)
        if not job:
            return
        with self._lock:
            self._current = job_id
        try:
            if job.get("cancel_requested"):
                JobsRepo.update(job_id, status="cancelled", finished_at=utcnow(),
                                message="Cancelado antes de iniciar")
                return
            JobsRepo.update(job_id, status="running", started_at=job.get("started_at") or utcnow(),
                            message="Iniciando procesamiento", error=None, error_hint=None,
                            cancel_requested=0)
            JobsRepo.add_event(job_id, "Trabajo iniciado.")
            ctx = JobContext(job_id)
            pipeline = Pipeline(ctx)
            result = pipeline.run()
            JobsRepo.update(
                job_id, status="completed", progress=100, stage="render",
                message="Doblaje completado", finished_at=utcnow(),
                output_path=result["path"], stats=ctx.stats, warnings=ctx.warnings,
                error=None, error_hint=None,
            )
            JobsRepo.add_event(job_id, "Trabajo completado correctamente.")
            try:
                pipeline.cleanup()
            except Exception:  # noqa: BLE001 - cleanup must never fail a job
                pass
            _cleanup_other_temp()
        except CancelledError:
            JobsRepo.update(job_id, status="cancelled", finished_at=utcnow(),
                            message="Trabajo cancelado", cancel_requested=0)
            JobsRepo.add_event(job_id, "Trabajo cancelado. Puedes reanudarlo más tarde.", "warning")
            _mark_running_stages(job_id, "cancelled")
        except AppError as exc:
            JobsRepo.update(job_id, status="failed", finished_at=utcnow(),
                            message=exc.message, error=exc.message, error_hint=exc.hint)
            JobsRepo.add_event(job_id, f"Error: {exc.message} {exc.hint or ''}", "error")
            _mark_running_stages(job_id, "failed")
        except Exception as exc:  # noqa: BLE001 - surface a safe message
            log.error("Fallo inesperado en el trabajo %s:\n%s", job_id, traceback.format_exc())
            message = f"Error inesperado durante el procesamiento: {type(exc).__name__}."
            hint = ("Revisa el registro y vuelve a intentarlo. Si el problema continúa, "
                    "prueba con un modelo más ligero o un video más corto.")
            JobsRepo.update(job_id, status="failed", finished_at=utcnow(),
                            message=message, error=message, error_hint=hint)
            JobsRepo.add_event(job_id, f"{message} {str(exc)[:300]}", "error")
            _mark_running_stages(job_id, "failed")
        finally:
            with self._lock:
                self._current = None
            try:
                from app.services import asr, translation

                asr.unload_all()
                translation.unload_all()
            except Exception:  # noqa: BLE001
                pass


def _mark_running_stages(job_id: str, status: str) -> None:
    job = JobsRepo.get(job_id)
    if not job:
        return
    for stage in job["stages"]:
        if stage["status"] == "running":
            JobsRepo.set_stage(job_id, stage["stage"], status)


def _cleanup_other_temp() -> None:
    """Remove stale scratch files older than 24h; keep project artifacts."""
    import os
    from pathlib import Path

    try:
        cutoff = time.time() - 86400
        for path in Path(config.temp_dir).glob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                try:
                    os.remove(path)
                except OSError:
                    pass
    except OSError:
        pass


queue_manager = JobQueue()
