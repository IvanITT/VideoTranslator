"""Configuration, security and request-validation tests."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError

from app.core.config import AppConfig, config
from app.core.errors import SecurityError, ValidationError
from app.core.security import (ensure_within, safe_slug, sanitize_filename,
                               verify_request)
from app.database.repository import SettingsRepo
from app.schemas.api import JobSettings, SettingsUpdate


# --------------------------------------------------------------- configuration
def test_local_host_detection():
    cfg = AppConfig()
    for host in ("127.0.0.1", "127.0.0.1:8765", "localhost:8765", "[::1]:8765",
                 "0.0.0.0:8765", None):
        assert cfg.is_local_host(host), host
    for host in ("evil.example", "10.0.0.8:8765", "127.0.0.1.evil.com"):
        assert not cfg.is_local_host(host), host


def test_required_directories_exist():
    for folder in (config.data_dir, config.uploads_dir, config.projects_dir,
                   config.exports_dir, config.temp_dir, config.models_dir):
        assert Path(folder).is_dir()


def test_ffmpeg_and_piper_are_discovered():
    assert config.ffmpeg and Path(config.ffmpeg).exists()
    assert config.ffprobe and Path(config.ffprobe).exists()
    assert config.piper and Path(config.piper).exists()


# -------------------------------------------------------------------- security
def test_path_containment_blocks_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "ok.txt"
    inside.write_text("ok", encoding="utf-8")
    assert ensure_within(inside, root) == inside.resolve()
    with pytest.raises(SecurityError):
        ensure_within(root / ".." / "outside.txt", root)
    with pytest.raises(SecurityError):
        ensure_within(tmp_path / "elsewhere.txt", root)


def test_filename_sanitizing():
    assert sanitize_filename("../../evil.mp4") == "evil.mp4"
    assert sanitize_filename('a<b>c?d|e*f.mp4') == "a_b_c_d_e_f.mp4"
    assert sanitize_filename("   ") == "video.mp4"
    assert sanitize_filename("x" * 300 + ".mp4").endswith(".mp4")
    assert len(sanitize_filename("x" * 300 + ".mp4")) <= 120
    assert safe_slug("Mi Video Ñandú.mp4") == "mi-video-nandu-mp4"
    assert safe_slug("///") == "video"


def test_write_requests_reject_non_local_host():
    from app.main import app

    bare = TestClient(app, base_url="http://127.0.0.1:8765",
                      headers={"X-VTS-Client": "web"})
    response = bare.get("/api/health", headers={"host": "attacker.example"})
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "forbidden"
    assert "locales" in body["message"]


def test_write_requests_require_client_header():
    from app.main import app

    bare = TestClient(app, base_url="http://127.0.0.1:8765")
    blocked = bare.post("/api/models/unload")
    assert blocked.status_code == 403
    assert "cabecera" in blocked.json()["error"]["message"].lower()

    allowed = bare.post("/api/models/unload", headers={"X-VTS-Client": "web"})
    assert allowed.status_code == 200


def test_write_requests_reject_cross_site_origin():
    from app.main import app

    bare = TestClient(app, base_url="http://127.0.0.1:8765",
                      headers={"X-VTS-Client": "web"})
    response = bare.post("/api/models/unload", headers={"origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    same = bare.post("/api/models/unload",
                     headers={"origin": "http://127.0.0.1:8765"})
    assert same.status_code == 200


def test_write_requests_reject_sec_fetch_cross_site():
    from app.main import app

    bare = TestClient(app, base_url="http://127.0.0.1:8765",
                      headers={"X-VTS-Client": "web"})
    response = bare.post("/api/models/unload", headers={"sec-fetch-site": "cross-site"})
    assert response.status_code == 403
    # Reads are never blocked by the CSRF rules.
    assert bare.get("/api/health", headers={"sec-fetch-site": "cross-site"}).status_code == 200


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


# ---------------------------------------------------------------- job settings
def test_job_settings_defaults_are_safe():
    settings = JobSettings()
    assert settings.target_language == "es"
    assert settings.target_variant == "es-MX"
    assert settings.mode == "dub_plus_background"
    assert settings.max_speedup == 1.18
    assert settings.separation is False
    assert settings.keep_temp is False


@pytest.mark.parametrize("field,raw,expected", [
    ("speech_rate", 9.0, 1.8),
    ("speech_rate", 0.1, 0.6),
    ("volume", 5.0, 2.0),
    ("volume", -1.0, 0.0),
    ("max_speedup", 4.0, 1.6),
    ("max_speedup", 0.5, 1.0),
    ("gap_ms", -50, 0),
    ("gap_ms", 5000, 1000),
    ("loudness_lufs", -100.0, -30.0),
    ("loudness_lufs", 0.0, -6.0),
    ("threads", 100, 32),
])
def test_job_settings_clamp_values(field, raw, expected):
    settings = JobSettings(**{field: raw})
    assert getattr(settings, field) == expected


@pytest.mark.parametrize("field,value", [
    ("source_language", "klingon"),
    ("target_variant", "es-AR"),
    ("mode", "karaoke"),
    ("preset", "ultra"),
    ("device", "tpu"),
])
def test_job_settings_reject_invalid_enums(field, value):
    with pytest.raises(PydanticValidationError):
        JobSettings(**{field: value})


def test_job_settings_audio_bitrate_falls_back():
    assert JobSettings(audio_bitrate="999k").audio_bitrate == "192k"
    assert JobSettings(audio_bitrate="320k").audio_bitrate == "320k"


def test_settings_update_constraints():
    with pytest.raises(PydanticValidationError):
        SettingsUpdate(max_upload_mb=1)
    with pytest.raises(PydanticValidationError):
        SettingsUpdate(max_duration_s=5)
    with pytest.raises(PydanticValidationError):
        SettingsUpdate(parallel_jobs=4)
    assert SettingsUpdate(gap_ms=250).gap_ms == 250


def test_settings_repo_persists_known_keys_only(client):
    updated = SettingsRepo.update({"gap_ms": 120, "not_a_real_key": "ignored"})
    assert updated["gap_ms"] == 120
    assert "not_a_real_key" not in updated
    assert SettingsRepo.all()["gap_ms"] == 120


def test_validation_error_shape():
    error = ValidationError("mensaje", "pista")
    assert error.status_code == 422
    assert error.to_dict() == {
        "code": "validation_error", "message": "mensaje", "hint": "pista",
    }
