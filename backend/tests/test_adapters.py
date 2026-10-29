"""ASR, translation, TTS and model-manager adapters (heavy models are mocked)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import CancelledError, MediaError, ModelMissingError
from app.services import asr, models_manager, translation, tts
from app.services.translation import (BaseTranslator, TranslationError,
                                      normalize_text, postprocess,
                                      shorten_for_fit)


# ------------------------------------------------------------------------ ASR
class FakeWhisperModel:
    def __init__(self, segments, language="en", probability=0.98):
        self.segments = segments
        self.language = language
        self.probability = probability

    def transcribe(self, path, **kwargs):
        info = SimpleNamespace(language=self.language,
                               language_probability=self.probability)
        return iter(self.segments), info


def fake_segment(start, end, text):
    return SimpleNamespace(start=start, end=end, text=text)


def test_transcribe_normalizes_whisper_output(monkeypatch):
    fake = FakeWhisperModel([
        fake_segment(0.0, 1.2, " Hello there. "),
        fake_segment(1.3, 2.4, "This is a test."),
    ])
    monkeypatch.setattr(asr, "load_model", lambda *a, **k: fake)
    progress: list[float] = []
    result = asr.transcribe(
        "audio.wav", model_dir="ignored", language="en", duration=3.0,
        progress=lambda value, label: progress.append(value),
    )
    assert result.language == "en"
    assert result.language_probability == 0.98
    assert [s["text"] for s in result.segments] == ["Hello there.", "This is a test."]
    assert result.segments[0]["start"] == 0.0
    assert result.segments[-1]["end"] <= 3.0
    assert progress and progress[-1] == 1.0
    assert result.elapsed_s >= 0


def test_transcribe_detects_language(monkeypatch):
    fake = FakeWhisperModel([fake_segment(0.0, 0.5, "Bonjour")], language="fr")
    monkeypatch.setattr(asr, "load_model", lambda *a, **k: fake)
    result = asr.transcribe("audio.wav", model_dir="ignored", duration=1.0)
    assert result.language == "fr"


def test_transcribe_cancellation(monkeypatch):
    fake = FakeWhisperModel([fake_segment(0.0, 1.0, "one"),
                             fake_segment(1.0, 2.0, "two")])
    monkeypatch.setattr(asr, "load_model", lambda *a, **k: fake)
    with pytest.raises(CancelledError):
        asr.transcribe("audio.wav", model_dir="ignored", duration=2.0,
                       cancel_check=lambda: True)


def test_transcribe_without_speech_raises(monkeypatch):
    fake = FakeWhisperModel([])
    monkeypatch.setattr(asr, "load_model", lambda *a, **k: fake)
    with pytest.raises(MediaError):
        asr.transcribe("audio.wav", model_dir="ignored", duration=2.0)


def test_transcribe_wraps_model_failures(monkeypatch):
    class Broken:
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(asr, "load_model", lambda *a, **k: Broken())
    with pytest.raises(asr.ASRError):
        asr.transcribe("audio.wav", model_dir="ignored", duration=2.0)


def test_merge_and_split_sorts_and_clamps():
    raw = [
        {"start": 2.0, "end": 3.0, "text": "second"},
        {"start": 0.0, "end": 1.0, "text": "first"},
        {"start": 0.5, "end": 0.7, "text": ""},
    ]
    merged = asr.merge_and_split(raw, total_duration=5.0)
    assert [s["text"] for s in merged] == ["first", "second"]
    clamped = asr.merge_and_split([{"start": 4.5, "end": 9.0, "text": "tail"}], 5.0)
    assert clamped[0]["end"] == 5.0


def test_merge_and_split_merges_overlaps():
    raw = [
        {"start": 0.0, "end": 2.0, "text": "hello"},
        {"start": 1.0, "end": 3.0, "text": "world"},
    ]
    merged = asr.merge_and_split(raw, 4.0)
    assert len(merged) == 1
    assert merged[0]["text"] == "hello world"
    assert merged[0]["end"] == 3.0


def test_merge_and_split_splits_long_segments():
    words = " ".join(f"word{i}" for i in range(20))
    raw = [{"start": 0.0, "end": 30.0, "text": words}]
    parts = asr.merge_and_split(raw, 30.0, max_len=14.0)
    assert len(parts) == 2
    assert parts[0]["start"] == 0.0
    assert parts[-1]["end"] == 30.0
    assert all(part["text"] for part in parts)


# ----------------------------------------------------------------- translation
class FakeTranslator(BaseTranslator):
    engine = "fake"

    def translate_batch(self, texts):
        return [f"ES:{text}" for text in texts]


class BrokenCountTranslator(BaseTranslator):
    engine = "fake"

    def translate_batch(self, texts):
        return ["only-one"]


def test_translate_uses_adapter(monkeypatch):
    fake = FakeTranslator("fake-dir")
    monkeypatch.setattr(translation, "get_translator", lambda *a, **k: fake)
    progress: list[float] = []
    result = translation.translate(
        ["hello", "world"], engine="marian", model_dir="fake-dir",
        progress=lambda value, label: progress.append(value),
    )
    assert result.texts == ["ES:hello", "ES:world"]
    assert result.engine == "marian"
    assert result.model == "fake-dir"
    assert progress[-1] == 1.0


def test_translate_batches_and_cancels(monkeypatch):
    fake = FakeTranslator("fake-dir")
    monkeypatch.setattr(translation, "get_translator", lambda *a, **k: fake)
    with pytest.raises(CancelledError):
        translation.translate(["a", "b", "c"], engine="marian",
                              model_dir="fake-dir", batch_size=1,
                              cancel_check=lambda: True)


def test_translate_validates_result_count(monkeypatch):
    monkeypatch.setattr(translation, "get_translator",
                        lambda *a, **k: BrokenCountTranslator("fake-dir"))
    with pytest.raises(TranslationError):
        translation.translate(["a", "b"], engine="marian", model_dir="fake-dir")


def test_translation_text_helpers():
    assert normalize_text("  hola   mundo  ") == "hola mundo"
    assert normalize_text("[Música] hola") == "hola"
    assert normalize_text("") == "…"
    assert postprocess("- hola , mundo") == "Hola, mundo"
    assert postprocess("YA MAYÚSCULAS") == "YA MAYÚSCULAS"
    long = "Bueno, pues la verdad es que simplemente quería contarte una historia"
    shortened = shorten_for_fit(long, 40)
    assert len(shortened) <= len(long)
    assert "Bueno" not in shortened or len(shortened) <= 40
    assert shorten_for_fit("corto", 40) == "corto"


def test_missing_translation_model_is_reported(tmp_path):
    with pytest.raises(ModelMissingError):
        translation.MarianTranslator(str(tmp_path / "empty"), threads=1)


# ------------------------------------------------------------------------- TTS
def test_tts_text_cleaning():
    assert tts.clean_text("[risas] Hola *amigo*  https://x.test") == "Hola amigo"
    assert tts.clean_text("   ") == ""
    assert tts.clean_text("(aparte) Texto_normal") == "Textonormal"  # markdown chars stripped


def test_tts_rejects_empty_text(tmp_path):
    with pytest.raises(Exception) as excinfo:
        tts.synthesize("   ", str(tmp_path / "out.wav"),
                       model={"engine": "piper", "local_dir": "missing"})
    assert "texto" in str(excinfo.value).lower()


# --------------------------------------------------------------- model manager
def test_manifest_is_well_formed():
    models = models_manager.all_models()
    assert len(models) >= 8
    ids = [m["id"] for m in models]
    assert len(ids) == len(set(ids))
    for model in models:
        assert model["stage"] in ("asr", "translation", "tts")
        assert model["license"]
        assert model["license_url"].startswith("https://")
        assert isinstance(model["commercial_use"], bool)
        assert model["local_dir"]


def test_installed_models_are_detected():
    models = models_manager.all_models()
    for model in models:
        installed = models_manager.is_installed(model)
        assert isinstance(installed, bool)
    assert models_manager.installed_models()


def test_resolvers_pick_installed_models():
    asr_model = models_manager.resolve_asr_model("low")
    assert asr_model["stage"] == "asr"
    assert models_manager.is_installed(asr_model)

    translation_model = models_manager.resolve_translation_model("en", "balanced")
    assert translation_model["stage"] == "translation"

    voice = models_manager.resolve_tts_model("es_MX-ald-medium")
    assert voice["stage"] == "tts"
    assert models_manager.find_by_voice("does-not-exist") is None


def test_voice_choices_prioritize_installed_voices():
    choices = models_manager.voice_choices()
    assert choices
    assert choices[0]["installed"] is True
    assert all("model_id" in voice and "license" in voice for voice in choices)


def test_describe_models_reports_install_state():
    described = models_manager.describe_models()
    assert described
    for model in described:
        assert "installed" in model
        assert model["expected_files"] >= 0
        assert model["installed_files"] <= model["expected_files"] or not model["expected_files"]
