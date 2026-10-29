"""Shared pytest fixtures.

The test process points ``VTS_DATA_DIR`` at a throw-away directory *before*
importing the application, so the real ``storage/`` folder is never touched.
FFmpeg and the downloaded models are reused from the project (read-only).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="vts_tests_"))

os.environ["VTS_DATA_DIR"] = str(TEST_ROOT / "storage")
os.environ.setdefault("VTS_MODELS_DIR", str(ROOT / "models"))
os.environ.setdefault("VTS_OFFLINE", "1")
sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import soundfile as sf  # noqa: E402

from app.core.config import config  # noqa: E402
from app.database.db import get_conn, init_db  # noqa: E402
from app.workers.queue import queue_manager  # noqa: E402

TABLES = ("events", "segments", "job_stages", "jobs", "projects",
          "model_downloads", "settings")


def pytest_sessionstart(session) -> None:
    init_db()


def pytest_sessionfinish(session, exitstatus) -> None:
    queue_manager.stop()
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_state():
    """Give every test an empty database and empty data folders."""
    init_db()
    with get_conn() as conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
    for folder in (config.uploads_dir, config.projects_dir, config.exports_dir,
                   config.temp_dir):
        folder.mkdir(parents=True, exist_ok=True)
        for child in folder.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    # Drop jobs submitted by a previous test (the worker is normally stopped).
    while True:
        try:
            queue_manager._queue.get_nowait()
        except Exception:  # noqa: BLE001 - queue.Empty
            break
    yield


@pytest.fixture(scope="session")
def media_dir() -> Path:
    path = TEST_ROOT / "media"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_ffmpeg(args: list[str]) -> None:
    if not config.ffmpeg:
        pytest.skip("FFmpeg is not installed")
    subprocess.run([config.ffmpeg, "-nostdin", "-y", "-v", "error", *args],
                   check=True, timeout=120)


@pytest.fixture(scope="session")
def sample_video(media_dir: Path) -> Path:
    """3 second H.264/AAC clip with a tone (no speech needed for media tests)."""
    path = media_dir / "sample.mp4"
    if not path.exists():
        _run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "3", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ])
    return path


@pytest.fixture(scope="session")
def silent_video(media_dir: Path) -> Path:
    path = media_dir / "silent.mp4"
    if not path.exists():
        _run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc=size=160x90:rate=15",
            "-t", "1.5", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(path),
        ])
    return path


@pytest.fixture
def make_wav():
    """Factory: ``make_wav(path, seconds, rate=48000, channels=1)``."""
    def factory(path: str | Path, seconds: float, *, sample_rate: int = 48000,
                channels: int = 1, frequency: float = 220.0) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        frames = max(1, int(round(seconds * sample_rate)))
        t = np.linspace(0.0, seconds, frames, endpoint=False, dtype="float32")
        wave = (0.15 * np.sin(2 * np.pi * frequency * t)).astype("float32")
        data = np.repeat(wave[:, None], channels, axis=1) if channels > 1 else wave
        sf.write(str(path), data, sample_rate, subtype="PCM_16")
        return path

    return factory


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    # The security middleware rejects non-local Host headers.
    return TestClient(app, base_url="http://127.0.0.1:8765",
                      headers={"X-VTS-Client": "web"})


@pytest.fixture
def upload_project(client, sample_video):
    """Create a project through the real upload endpoint and return the JSON."""
    def factory(video: Path | None = None, name: str = "Proyecto de prueba") -> dict:
        video = video or sample_video
        with open(video, "rb") as handle:
            response = client.post(
                "/api/projects",
                files={"file": (video.name, handle, "video/mp4")},
                data={"name": name},
            )
        assert response.status_code == 201, response.text
        return response.json()

    return factory


@pytest.fixture
def upload_seconds():
    """Small helper to wait for an asynchronous condition."""
    def wait(predicate, timeout: float = 10.0, interval: float = 0.05):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(interval)
        return predicate()

    return wait
