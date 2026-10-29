"""Local-only security helpers: origin checks, CSRF header, path containment."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Request

from app.core.config import config
from app.core.errors import SecurityError

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
CLIENT_HEADER = "x-vts-client"


def _allowed_origins(request: Request) -> set[str]:
    host = request.headers.get("host", f"127.0.0.1:{config.port}")
    port = host.split(":")[-1] if ":" in host else str(config.port)
    return {
        host,
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
    }


def verify_request(request: Request) -> None:
    """Reject cross-site mutations while keeping browser and CLI use simple."""
    if not config.is_local_host(request.headers.get("host")):
        raise SecurityError(
            "Solicitud rechazada: la API solo acepta conexiones locales.",
            "Abre la aplicación desde http://127.0.0.1 en este equipo.",
        )
    if request.method not in MUTATING:
        return

    origin = request.headers.get("origin")
    if origin:
        netloc = urlparse(origin).netloc
        if netloc not in _allowed_origins(request):
            raise SecurityError(
                "Solicitud bloqueada por protección de origen (CSRF).",
                "Usa la interfaz oficial en http://127.0.0.1. No abras la API desde otros sitios.",
            )
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site and fetch_site not in ("same-origin", "same-site", "none"):
        raise SecurityError(
            "Solicitud bloqueada: origen externo.",
            "Las operaciones de escritura solo se permiten desde la interfaz local.",
        )
    if request.headers.get(CLIENT_HEADER) != "web":
        raise SecurityError(
            "Falta la cabecera de cliente local.",
            f"Añade «{CLIENT_HEADER}: web» a la petición o usa la interfaz de la aplicación.",
        )


def ensure_within(path: str | Path, root: str | Path) -> Path:
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise SecurityError(
            "Ruta de archivo no permitida.",
            "Solo se accede a archivos dentro de las carpetas configuradas.",
        )
    return resolved


def sanitize_filename(name: str, fallback: str = "video.mp4") -> str:
    name = Path(name or "").name
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", name).strip(" .")
    if not name:
        return fallback
    if len(name) > 120:
        stem, dot, suffix = name.rpartition(".")
        name = (stem[:100] + dot + suffix[:10]) if dot else name[:120]
    return name


def safe_slug(name: str, fallback: str = "video") -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", name or "")
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return (normalized[:60] or fallback)
