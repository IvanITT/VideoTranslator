"""Dialogue timing, speed limits and dub-track assembly."""
from __future__ import annotations

import math

import numpy as np
import pytest
import soundfile as sf

from app.core.errors import CancelledError
from app.services import alignment
from app.services.alignment import (AlignmentError, build_dub, clamp_gap,
                                    estimate_duration, fit_text_to_window,
                                    plan_timeline)


# ------------------------------------------------------------------- planning
def test_plan_timeline_keeps_segments_ordered_and_separated():
    segments = [
        {"index": 0, "start": 0.0, "end": 1.0, "speech_duration": 0.5, "text": "A"},
        {"index": 1, "start": 2.0, "end": 3.0, "speech_duration": 0.5, "text": "B"},
        {"index": 2, "start": 3.0, "end": 4.0, "speech_duration": 0.5, "text": "C"},
    ]
    placements, warnings = plan_timeline(segments, 10.0, gap_ms=80, max_speedup=1.18)
    assert len(placements) == 3
    assert warnings == []
    for previous, current in zip(placements, placements[1:]):
        assert current.start >= previous.end
    assert placements[0].start == 0.0
    assert placements[-1].end <= 10.0
    assert all(p.speed == 1.0 for p in placements)


def test_plan_timeline_sorts_unordered_input():
    segments = [
        {"index": 1, "start": 2.0, "end": 3.0, "speech_duration": 0.5},
        {"index": 0, "start": 0.0, "end": 1.0, "speech_duration": 0.5},
    ]
    placements, _ = plan_timeline(segments, 5.0)
    assert [p.index for p in placements] == [0, 1]
    assert placements[0].start == 0.0


def test_plan_timeline_speeds_up_but_respects_limit():
    segments = [
        {"index": 0, "start": 0.0, "end": 1.0, "speech_duration": 2.0, "text": "long"},
        {"index": 1, "start": 1.0, "end": 2.0, "speech_duration": 0.3, "text": "next"},
    ]
    placements, warnings = plan_timeline(segments, 10.0, gap_ms=80, max_speedup=1.18)
    first = placements[0]
    assert first.speed == pytest.approx(1.18)
    assert first.warning is not None and warnings
    assert first.end <= 10.0
    # The next segment is pushed after the stretched line, never overlapped.
    assert placements[1].start >= first.end


def test_plan_timeline_never_exceeds_video_duration():
    segments = [
        {"index": 0, "start": 9.5, "end": 10.0, "speech_duration": 2.0, "text": "tail"},
    ]
    placements, warnings = plan_timeline(segments, 10.0)
    assert placements[0].end == pytest.approx(10.0)
    assert placements[0].speed > 1.18  # documented extra compression for the tail
    assert any("recort" in warning.lower() for warning in warnings)


def test_plan_timeline_skips_empty_audio():
    segments = [
        {"index": 0, "start": 0.0, "end": 1.0, "speech_duration": 0.0},
        {"index": 1, "start": 1.0, "end": 2.0, "speech_duration": 0.5},
    ]
    placements, _ = plan_timeline(segments, 5.0)
    assert [p.index for p in placements] == [1]


def test_plan_timeline_handles_empty_input():
    assert plan_timeline([], 5.0) == ([], [])


def test_plan_timeline_clamps_start_past_end():
    placements, _ = plan_timeline(
        [{"index": 0, "start": 30.0, "end": 31.0, "speech_duration": 0.4}], 10.0
    )
    assert placements[0].start <= 10.0 - 0.25 + 1e-6


