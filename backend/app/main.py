"""FastAPI application entry point (localhost only)."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_jobs, routes_models, routes_projects, routes_settings, routes_system
from app.core.config import config
from app.core.errors import AppError, SecurityError
from app.core.security import verify_request
from app.database.db import init_db
from app.database.repository import JobsRepo
from app.workers.queue import queue_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("vts")

app = FastAPI(
    title="Spanish Dubbing Studio",
    version=config.version,
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def local_security(request: Request, call_next):
    try:
        verify_request(request)
    except SecurityError as exc:
        return JSONResponse(status_code=exc.status_code,
                            content={"error": exc.to_dict()})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path == "/" or request.url.path.endswith(".html"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
            "font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; "
            "form-action 'self'",
        )
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.to_dict()})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    log.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": {
        "code": "internal_error",
        "message": "Error interno inesperado.",
        "hint": "Revisa la consola del backend y vuelve a intentarlo. El progreso del "
                "trabajo se conserva.",
    }})


for router in (routes_system.router, routes_projects.router, routes_jobs.router,
               routes_models.router, routes_settings.router):
    app.include_router(router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    interrupted = JobsRepo.mark_interrupted()
    if interrupted:
        log.warning("%s trabajo(s) quedaron interrumpidos; pueden reanudarse.", interrupted)
    queue_manager.start()
    log.info("Spanish Dubbing Studio %s · http://%s:%s", config.version,
             config.host, config.port)
    if not config.ffmpeg:
        log.error("FFmpeg no encontrado: ejecuta scripts/setup.ps1")


@app.on_event("shutdown")
def _shutdown() -> None:
    queue_manager.stop()


_dist = config.frontend_dist
if (_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": {
            "code": "not_found", "message": "Endpoint no encontrado.", "hint": None}})
    if _dist.exists():
        target = (_dist / full_path).resolve()
        if target.is_file() and _dist.resolve() in target.parents:
            return FileResponse(target)
        index = _dist / "index.html"
        if index.exists():
            return FileResponse(index)
    return JSONResponse(status_code=503, content={
        "error": {
            "code": "frontend_not_built",
            "message": "La interfaz web no está compilada.",
            "hint": "Ejecuta scripts/setup.ps1 o `npm install && npm run build` en frontend/.",
        }
    })


def main() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=config.host, port=config.port,
                log_level="info", reload=False, access_log=False)


if __name__ == "__main__":
    main()
