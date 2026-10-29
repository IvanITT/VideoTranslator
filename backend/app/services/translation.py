"""Local translation adapters (MarianMT and NLLB-200).

All models are loaded from disk (``local_files_only=True``); no remote
inference endpoint is ever contacted. Adapters share :class:`BaseTranslator`.
"""
from __future__ import annotations

import gc
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from app.core.errors import AppError, ModelMissingError

CancelCheck = Callable[[], bool]
ProgressCb = Callable[[float, str], None]

NLLB_LANG_CODES = {
    "en": "eng_Latn", "es": "spa_Latn", "fr": "fra_Latn", "de": "deu_Latn",
    "pt": "por_Latn", "it": "ita_Latn", "ja": "jpn_Jpan", "ko": "kor_Hang",
    "zh": "zho_Hans", "ru": "rus_Cyrl", "ar": "arb_Arab", "hi": "hin_Deva",
    "nl": "nld_Latn", "pl": "pol_Latn", "tr": "tur_Latn", "sv": "swe_Latn",
    "uk": "ukr_Cyrl", "id": "ind_Latn",
}

_cache: dict[tuple, "BaseTranslator"] = {}
_lock = threading.Lock()


class TranslationError(AppError):
    code = "translation_error"
    status_code = 500


@dataclass
class TranslationResult:
    texts: list[str]
    engine: str
    model: str
    elapsed_s: float


class BaseTranslator:
    engine = "base"

    def __init__(self, model_dir: str, threads: int = 2, quantize: bool = False):
        self.model_dir = str(model_dir)
        self.threads = max(1, int(threads))
        self.quantize = quantize
        self.name = Path(self.model_dir).name

    def translate_batch(self, texts: list[str]) -> list[str]:  # pragma: no cover - abstract
        raise NotImplementedError

    def translate_many(self, texts: list[str], *, batch_size: int = 8,
                       cancel_check: CancelCheck | None = None,
                       progress: ProgressCb | None = None) -> list[str]:
        results: list[str] = []
        total = max(1, len(texts))
        for start in range(0, len(texts), batch_size):
            if cancel_check and cancel_check():
                from app.core.errors import CancelledError

                raise CancelledError("Trabajo cancelado durante la traducción.")
            chunk = texts[start:start + batch_size]
            translated = self.translate_batch(chunk)
            if len(translated) != len(chunk):
                raise TranslationError(
                    "El motor de traducción devolvió un número inesperado de segmentos.",
                    "Reintenta la traducción o cambia el modelo en Ajustes.",
                )
            results.extend(translated)
            if progress:
                progress(min(0.99, (start + len(chunk)) / total), "Traduciendo al español")
        if progress:
            progress(1.0, "Traducción completada")
        return results


class MarianTranslator(BaseTranslator):
    engine = "marian"

    def __init__(self, model_dir: str, threads: int = 2, quantize: bool = False):
        super().__init__(model_dir, threads, quantize)
        try:
            import torch
            from transformers import MarianMTModel, MarianTokenizer
        except ImportError as exc:  # pragma: no cover
            raise TranslationError("Faltan dependencias de traducción.",
                                   "Ejecuta scripts/setup.ps1 para instalar todo.") from exc

        if not (Path(model_dir) / "pytorch_model.bin").exists():
            raise ModelMissingError(
                "El modelo de traducción MarianMT no está instalado.",
                "Abre «Modelos» y descarga el modelo English → Spanish.",
            )
        torch.set_num_threads(self.threads)
        self._torch = torch
        try:
            self.tokenizer = MarianTokenizer.from_pretrained(model_dir, local_files_only=True)
            self.model = MarianMTModel.from_pretrained(model_dir, local_files_only=True)
            self.model.eval()
            if quantize:
                self.model = torch.quantization.quantize_dynamic(
                    self.model, {torch.nn.Linear}, dtype=torch.qint8
                )
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(
                "No se pudo cargar el modelo MarianMT.",
                f"Verifica los archivos del modelo y la RAM disponible. Detalle: {exc}",
            ) from exc

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        cleaned = [normalize_text(t) for t in texts]
        try:
            batch = self.tokenizer(cleaned, return_tensors="pt", padding=True,
                                   truncation=True, max_length=512)
            with self._torch.no_grad():
                output = self.model.generate(
                    **batch,
                    max_new_tokens=min(512, max(48, max(len(t) for t in cleaned) * 3)),
                    num_beams=4,
                    length_penalty=1.0,
                    no_repeat_ngram_size=3,
                )
            decoded = self.tokenizer.batch_decode(output, skip_special_tokens=True)
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(
                "Falló la traducción de un segmento.",
                f"Revisa el texto original o divide las frases muy largas. Detalle: {exc}",
            ) from exc
        return [postprocess(d) for d in decoded]


