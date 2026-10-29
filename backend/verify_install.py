"""Print a local installation report (used by setup.ps1 and for support)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.core.config import PROJECT_ROOT, config  # noqa: E402
from app.services import models_manager, tts  # noqa: E402


def _line(ok: bool, label: str, detail: str) -> bool:
    marker = "OK  " if ok else "WARN"
    print(f"[{marker}] {label}: {detail}")
    return ok


def version_of(executable: str | None, *args: str) -> str:
    if not executable or not Path(executable).exists():
        return "not found"
    try:
        result = subprocess.run([executable, *args], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
        text = (result.stdout or result.stderr or "").strip().splitlines()
        return text[0] if text else "no output"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"error: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true",
                        help="Fail when AI models are missing")
    args = parser.parse_args(argv)

    print(f"Spanish Dubbing Studio {config.version}")
    print(f"Project:  {PROJECT_ROOT}")
    print(f"Data:     {config.data_dir}")
    print(f"Models:   {config.models_dir}")
    print(f"Python:   {sys.version.split()[0]}  ({sys.executable})")
    print()

    required_ok = True
    required_ok &= _line(bool(config.ffmpeg), "FFmpeg",
                         version_of(config.ffmpeg, "-version"))
    required_ok &= _line(bool(config.ffprobe), "FFprobe",
                         version_of(config.ffprobe, "-version"))
    required_ok &= _line(bool(config.piper), "Piper",
                         version_of(config.piper, "--version"))

    dist = config.frontend_dist / "index.html"
    required_ok &= _line(dist.exists(), "Frontend build",
                         str(config.frontend_dist) if dist.exists()
                         else "missing; run npm run build in frontend/")

    engines = tts.engine_available()
    print(f"[INFO] TTS engines: Piper={engines['piper']} SAPI={engines['sapi']} "
          f"eSpeak={engines['espeak']}")

    installed = models_manager.installed_models()
    for stage, label in (("asr", "Speech recognition"),
                         ("translation", "Translation"),
                         ("tts", "Spanish voice")):
        stage_models = [m for m in installed if m["stage"] == stage]
        ok = bool(stage_models)
        if not ok:
            required_ok = False
        _line(ok, label, ", ".join(m["id"] for m in stage_models) or "none installed")

    total_mb = 0.0
    for model in installed:
        for file in models_manager.model_files(model):
            if file.exists():
                total_mb += file.stat().st_size / (1024 ** 2)
    print(f"[INFO] Installed model files: {total_mb:.0f} MB")
    print()
    if required_ok:
        print("Installation looks complete. Start with:  scripts\\start.ps1")
        return 0
    if args.strict:
        print("Some components are missing. Run scripts\\setup.ps1 or open the Modelos page.")
        return 1
    print("The app can start, but dubbing needs FFmpeg, Piper and the AI models.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
