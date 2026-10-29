"""Audio mixing and final MP4 muxing with FFmpeg."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.core.errors import MediaError
from app.services import ffmpeg

CancelCheck = Callable[[], bool] | None
ProgressCb = Callable[[float, str], None] | None

MODES = {
    "dub_only": "Solo doblaje en español",
    "replace_dialogue": "Reemplazar diálogo (fondo original atenuado)",
    "dub_plus_background": "Doblaje + fondo separado",
    "dual": "Doblaje + audio original (dos pistas)",
}


class MixError(MediaError):
    code = "mix_error"


def mix_audio(dub_path: str, output: str, *, background_path: str | None = None,
              mode: str = "dub_plus_background", loudness_lufs: float = -16.0,
              ducking: bool = True, duration: float | None = None,
              background_gain: float = 0.9,
              cancel_check: CancelCheck = None) -> dict:
    """Mix the Spanish dub with an optional background bed, then normalize."""
    if mode not in MODES:
        mode = "dub_plus_background"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    use_background = mode != "dub_only" and bool(background_path) and \
        Path(str(background_path)).exists()

    filter_dub = (
        f"[0:a]aresample=48000,volume=1.0[dub];"
    )
    filter_bg = None
    if use_background:
        gain = max(0.0, min(1.5, background_gain))
        if mode == "replace_dialogue":
            gain *= 0.35
        filter_bg = f"[1:a]aresample=48000,volume={gain:.3f}[bg];"
        if duration:
            # Guarantee the ambience bed survives even when the dub is shorter:
            # sidechaincompress otherwise ends at the shortest input.
            filter_dub = (f"[0:a]aresample=48000,volume=1.0,"
                          f"apad=whole_dur={duration:.3f}[dub];")
            filter_bg = (f"[1:a]aresample=48000,volume={gain:.3f},"
                         f"apad=whole_dur={duration:.3f}[bg];")
        if ducking:
            chain = (
                f"{filter_dub}"
                f"{filter_bg}"
                "[bg][dub]sidechaincompress=threshold=0.025:ratio=8:attack=20:"
                "release=420:makeup=1[bgduck];"
                "[bgduck][dub]amix=inputs=2:duration=longest:normalize=0[mix];"
                f"[mix]loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11,"
                "alimiter=limit=0.95[out]"
            )
        else:
            chain = (
                f"{filter_dub}"
                f"{filter_bg}"
                "[bg][dub]amix=inputs=2:duration=longest:normalize=0[mix];"
                f"[mix]loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11,"
                "alimiter=limit=0.95[out]"
            )
        inputs = ["-i", dub_path, "-i", str(background_path)]
    else:
        chain = (
            f"{filter_dub}"
            f"[dub]loudnorm=I={loudness_lufs}:TP=-1.5:LRA=11,"
            "alimiter=limit=0.95[out]"
        )
        inputs = ["-i", dub_path]

    cmd = [
        ffmpeg.ffmpeg_path(), "-nostdin", "-y", "-v", "error", *inputs,
        "-filter_complex", chain, "-map", "[out]",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
    ]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd.append(output)
    ffmpeg.run_command(cmd, cancel_check=cancel_check, timeout=3600)
    if not Path(output).exists() or Path(output).stat().st_size < 1000:
        raise MixError("La mezcla de audio quedó vacía.",
                       "Revisa el audio original y vuelve a renderizar.")
    return {"path": output, "mode": mode, "background": use_background,
            "ducking": bool(ducking and use_background)}


def render_video(video_path: str, audio_path: str, output: str, *,
                 mode: str = "dub_only", duration: float | None = None,
                 audio_bitrate: str = "192k",
                 include_original: bool = False,
                 cancel_check: CancelCheck = None,
                 progress: ProgressCb = None) -> dict:
    """Mux the new audio with the untouched video stream (stream copy)."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg.ffmpeg_path(), "-nostdin", "-y", "-v", "error",
           "-i", video_path, "-i", audio_path]
    if include_original or mode == "dual":
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-map", "0:a:0?",
                "-metadata:s:a:0", "language=spa",
                "-metadata:s:a:0", "title=Doblaje español",
                "-metadata:s:a:1", "language=und",
                "-metadata:s:a:1", "title=Audio original"]
    else:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    cmd += [
        "-c:v", "copy", "-c:a", "aac", "-b:a", audio_bitrate,
        "-movflags", "+faststart", "-map_metadata", "0", "-progress", "pipe:1",
        "-nostats", output,
    ]
    ffmpeg._run_with_progress(cmd, duration=duration, progress_cb=progress,
                              cancel_check=cancel_check, label="Renderizando video")
    return verify_output(output, expected_duration=duration)


def verify_output(path: str, *, expected_duration: float | None = None) -> dict:
    if not Path(path).exists() or Path(path).stat().st_size < 1000:
        raise MixError("El archivo final no se creó correctamente.",
                       "Revisa el registro del renderizado y vuelve a intentarlo.")
    info = ffmpeg.probe(path)
    warnings: list[str] = []
    if not info.get("has_audio"):
        raise MixError("El video final no tiene pista de audio.",
                       "El renderizado de audio falló; vuelve a renderizar.")
    if expected_duration and abs(info["duration"] - expected_duration) > 1.5:
        warnings.append(
            f"La duración final ({info['duration']:.1f}s) difiere de la original "
            f"({expected_duration:.1f}s)."
        )
    return {
        "path": path,
        "duration": info["duration"],
        "width": info["width"],
        "height": info["height"],
        "fps": info["fps"],
        "video_codec": info["video_codec"],
        "audio_codec": info["audio_codec"],
        "size_bytes": Path(path).stat().st_size,
        "warnings": warnings,
    }


def remaining_time(progress: float, elapsed: float) -> float | None:
    if progress <= 0.01 or elapsed <= 0:
        return None
    return max(0.0, elapsed / progress * (1.0 - progress))
