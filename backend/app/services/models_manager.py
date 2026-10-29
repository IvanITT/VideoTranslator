"""Model manifest, local installation state and explicit downloads.

Nothing here is downloaded automatically. Model loads always read from the
local directory with ``local_files_only=True`` so the processing pipeline works
without an internet connection.
"""
from __future__ import annotations

import fnmatch
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

from app.core.config import config
from app.core.errors import ModelMissingError, NotFoundError
from app.database.repository import ModelDownloadsRepo

_lock = threading.Lock()
_download_threads: dict[str, threading.Thread] = {}

REQUIRED_FILES = {
    "faster-whisper": ["model.bin", "config.json", "tokenizer.json"],
    "marian": ["pytorch_model.bin", "config.json", "source.spm", "target.spm"],
    "nllb": ["pytorch_model.bin", "config.json", "sentencepiece.bpe.model"],
    "piper": [],  # validated with the .onnx file
}


def _manifest_path() -> Path:
    path = config.models_dir / "manifest.json"
    if not path.exists():
        raise NotFoundError("No se encontró models/manifest.json.",
                            "Restaura el archivo de manifiesto del proyecto.")
    return path


def load_manifest() -> dict:
    with open(_manifest_path(), "r", encoding="utf-8") as handle:
        return json.load(handle)


def all_models() -> list[dict]:
    return load_manifest().get("models", [])


def get_model(model_id: str) -> dict:
    for model in all_models():
        if model["id"] == model_id:
            return model
    raise NotFoundError(f"Modelo desconocido: {model_id}",
                        "Actualiza el manifiesto o elige otro modelo.")


def model_dir(model: dict) -> Path:
    return config.models_dir / model["local_dir"]


def model_files(model: dict) -> list[Path]:
    directory = model_dir(model)
    if "files" in model:
        return [directory / Path(target).name for target in model["files"].values()]
    patterns = model.get("allow_patterns", [])
    required = REQUIRED_FILES.get(model.get("engine", ""), [])
    names = set(required)
    for pattern in patterns:
        if "*" not in pattern:
            names.add(pattern)
    return [directory / name for name in sorted(names)]


def is_installed(model: dict) -> bool:
    directory = model_dir(model)
    if not directory.exists():
        return False
    if model.get("engine") == "piper":
        return bool(list(directory.glob("*.onnx")))
    required = REQUIRED_FILES.get(model.get("engine", ""), [])
    if not required:
        return any(directory.iterdir())
    return all((directory / name).exists() for name in required)


def installed_models() -> list[dict]:
    return [model for model in all_models() if is_installed(model)]


def find_by_voice(voice_id: str) -> dict | None:
    for model in all_models():
        if model.get("stage") == "tts" and model.get("voice", {}).get("id") == voice_id:
            return model
    return None


def resolve_asr_model(preset: str = "balanced") -> dict:
    preferred = {
        "low": "whisper-tiny",
        "balanced": "whisper-base",
        "high": "whisper-small",
    }.get(preset, "whisper-base")
    model = get_model(preferred)
    if is_installed(model):
        return model
    for fallback in ("whisper-base", "whisper-tiny", "whisper-small"):
        candidate = get_model(fallback)
        if is_installed(candidate):
            return candidate
    raise ModelMissingError(
        "No hay ningún modelo de reconocimiento de voz instalado.",
        "Abre «Modelos» y descarga Whisper Base (≈145 MB).",
    )


def resolve_translation_model(source_lang: str, preset: str = "balanced") -> dict:
    if source_lang and source_lang != "auto":
        for model in all_models():
            if model.get("stage") == "translation" and model.get("source_lang") == source_lang \
                    and is_installed(model):
                return model
    nllb = next((m for m in all_models() if m.get("engine") == "nllb" and is_installed(m)), None)
    if nllb:
        return nllb
    lang = source_lang if source_lang and source_lang != "auto" else "en"
    suggestion = f"marian-{lang}-es"
    raise ModelMissingError(
        f"No hay un modelo de traducción instalado para «{lang}» → español.",
        f"Abre «Modelos» y descarga el modelo {suggestion} (≈310 MB) o NLLB-200 "
        "si necesitas más idiomas.",
    )


def resolve_tts_model(voice_id: str) -> dict:
    model = find_by_voice(voice_id)
    if model and is_installed(model):
        return model
    for candidate in all_models():
        if candidate.get("stage") == "tts" and is_installed(candidate):
            return candidate
    raise ModelMissingError(
        "No hay ninguna voz en español instalada.",
        "Abre «Modelos» y descarga la voz «Ald – Español (México)» (≈63 MB).",
    )


def voices() -> list[dict]:
    result = []
    for model in all_models():
        if model.get("stage") != "tts":
            continue
        voice = dict(model.get("voice") or {})
        voice.update({
            "model_id": model["id"],
            "installed": is_installed(model),
            "license": model.get("license"),
            "size_mb": model.get("approx_size_mb"),
            "quality": model.get("quality"),
        })
        result.append(voice)
    return result


