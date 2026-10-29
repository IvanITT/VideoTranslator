"""Subtitle and transcript exporters."""
from __future__ import annotations

from app.services.alignment import seconds_to_srt


def to_srt(segments: list[dict]) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        text = (seg.get("text_es") or seg.get("text_src") or "").strip()
        if not text:
            continue
        start = seconds_to_srt(seg.get("start", 0))
        end = seconds_to_srt(max(seg.get("end", 0), seg.get("start", 0) + 0.5))
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _vtt_time(seconds: float) -> str:
    return seconds_to_srt(seconds).replace(",", ".")


def to_vtt(segments: list[dict]) -> str:
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(segments, start=1):
        text = (seg.get("text_es") or seg.get("text_src") or "").strip()
        if not text:
            continue
        start = _vtt_time(seg.get("start", 0))
        end = _vtt_time(max(seg.get("end", 0), seg.get("start", 0) + 0.5))
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def to_transcript(segments: list[dict], *, include_source: bool = True) -> str:
    lines = ["TRANSCRIPCIÓN Y DOBLAJE", "=" * 24, ""]
    for i, seg in enumerate(segments, start=1):
        stamp = f"[{seconds_to_srt(seg.get('start', 0))} → {seconds_to_srt(seg.get('end', 0))}]"
        lines.append(f"{i}. {stamp}")
        if include_source and seg.get("text_src"):
            lines.append(f"   Original: {seg['text_src']}")
        lines.append(f"   Español:  {seg.get('text_es', '')}")
        lines.append("")
    return "\n".join(lines)
