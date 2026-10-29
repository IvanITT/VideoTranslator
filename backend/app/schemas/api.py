"""Pydantic request/response models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

LANGUAGES = {
    "auto": "Detectar automáticamente",
    "en": "Inglés", "fr": "Francés", "de": "Alemán", "pt": "Portugués",
    "it": "Italiano", "ja": "Japonés", "ko": "Coreano", "zh": "Chino",
    "ru": "Ruso", "ar": "Árabe", "hi": "Hindi", "nl": "Neerlandés",
    "pl": "Polaco", "tr": "Turco", "sv": "Sueco", "uk": "Ucraniano",
    "id": "Indonesio", "es": "Español",
}

TARGET_VARIANTS = {
    "es-MX": "Español (México)",
    "es-ES": "Español (España)",
    "es-001": "Español neutro (Latinoamérica)",
}

MODES = {
    "dub_plus_background": "Doblaje + fondo (separa la voz original)",
    "replace_dialogue": "Reemplazar diálogo (audio original atenuado)",
    "dub_only": "Solo doblaje en español",
    "dual": "Doblaje + audio original (dos pistas)",
}

PRESETS = {
    "low": "Bajo consumo",
    "balanced": "Equilibrado",
    "high": "Alta calidad",
}


class JobSettings(BaseModel):
    source_language: str = "auto"
    target_language: Literal["es"] = "es"
    target_variant: str = "es-MX"
    voice: str = "es_MX-ald-medium"
    mode: str = "dub_plus_background"
    preset: str = "balanced"
    separation: bool = False
    separation_method: str = "auto"
    asr_model: str = "auto"
    translation_engine: str = "auto"
    speech_rate: float = 1.0
    volume: float = 1.0
    max_speedup: float = 1.18
    gap_ms: int = 80
    loudness_lufs: float = -16.0
    ducking: bool = True
    keep_temp: bool = False
    threads: int = 0
    device: str = "auto"
    compute_type: str = "int8"
    quantize_translation: bool = False
    max_duration_s: int = 3600
    audio_bitrate: str = "192k"
    resume: bool = False

    @field_validator("source_language")
    @classmethod
    def _lang(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError("Idioma de origen no soportado.")
        return value

    @field_validator("target_variant")
    @classmethod
    def _variant(cls, value: str) -> str:
        if value not in TARGET_VARIANTS:
            raise ValueError("Variante de español no soportada.")
        return value

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        if value not in MODES:
            raise ValueError("Modo de audio no válido.")
        return value

    @field_validator("preset")
    @classmethod
    def _preset(cls, value: str) -> str:
        if value not in PRESETS:
            raise ValueError("Perfil no válido.")
        return value

    @field_validator("device")
    @classmethod
    def _device(cls, value: str) -> str:
        if value not in ("auto", "cpu", "cuda"):
            raise ValueError("Dispositivo no válido.")
        return value

    @field_validator("speech_rate")
    @classmethod
    def _rate(cls, value: float) -> float:
        return float(min(1.8, max(0.6, value)))

    @field_validator("volume")
    @classmethod
    def _volume(cls, value: float) -> float:
        return float(min(2.0, max(0.0, value)))

    @field_validator("max_speedup")
    @classmethod
    def _speed(cls, value: float) -> float:
        return float(min(1.6, max(1.0, value)))

    @field_validator("gap_ms")
    @classmethod
    def _gap(cls, value: int) -> int:
        return int(min(1000, max(0, value)))

    @field_validator("loudness_lufs")
    @classmethod
    def _loud(cls, value: float) -> float:
        return float(min(-6.0, max(-30.0, value)))

    @field_validator("threads")
    @classmethod
    def _threads(cls, value: int) -> int:
        return int(min(32, max(0, value)))

    @field_validator("audio_bitrate")
    @classmethod
    def _bitrate(cls, value: str) -> str:
        if value not in ("128k", "160k", "192k", "256k", "320k"):
            return "192k"
        return value


class SettingsUpdate(BaseModel):
    cpu_threads: int | None = None
    preset: str | None = None
    asr_model: str | None = None
    translation_engine: str | None = None
    voice: str | None = None
    target_variant: str | None = None
    source_language: str | None = None
    mode: str | None = None
    separation: bool | None = None
    keep_temp: bool | None = None
    max_upload_mb: int | None = Field(default=None, ge=16, le=10240)
    max_duration_s: int | None = Field(default=None, ge=10, le=21600)
    speech_rate: float | None = Field(default=None, ge=0.6, le=1.8)
    volume: float | None = Field(default=None, ge=0.0, le=2.0)
    max_speedup: float | None = Field(default=None, ge=1.0, le=1.6)
    gap_ms: int | None = Field(default=None, ge=0, le=1000)
    loudness_lufs: float | None = Field(default=None, ge=-30, le=-6)
    ducking: bool | None = None
    parallel_jobs: int | None = Field(default=None, ge=1, le=1)
    device: str | None = None
    compute_type: str | None = None
    cleanup_days: int | None = Field(default=None, ge=1, le=365)
    quantize_translation: bool | None = None


class SegmentUpdate(BaseModel):
    text_es: str | None = Field(default=None, max_length=4000)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)


class SegmentRegenerate(BaseModel):
    text_es: str | None = Field(default=None, max_length=4000)


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)