def voice_choices() -> list[dict]:
    """Installed voices first, then available ones (marked as not installed)."""
    return sorted(voices(), key=lambda v: (not v["installed"], v.get("variant") != "es-MX"))


def describe_models() -> list[dict]:
    downloads = ModelDownloadsRepo.get_all()
    out = []
    for model in all_models():
        installed = is_installed(model)
        files = model_files(model)
        out.append({
            **model,
            "installed": installed,
            "installed_files": sum(1 for f in files if f.exists()),
            "expected_files": len(files),
            "local_path": str(model_dir(model)),
            "download": downloads.get(model["id"]),
            "downloaded_size_mb": round(
                sum(f.stat().st_size for f in files if f.exists()) / (1024 ** 2), 1
            ) if installed else 0,
        })
    return out


def _repo_file_list(model: dict) -> list[str]:
    from huggingface_hub import HfApi

    api = HfApi()
    if "files" in model:
        return list(model["files"].keys())
    files = api.list_repo_files(model["repo_id"])
    patterns = model.get("allow_patterns") or ["*"]
    selected = []
    for name in files:
        if name.startswith("."):
            continue
        if any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
            selected.append(name)
    return selected


def _file_sizes(model: dict, filenames: list[str]) -> dict[str, int]:
    from huggingface_hub import HfApi

    sizes: dict[str, int] = {}
    try:
        info = HfApi().model_info(model["repo_id"], files_metadata=True)
        for sibling in info.siblings or []:
            if sibling.rfilename in filenames:
                sizes[sibling.rfilename] = int(getattr(sibling, "size", 0) or 0)
    except Exception:
        pass
    return sizes


def download_model(model_id: str, background: bool = True) -> dict:
    """Download one model. Only ever called from an explicit user action."""
    model = get_model(model_id)
    with _lock:
        thread = _download_threads.get(model_id)
        if thread and thread.is_alive():
            return {"status": "already_downloading", "model_id": model_id}
        if is_installed(model):
            return {"status": "installed", "model_id": model_id}

        def worker() -> None:
            try:
                _do_download(model)
                ModelDownloadsRepo.upsert(model_id, "completed", 1.0, "Modelo instalado", 0, 0)
            except Exception as exc:  # noqa: BLE001 - reported to the UI
                ModelDownloadsRepo.upsert(
                    model_id, "failed", 0.0,
                    f"Error de descarga: {exc}. Comprueba tu conexión y vuelve a intentarlo.",
                )

        thread = threading.Thread(target=worker, name=f"download-{model_id}", daemon=True)
        _download_threads[model_id] = thread
        ModelDownloadsRepo.upsert(model_id, "downloading", 0.0, "Preparando descarga…")
        thread.start()
    return {"status": "started", "model_id": model_id}


def _do_download(model: dict) -> None:
    from huggingface_hub import hf_hub_download

    destination = model_dir(model)
    destination.mkdir(parents=True, exist_ok=True)
    filenames = _repo_file_list(model)
    if not filenames:
        raise RuntimeError("El repositorio no contiene los archivos esperados.")
    sizes = _file_sizes(model, filenames)
    total = sum(sizes.values()) or 1
    done_bytes = 0

    for name in filenames:
        ModelDownloadsRepo.upsert(
            model["id"], "downloading", min(0.99, done_bytes / total),
            f"Descargando {Path(name).name}…", total, done_bytes,
        )
        path = hf_hub_download(model["repo_id"], name, local_dir=str(destination))
        target_name = model.get("files", {}).get(name)
        if target_name:
            target = destination / Path(target_name).name
            if Path(path).resolve() != target.resolve():
                shutil.copy2(path, target)
        done_bytes += sizes.get(name, Path(path).stat().st_size)
        ModelDownloadsRepo.upsert(
            model["id"], "downloading", min(0.99, done_bytes / total),
            f"{Path(name).name} listo", total, done_bytes,
        )
        time.sleep(0.01)

    if model.get("engine") == "piper":
        # Remove the nested HF layout, keep only the voice files + model card.
        for child in destination.iterdir():
            if child.is_dir() and child.name not in {".cache"}:
                shutil.rmtree(child, ignore_errors=True)
            elif child.name == ".cache":
                shutil.rmtree(child, ignore_errors=True)


def remove_model(model_id: str) -> None:
    model = get_model(model_id)
    with _lock:
        thread = _download_threads.get(model_id)
        if thread and thread.is_alive():
            raise ModelMissingError("El modelo se está descargando.",
                                    "Espera a que termine antes de eliminarlo.")
        directory = model_dir(model).resolve()
        root = config.models_dir.resolve()
        if root not in directory.parents:
            raise ModelMissingError("Ruta de modelo no permitida.", "Revisa el manifiesto.")
        if directory.exists():
            shutil.rmtree(directory)
        ModelDownloadsRepo.upsert(model_id, "not_installed", 0.0, "Modelo eliminado")