class NLLBTranslator(BaseTranslator):
    engine = "nllb"

    def __init__(self, model_dir: str, threads: int = 2, quantize: bool = False,
                 source_lang: str = "en", target_lang: str = "es"):
        super().__init__(model_dir, threads, quantize)
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise TranslationError("Faltan dependencias de traducción.",
                                   "Ejecuta scripts/setup.ps1 para instalar todo.") from exc

        if not (Path(model_dir) / "pytorch_model.bin").exists():
            raise ModelMissingError(
                "El modelo NLLB-200 no está instalado.",
                "Abre «Modelos» y descarga NLLB-200 Distilled 600M (≈2.5 GB).",
            )
        torch.set_num_threads(self.threads)
        self._torch = torch
        self.source_lang = source_lang
        self.target_lang = target_lang
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_dir, local_files_only=True)
            self.model.eval()
            if quantize:
                self.model = torch.quantization.quantize_dynamic(
                    self.model, {torch.nn.Linear}, dtype=torch.qint8
                )
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(
                "No se pudo cargar el modelo NLLB-200.",
                f"Necesita ~3 GB de RAM libre. Detalle: {exc}",
            ) from exc

    def _lang_id(self, code: str) -> int:
        return self.tokenizer.convert_tokens_to_ids(NLLB_LANG_CODES.get(code, "eng_Latn"))

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        cleaned = [normalize_text(t) for t in texts]
        try:
            self.tokenizer.src_lang = NLLB_LANG_CODES.get(self.source_lang, "eng_Latn")
            batch = self.tokenizer(cleaned, return_tensors="pt", padding=True,
                                   truncation=True, max_length=512)
            with self._torch.no_grad():
                output = self.model.generate(
                    **batch,
                    forced_bos_token_id=self._lang_id(self.target_lang),
                    max_new_tokens=min(512, max(48, max(len(t) for t in cleaned) * 3)),
                    num_beams=3,
                )
            decoded = self.tokenizer.batch_decode(output, skip_special_tokens=True)
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(
                "Falló la traducción con NLLB-200.",
                f"Comprueba la RAM disponible o usa MarianMT. Detalle: {exc}",
            ) from exc
        return [postprocess(d) for d in decoded]


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # Whisper occasionally leaves musical annotations; they cannot be dubbed.
    text = re.sub(r"[\[\(](música|music|aplausos|applause|risas|laughter)[\]\)]",
                  "", text, flags=re.IGNORECASE).strip()
    return text or "…"


def postprocess(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^[-–—]\s*", "", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def shorten_for_fit(text: str, max_chars: int) -> str:
    """Conservative, meaning-preserving trim of Spanish fillers only."""
    if len(text) <= max_chars:
        return text
    fillers = [
        r"\bbueno\b", r"\bpues\b", r"\beh\b", r"\beste\b", r"\bo sea\b",
        r"\bla verdad\b", r"\bde hecho\b", r"\bsimplemente\b", r"\brealmente\b",
    ]
    reduced = text
    for filler in fillers:
        if len(reduced) <= max_chars:
            break
        reduced = re.sub(filler + r"[,]?\s*", "", reduced, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", reduced).strip() or text


def get_translator(engine: str, model_dir: str, *, threads: int = 2,
                   quantize: bool = False, source_lang: str = "en",
                   target_lang: str = "es") -> BaseTranslator:
    key = (engine, str(Path(model_dir).resolve()), threads, quantize, source_lang, target_lang)
    with _lock:
        translator = _cache.get(key)
        if translator is None:
            if engine == "nllb":
                translator = NLLBTranslator(model_dir, threads, quantize,
                                            source_lang=source_lang, target_lang=target_lang)
            else:
                translator = MarianTranslator(model_dir, threads, quantize)
            _cache[key] = translator
        return translator


def translate(texts: list[str], *, engine: str, model_dir: str, threads: int = 2,
              quantize: bool = False, source_lang: str = "en", target_lang: str = "es",
              batch_size: int = 8, cancel_check: CancelCheck | None = None,
              progress: ProgressCb | None = None) -> TranslationResult:
    started = time.monotonic()
    translator = get_translator(engine, model_dir, threads=threads, quantize=quantize,
                                source_lang=source_lang, target_lang=target_lang)
    texts_out = translator.translate_many(texts, batch_size=batch_size,
                                          cancel_check=cancel_check, progress=progress)
    return TranslationResult(
        texts=texts_out, engine=engine, model=translator.name,
        elapsed_s=round(time.monotonic() - started, 1),
    )


def unload_all() -> None:
    with _lock:
        _cache.clear()
    gc.collect()
