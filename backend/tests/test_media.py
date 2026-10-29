"""FFmpeg wrappers, audio extraction, mixing and MP4 muxing."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
import soundfile as sf

from app.core.errors import CancelledError, MediaError
from app.services import ffmpeg, mixing
from app.services.ffmpeg import FFmpegError


# --------------------------------------------------------------------- probing
def test_probe_reports_video_and_audio(sample_video):
    info = ffmpeg.probe(sample_video)
    assert info["width"] == 320
    assert info["height"] == 180
    assert info["has_audio"] is True
    assert info["audio_codec"] == "aac"
    assert info["video_codec"] == "h264"
    assert 2.5 <= info["duration"] <= 3.5
    assert info["fps"] == pytest.approx(25.0, abs=0.1)
    assert info["size_bytes"] > 1000


def test_probe_rejects_missing_file(tmp_path):
    with pytest.raises(MediaError):
        ffmpeg.probe(tmp_path / "nope.mp4")


def test_probe_rejects_non_media_file(tmp_path):
    bogus = tmp_path / "bogus.mp4"
    bogus.write_text("this is not a video", encoding="utf-8")
    with pytest.raises(MediaError):
        ffmpeg.probe(bogus)


def test_probe_detects_missing_audio_track(silent_video):
    info = ffmpeg.probe(silent_video)
    assert info["has_audio"] is False
    assert info["audio_codec"] is None
    assert info["duration"] == pytest.approx(1.5, abs=0.2)


# ------------------------------------------------------------------ extraction
def test_extract_audio_resamples_to_16k_mono(sample_video, tmp_path):
    output = tmp_path / "asr.wav"
    ffmpeg.extract_audio(str(sample_video), str(output), sample_rate=16000,
                         channels=1, duration=3.0)
    assert output.exists()
    info = sf.info(str(output))
    assert info.samplerate == 16000
    assert info.channels == 1
    assert 2.5 <= info.frames / info.samplerate <= 3.5
    assert ffmpeg.probe_audio_duration(str(output)) == pytest.approx(3.0, abs=0.2)


def test_extract_audio_progress_reaches_one(sample_video, tmp_path):
    seen: list[float] = []
    ffmpeg.extract_audio(str(sample_video), str(tmp_path / "a.wav"),
                         sample_rate=16000, channels=1, duration=3.0,
                         progress_cb=lambda value, label: seen.append(value))
    assert seen and seen[-1] == 1.0
    assert all(0.0 <= value <= 1.0 for value in seen)


def test_make_thumbnail_and_wav_duration(sample_video, tmp_path):
    thumb = tmp_path / "thumb.jpg"
    assert ffmpeg.make_thumbnail(str(sample_video), str(thumb)) is True
    assert thumb.exists() and thumb.stat().st_size > 100
    assert ffmpeg.wav_duration(thumb) >= 0.0  # never raises on non-audio files


def test_silence_generator(tmp_path):
    output = tmp_path / "silence.wav"
    ffmpeg.silence(0.5, str(output), sample_rate=48000, channels=2)
    info = sf.info(str(output))
    assert info.samplerate == 48000
    assert info.channels == 2
    assert info.frames / info.samplerate == pytest.approx(0.5, abs=0.02)


# --------------------------------------------------------- timestamps/subtitles
@pytest.mark.parametrize("seconds,expected", [
    (0, "00:00:00,000"),
    (0.001, "00:00:00,001"),
    (61.5, "00:01:01,500"),
    (3599.999, "00:59:59,999"),
    (3600, "01:00:00,000"),
    (3661.25, "01:01:01,250"),
    (-5, "00:00:00,000"),
])
def test_seconds_to_srt(seconds, expected):
    from app.services.alignment import seconds_to_srt

    assert seconds_to_srt(seconds) == expected


def test_subtitle_exporters():
    from app.services import subtitles

    segments = [
        {"start": 0.0, "end": 1.25, "text_es": "Hola mundo", "text_src": "Hello"},
        {"start": 1.5, "end": 2.0, "text_es": "Segunda línea", "text_src": "Second"},
        {"start": 3.0, "end": 4.0, "text_es": "", "text_src": ""},
    ]
    srt = subtitles.to_srt(segments)
    assert "1\n00:00:00,000 --> 00:00:01,250\nHola mundo" in srt
    assert "2\n00:00:01,500 --> 00:00:02,000\nSegunda línea" in srt
    assert srt.count("-->") == 2

    vtt = subtitles.to_vtt(segments)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.250" in vtt

    transcript = subtitles.to_transcript(segments)
    assert "Original: Hello" in transcript
    assert "Español:  Hola mundo" in transcript


# -------------------------------------------------------- subprocess supervision
def test_run_command_cancellation():
    started = time.monotonic()
    with pytest.raises(CancelledError):
        ffmpeg.run_command(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            cancel_check=lambda: time.monotonic() - started > 0.6,
        )
    assert time.monotonic() - started < 6


def test_run_command_timeout():
    with pytest.raises(FFmpegError):
        ffmpeg.run_command([sys.executable, "-c", "import time; time.sleep(10)"],
                           timeout=0.5)


def test_run_command_reports_exit_code():
    with pytest.raises(FFmpegError) as excinfo:
        ffmpeg.run_command([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert "código 3" in excinfo.value.message


# ------------------------------------------------------------------- mixing
def test_mix_audio_dub_only(make_wav, tmp_path):
    dub = make_wav(tmp_path / "dub.wav", 1.5, channels=2)
    output = tmp_path / "mix.wav"
    result = mixing.mix_audio(str(dub), str(output), mode="dub_only",
                              duration=1.5)
    assert result["background"] is False
    assert output.exists() and output.stat().st_size > 1000
    info = sf.info(str(output))
    assert info.samplerate == 48000
    assert info.channels == 2
    assert info.frames / info.samplerate == pytest.approx(1.5, abs=0.1)


def test_mix_audio_with_ducked_background(make_wav, tmp_path):
    dub = make_wav(tmp_path / "dub.wav", 1.0, channels=2, frequency=300)
    bed = make_wav(tmp_path / "bed.wav", 1.5, channels=2, frequency=120)
    output = tmp_path / "mix.wav"
    result = mixing.mix_audio(str(dub), str(output), background_path=str(bed),
                              mode="replace_dialogue", ducking=True, duration=1.5)
    assert result == {"path": str(output), "mode": "replace_dialogue",
                      "background": True, "ducking": True}
    assert sf.info(str(output)).frames / 48000 == pytest.approx(1.5, abs=0.1)


def test_mix_audio_ignores_missing_background(make_wav, tmp_path):
    dub = make_wav(tmp_path / "dub.wav", 0.5, channels=2)
    result = mixing.mix_audio(str(dub), str(tmp_path / "mix.wav"),
                              background_path=str(tmp_path / "missing.wav"),
                              mode="dub_plus_background")
    assert result["background"] is False


def test_render_video_preserves_streams(sample_video, make_wav, tmp_path):
    dub = make_wav(tmp_path / "dub.wav", 3.0, channels=2)
    output = tmp_path / "output.mp4"
    progress: list[float] = []
    result = mixing.render_video(str(sample_video), str(dub), str(output),
                                 duration=3.0,
                                 progress=lambda value, label: progress.append(value))
    assert output.exists()
    assert result["width"] == 320 and result["height"] == 180
    assert result["video_codec"] == "h264"
    assert result["audio_codec"] == "aac"
    assert 2.5 <= result["duration"] <= 3.5
    assert progress and progress[-1] == 1.0


def test_render_video_dual_keeps_original_track(sample_video, make_wav, tmp_path):
    dub = make_wav(tmp_path / "dub.wav", 3.0, channels=2)
    output = tmp_path / "dual.mp4"
    mixing.render_video(str(sample_video), str(dub), str(output), mode="dual",
                        include_original=True, duration=3.0)
    listing = ffmpeg.run_command([
        ffmpeg.ffprobe_path(), "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(output),
    ])
    assert len([line for line in listing.stdout.splitlines() if line.strip()]) == 2


def test_verify_output_rejects_bad_files(tmp_path):
    with pytest.raises(mixing.MixError):
        mixing.verify_output(str(tmp_path / "missing.mp4"))
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"x" * 10)
    with pytest.raises(mixing.MixError):
        mixing.verify_output(str(tiny))
