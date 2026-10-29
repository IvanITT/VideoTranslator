"""Download the recommended local models from Hugging Face.

Downloads are explicit and resumable thanks to the Hugging Face cache.
Run from anywhere:

    .venv\\Scripts\\python.exe backend\\download_models.py --minimal
    .venv\\Scripts\\python.exe backend\\download_models.py --list
    .venv\\Scripts\\python.exe backend\\download_models.py whisper-base marian-en-es

Nothing is downloaded by the web application unless the user asks for it in
the Modelos page.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.database.db import init_db  # noqa: E402
from app.database.repository import ModelDownloadsRepo  # noqa: E402
from app.services import models_manager  # noqa: E402

MINIMAL = ["whisper-tiny", "marian-en-es", "piper-es-mx-ald-medium"]
TIMEOUT_SECONDS = 2 * 60 * 60


def _say(message: str = "") -> None:
    print(message, flush=True)


def list_models() -> int:
    _say(f"{'ID':32} {'STAGE':12} {'SIZE':>8}  {'LICENSE':18} INSTALLED")
    _say("-" * 92)
    for model in models_manager.all_models():
        installed = "yes" if models_manager.is_installed(model) else "no"
        size = f"{model.get('approx_size_mb', '?')} MB"
        _say(f"{model['id']:32} {model['stage']:12} {size:>8}  "
             f"{str(model.get('license'))[:18]:18} {installed}")
    _say("")
    _say("Minimal set: " + ", ".join(MINIMAL))
    return 0


def download(model_id: str) -> None:
    model = models_manager.get_model(model_id)
    if models_manager.is_installed(model):
        _say(f"[ok] {model_id} already installed in {model['local_dir']}")
        return

    _say(f"[..] {model['name']}  (~{model.get('approx_size_mb', '?')} MB, "
         f"license: {model.get('license')})")
    result = models_manager.download_model(model_id, background=True)
    if result.get("status") == "installed":
        _say(f"[ok] {model_id} already installed")
        return

    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_line = ""
    while time.monotonic() < deadline:
        state = ModelDownloadsRepo.get_all().get(model_id) or {}
        status = state.get("status")
        if status == "completed":
            if last_line:
                _say("")
            if not models_manager.is_installed(model):
                raise RuntimeError(
                    f"{model_id} finished downloading but required files are missing. "
                    f"Delete models/{model['local_dir']} and try again."
                )
            files = models_manager.model_files(model)
            size_mb = sum(f.stat().st_size for f in files if f.exists()) / (1024 ** 2)
            _say(f"[ok] {model_id} installed ({size_mb:.0f} MB)")
            return
        if status == "failed":
            raise RuntimeError(state.get("message") or f"Download failed: {model_id}")
        progress = float(state.get("progress") or 0.0) * 100
        message = str(state.get("message") or "Downloading...")
        line = f"     {progress:5.1f}%  {message[:70]}"
        if line != last_line:
            print(f"\r{line:<110}", end="", flush=True)
            last_line = line
        time.sleep(0.5)
    raise TimeoutError(f"Timed out while downloading {model_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download local models explicitly")
    parser.add_argument("models", nargs="*", help="Model IDs (default: minimal set)")
    parser.add_argument("--minimal", action="store_true",
                        help="Recommended first install (default)")
    parser.add_argument("--all", action="store_true", help="Download every model")
    parser.add_argument("--list", action="store_true", help="List the manifest")
    args = parser.parse_args(argv)

    init_db()
    if args.list:
        return list_models()

    if args.all:
        ids = [model["id"] for model in models_manager.all_models()]
    elif args.models:
        ids = args.models
    else:
        ids = MINIMAL

    _say(f"Models to install: {', '.join(ids)}")
    failures = 0
    try:
        for model_id in ids:
            try:
                download(model_id)
            except Exception as exc:  # noqa: BLE001 - continue with the next model
                failures += 1
                _say("")
                _say(f"[!!] {model_id}: {exc}")
    except KeyboardInterrupt:
        _say("\nCancelled. Partial downloads resume next time.")
        return 130

    if failures:
        _say("")
        _say(f"{failures} model(s) failed. Check your connection and retry, or use "
             "the Modelos page in the app.")
        return 1
    _say("")
    _say("All requested models are installed. The app can now work offline.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
