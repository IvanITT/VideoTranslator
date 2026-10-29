"""Application configuration.

All paths and defaults are resolved once at import time. Runtime-editable
settings live in SQLite (see ``app.database.settings``) and override these
defaults through :class:`~app.database.repository.SettingsRepo`.
"""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("VTS_ROOT") or Path(__file__).resolve().parents[3]).resolve()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _find_binary(name: str, env_var: str) -> str | None:
    """Locate ffmpeg/ffprobe without assuming it is on PATH."""
    explicit = os.environ.get(env_var)
    if explicit and Path(explicit).exists():
        return str(Path(explicit))
    candidates = [
        PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / f"{name}.exe",
        PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / name,
        PROJECT_ROOT / "tools" / "bin" / f"{name}.exe",
        PROJECT_ROOT / "tools" / "bin" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


def _default_threads() -> int:
    physical = max(1, (os.cpu_count() or 2) // 2)
    return max(1, min(4, physical))


@dataclass(frozen=True)
class AppConfig:
    root: Path = PROJECT_ROOT
    data_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("VTS_DATA_DIR", str(PROJECT_ROOT / "storage"))
    ))
    models_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("VTS_MODELS_DIR", str(PROJECT_ROOT / "models"))
    ))
    frontend_dist: Path = field(default_factory=lambda: PROJECT_ROOT / "frontend" / "dist")
    ffmpeg: str | None = field(default_factory=lambda: _find_binary("ffmpeg", "VTS_FFMPEG"))
    ffprobe: str | None = field(default_factory=lambda: _find_binary("ffprobe", "VTS_FFPROBE"))
    piper: str | None = field(default_factory=lambda: (
        os.environ.get("VTS_PIPER")
        or (str(PROJECT_ROOT / "tools" / "piper" / "piper.exe") if (PROJECT_ROOT / "tools" / "piper" / "piper.exe").exists() else None)
        or (str(PROJECT_ROOT / "tools" / "piper" / "piper") if (PROJECT_ROOT / "tools" / "piper" / "piper").exists() else None)
        or shutil.which("piper")
    ))
    host: str = field(default_factory=lambda: os.environ.get("VTS_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("VTS_PORT", 8765))
    offline: bool = field(default_factory=lambda: _env_bool("VTS_OFFLINE", False))
    max_upload_mb: int = field(default_factory=lambda: _env_int("VTS_MAX_UPLOAD_MB", 2048))
    max_duration_s: int = field(default_factory=lambda: _env_int("VTS_MAX_DURATION_S", 3600))
    worker_poll_s: float = 1.0
    version: str = "1.0.0"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / "temporary"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.uploads_dir,
            self.projects_dir,
            self.exports_dir,
            self.temp_dir,
            self.models_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def is_local_host(self, host_header: str | None) -> bool:
        if not host_header:
            return True
        host = host_header.strip()
        if host.startswith("["):  # IPv6 literal, e.g. [::1]:8765
            end = host.find("]")
            host = host[1:end] if end != -1 else host[1:]
        else:
            host = host.split(":")[0]
        return host.lower() in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


config = AppConfig()
config.ensure_dirs()


def require_ffmpeg() -> None:
    """Fail fast with an actionable message when FFmpeg is missing."""
    if not config.ffmpeg or not Path(config.ffmpeg).exists():
        raise RuntimeError(
            "FFmpeg was not found. Run scripts/setup.ps1 (Windows) or set VTS_FFMPEG "
            "to the full path of the ffmpeg executable."
        )


if sys.platform == "win32":
    # Keep subprocesses from flashing console windows.
    SUBPROCESS_FLAGS = 0x08000000  # CREATE_NO_WINDOW
else:
    SUBPROCESS_FLAGS = 0
