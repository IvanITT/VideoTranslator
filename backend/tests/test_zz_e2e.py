"""Real end-to-end dubbing test.

Marked ``slow``: uploads a real English clip, runs the whole local pipeline
(Whisper Tiny -> MarianMT -> Piper -> sync -> mix -> MP4), then transcribes the
resulting audio again to prove it is actually Spanish.

Requires FFmpeg, Piper, whisper-tiny, marian-en-es and the default Spanish
voice (see docs/INSTALL.md). Skip with ``pytest -m "not slow"``.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.core.config import config
from app.database.repository import JobsRepo, SegmentsRepo
from app.services import asr, ffmpeg, models_manager
from app.workers.queue import queue_manager

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "sample_en.mp4"
REQUIRED_MODELS = ("whisper-tiny", "marian-en-es", "piper-es-mx-ald-medium")


def _requirements_missing() -> list[str]:
    missing: list[str] = []
    if not config.ffmpeg or not Path(config.ffmpeg).exists():
        missing.append("FFmpeg")
    if not config.piper or not Path(config.piper).exists():
        missing.append("Piper")
    if not SAMPLE.exists():
        missing.append("samples/sample_en.mp4")
    for model_id in REQUIRED_MODELS:
        try:
            model = models_manager.get_model(model_id)
        except Exception:  # noqa: BLE001
            missing.append(model_id)
            continue
        if not models_manager.is_installed(model):
            missing.append(model_id)
    return missing


@pytest.mark.slow
def test_real_end_to_end_dubbing(client, tmp_path):
    missing = _requirements_missing()
    if missing:
        pytest.skip("Missing E2E requirements: " + ", ".join(missing))

    with open(SAMPLE, "rb") as handle:
        upload = client.post(
            "/api/projects",
            files={"file": ("sample_en.mp4", handle, "video/mp4")},
            data={"name": "Prueba E2E"},
        )
    assert upload.status_code == 201, upload.text
    project = upload.json()

    created = client.post(f"/api/projects/{project['id']}/jobs", json={
        "source_language": "auto",
        "preset": "low",
        "asr_model": "whisper-tiny",
        "translation_engine": "marian",
        "voice": "es_MX-ald-medium",
        "mode": "dub_only",
        "separation": False,
        "threads": 2,
        "keep_temp": True,
    })
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]

    queue_manager.start()
    deadline = time.monotonic() + 420
    job = JobsRepo.get(job_id)
    try:
        while time.monotonic() < deadline:
            job = JobsRepo.get(job_id)
            if job["status"] in ("completed", "failed", "cancelled", "interrupted"):
                break
            time.sleep(0.5)
        else:
            pytest.fail("The dubbing job did not finish within 7 minutes")

        assert job["status"] == "completed", (
            f"{job['status']}: {job.get('error')} / {job.get('error_hint')}"
        )
        assert job["progress"] == 100
        output_path = Path(job["output_path"] or "")
        assert output_path.exists() and output_path.stat().st_size > 1000

        stats = job["stats"]
        assert stats["asr_model"] == "whisper-tiny"
        assert stats["translation_engine"] == "marian"
        assert stats["tts_engine"] == "piper"
        assert stats["output_duration"] == pytest.approx(project["duration"], abs=1.5)
        assert stats["output_width"] == project["width"]
        assert stats["output_height"] == project["height"]

        segments = SegmentsRepo.list(job_id)
        assert len(segments) >= 1
        assert all(segment["text_src"].strip() for segment in segments)
        assert all(segment["text_es"].strip() for segment in segments)
        assert any(segment["text_es"] != segment["text_src"] for segment in segments)
        assert any(segment["tts_path"] and Path(segment["tts_path"]).exists()
                   for segment in segments)

        srt = client.get(f"/api/jobs/{job_id}/subtitles/srt")
        assert srt.status_code == 200 and "-->" in srt.text
        download = client.get(f"/api/jobs/{job_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("video/mp4")

        # The output must contain a Spanish voice track, not the English one.
        proof_wav = tmp_path / "output_16k.wav"
        ffmpeg.extract_audio(str(output_path), str(proof_wav),
                             sample_rate=16000, channels=1,
                             duration=stats["output_duration"])
        tiny = models_manager.get_model("whisper-tiny")
        result = asr.transcribe(
            str(proof_wav), model_dir=str(models_manager.model_dir(tiny)),
            language=None, threads=2, duration=stats["output_duration"],
        )
        assert result.language == "es", (
            f"Expected Spanish audio, detected {result.language} "
            f"({result.language_probability:.0%})"
        )
        assert result.language_probability >= 0.5
        assert result.segments
    finally:
        queue_manager.stop()