# --------------------------------------------------------------- dub assembly
def test_build_dub_preserves_total_duration(make_wav, tmp_path):
    first = make_wav(tmp_path / "a.wav", 0.5, channels=1)
    second = make_wav(tmp_path / "b.wav", 0.6, channels=1)
    segments = [
        {"idx": 0, "start": 0.0, "end": 0.5, "text_es": "uno",
         "tts_path": str(first), "tts_duration": 0.5},
        {"idx": 1, "start": 1.2, "end": 1.8, "text_es": "dos",
         "tts_path": str(second), "tts_duration": 0.6},
    ]
    output = tmp_path / "dub.wav"
    result = build_dub(segments, str(output), total_duration=2.0, gap_ms=80)
    assert output.exists()
    assert result.duration == pytest.approx(2.0, abs=0.02)
    assert result.max_speed == 1.0
    assert len(result.placements) == 2
    assert result.warnings == []
    info = sf.info(str(output))
    assert info.samplerate == 48000
    assert info.channels == 2
    assert abs(info.frames - 2.0 * 48000) <= 2

    data, _ = sf.read(str(output), dtype="float32", always_2d=True)
    assert np.max(np.abs(data)) > 0.01  # actual speech present
    # The second line only starts at 1.2 s: the gap stays silent.
    assert np.max(np.abs(data[int(0.7 * 48000):int(1.1 * 48000)])) < 0.001


def test_build_dub_applies_atempo_for_long_lines(make_wav, tmp_path):
    long = make_wav(tmp_path / "long.wav", 1.2, channels=1)
    segments = [
        {"idx": 0, "start": 0.0, "end": 1.2, "text_es": "larga",
         "tts_path": str(long), "tts_duration": 1.2},
    ]
    output = tmp_path / "dub.wav"
    result = build_dub(segments, str(output), total_duration=1.0, gap_ms=0,
                       max_speedup=1.18)
    assert result.max_speed >= 1.18
    assert sf.info(str(output)).frames == pytest.approx(48000, abs=4)
    # The sped-up line must still be audible.
    data, _ = sf.read(str(output), dtype="float32", always_2d=True)
    assert np.max(np.abs(data)) > 0.01


def test_build_dub_cancellation(make_wav, tmp_path):
    segment = make_wav(tmp_path / "a.wav", 0.5)
    with pytest.raises(CancelledError):
        build_dub(
            [{"idx": 0, "start": 0.0, "end": 0.5, "tts_path": str(segment),
              "tts_duration": 0.5}],
            str(tmp_path / "dub.wav"), total_duration=1.0,
            cancel_check=lambda: True,
        )


def test_build_dub_requires_audio(tmp_path):
    with pytest.raises(AlignmentError):
        build_dub([], str(tmp_path / "dub.wav"), total_duration=1.0)
    with pytest.raises(AlignmentError):
        build_dub(
            [{"idx": 0, "start": 0.0, "end": 1.0, "tts_path": str(tmp_path / "gone.wav"),
              "tts_duration": 1.0}],
            str(tmp_path / "dub.wav"), total_duration=1.0,
        )


# --------------------------------------------------------------------- helpers
def test_estimate_duration_and_text_fitting():
    short = "Hola"
    long = "Bueno, pues la verdad es que simplemente quería decirte algo importante"
    assert estimate_duration(short) >= 0.6
    assert estimate_duration(long) > estimate_duration(short)
    assert fit_text_to_window(short, 5.0) == (short, False)
    trimmed, changed = fit_text_to_window(long, 0.8)
    assert changed is True
    assert len(trimmed) < len(long)


def test_clamp_gap():
    assert clamp_gap(80) == 80
    assert clamp_gap(-3) == 0
    assert clamp_gap(99999) == 1000
    assert clamp_gap("bad") == 80  # type: ignore[arg-type]
    assert clamp_gap(None) == 80  # type: ignore[arg-type]


def test_placement_rounding_is_stable():
    placements, _ = plan_timeline(
        [{"index": 0, "start": 0.123456, "end": 1.987654,
          "speech_duration": 0.456789}], 5.0
    )
    placement = placements[0]
    assert placement.start == round(placement.start, 3)
    assert placement.end == round(placement.end, 3)
    assert not math.isnan(placement.speed)
