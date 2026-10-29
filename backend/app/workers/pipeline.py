"""End-to-end dubbing pipeline.

Every stage persists its artifacts so an interrupted or failed job can resume
without redoing completed work. The pipeline never touches the uploaded file.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

import psutil

from app.core.config import config
from app.core.errors import AppError, CancelledError, MediaError, ResourceError
from app.database.repository import (
    STAGES,
    JobsRepo,
    SegmentsRepo,
    SettingsRepo,
    utcnow,
)
from app.services import (
    alignment,
    asr,
    ffmpeg,
    models_manager,
    mixing,
    separation,
    translation,
    tts,
)
from app.services import subtitles

STAGE_WEIGHTS = {
    "analysis": 2,
    "extraction": 5,
    "asr": 20,
    "translation": 12,
    "separation": 5,
    "tts": 32,
    "sync": 8,
    "mix": 4,
    "render": 12,
}


def _fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class JobContext:
    def __init__(self, job_id: str):
        job = JobsRepo.get(job_id)
        if not job:
            raise AppError("El trabajo no existe.", "Actualiza la lista de proyectos.")
        self.job_id = job_id
        self.job = job
        self.project = job["project"]
        self.settings = job["settings"] or {}
        self.resume = bool(self.settings.get("resume"))
        self.started = time.monotonic()
        self.warnings: list[str] = list(job.get("warnings") or [])
        self.stats: dict = dict(job.get("stats") or {})
        self.stage_frac: dict[str, float] = {s["stage"]: s["progress"] for s in job["stages"]}
        self.stage_status: dict[str, str] = {s["stage"]: s["status"] for s in job["stages"]}
        self.job_dir = config.projects_dir / self.project["id"] / f"job_{job_id}"
        self.job_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ utils
    def cancel_requested(self) -> bool:
        row = JobsRepo.get(self.job_id)
        return bool(row and row.get("cancel_requested"))

    def check_cancel(self) -> None:
        if self.cancel_requested():
            raise CancelledError("Trabajo cancelado por el usuario.")

    def log(self, message: str, level: str = "info") -> None:
        JobsRepo.add_event(self.job_id, message, level)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
        self.log(message, "warning")
        JobsRepo.update(self.job_id, warnings=self.warnings)

    def progress(self, stage: str, fraction: float, message: str | None = None) -> None:
        self.check_cancel()
        fraction = max(0.0, min(1.0, fraction))
        self.stage_frac[stage] = fraction
        done = 0.0
        for name, weight in STAGE_WEIGHTS.items():
            if name == stage:
                done += weight * fraction
                break
            done += weight
        JobsRepo.update(self.job_id, progress=round(min(99.0, done), 1),
                        stage=stage, message=message or job_stage_label(stage))
        JobsRepo.set_stage(self.job_id, stage, "running", fraction, message)

    def stage_start(self, stage: str, message: str) -> None:
        self.check_cancel()
        JobsRepo.set_stage(self.job_id, stage, "running", 0.0, message)
        JobsRepo.update(self.job_id, stage=stage, message=message)
        self.log(f"INICIO {job_stage_label(stage)}: {message}")

    def stage_done(self, stage: str, detail: str = "Completado", *, skipped: bool = False) -> None:
        JobsRepo.set_stage(self.job_id, stage, "skipped" if skipped else "completed", 1.0, detail)
        self.stage_frac[stage] = 1.0
        self.stage_status[stage] = "skipped" if skipped else "completed"
        JobsRepo.update(self.job_id, progress=round(min(99.0, self.global_progress()), 1))
        self.log(f"OK {job_stage_label(stage)}: {detail}")

    def global_progress(self) -> float:
        return sum(
            STAGE_WEIGHTS[name] * (1.0 if status in ("completed", "skipped") else self.stage_frac.get(name, 0))
            for name, status in self.stage_status.items()
            if name in STAGE_WEIGHTS
        )

    def path(self, *parts: str) -> Path:
        path = self.job_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_memory(self, required_mb: int, stage: str) -> None:
        available = psutil.virtual_memory().available / (1024 ** 2)
        deadline = time.monotonic() + 45
        while available < required_mb and time.monotonic() < deadline:
            self.log(
                f"Esperando memoria libre para {job_stage_label(stage)} "
                f"({available:.0f} MB disponibles, {required_mb} MB necesarios)…",
                "warning",
            )
            time.sleep(3)
            available = psutil.virtual_memory().available / (1024 ** 2)
        if available < required_mb:
            raise ResourceError(
                f"No hay suficiente memoria RAM para {job_stage_label(stage).lower()} "
                f"({required_mb} MB necesarios, {available:.0f} MB libres).",
                "Cierra otras aplicaciones, elige un modelo más ligero o reduce los hilos "
                "de CPU en Ajustes. El progreso anterior se conserva para reanudar.",
            )

    def write_json(self, name: str, data: dict | list) -> Path:
        path = self.path(name)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def read_json(self, name: str) -> dict | list | None:
        path = self.job_dir / name
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    @property
    def threads(self) -> int:
        configured = int(self.settings.get("threads") or SettingsRepo.all().get("cpu_threads") or 0)
        return configured if configured > 0 else max(1, min(4, (psutil.cpu_count(logical=False) or 2)))


def job_stage_label(stage: str) -> str:
    from app.database.repository import STAGE_LABELS

    return STAGE_LABELS.get(stage, stage)


class Pipeline:
    def __init__(self, ctx: JobContext):
        self.ctx = ctx
        self.duration = float(ctx.project.get("duration") or 0)
        self.segments: list[dict] = []

    # ------------------------------------------------------------------- run
    def run(self) -> dict:
        ctx = self.ctx
        ctx.check_cancel()
        ctx.ensure_memory(500, "analysis")
        self._validate_inputs()
        self._stage_analysis()
        self._stage_extraction()
        self._stage_asr()
        self._stage_translation()
        self._stage_separation()
        self._stage_tts()
        self._stage_sync()
        self._stage_mix()
        result = self._stage_render()
        return result

    # --------------------------------------------------------------- helpers
    def _validate_inputs(self) -> None:
        ctx = self.ctx
        if not ctx.project:
            raise MediaError("El proyecto no existe.", "Vuelve a subir el video.")
        source = Path(ctx.project["source_path"])
        if not source.exists():
            raise MediaError(
                "El archivo fuente ya no está disponible.",
                "El proyecto se movió o se eliminó. Vuelve a subir el video.",
            )
        if not ctx.project.get("has_audio"):
            raise MediaError(
                "El video no tiene pista de audio.",
                "Este sistema necesita diálogo audible. Sube un video con audio.",
            )
        free_gb = ffmpeg.available_disk_gb(config.data_dir)
        needed = max(0.5, self.duration / 3600 * 1.5)
        if free_gb < needed:
            raise ResourceError(
                f"Espacio insuficiente en disco ({free_gb:.1f} GB libres).",
                f"Libera al menos {needed:.1f} GB o cambia la carpeta de datos en Ajustes.",
            )

    def _stage_analysis(self) -> None:
        ctx = self.ctx
        if ctx.stage_status.get("analysis") == "completed" and (ctx.job_dir / "analysis.json").exists():
            ctx.stage_done("analysis", "Metadatos reutilizados", skipped=True)
            return
        ctx.stage_start("analysis", "Verificando pistas y duración")
        probe = ffmpeg.probe(ctx.project["source_path"])
        if not probe.get("has_audio"):
            raise MediaError("El video no contiene audio.", "Sube un video con diálogo.")
        if probe["duration"] > float(ctx.settings.get("max_duration_s") or config.max_duration_s):
            raise MediaError(
                f"El video dura {probe['duration'] / 60:.1f} min y supera el límite configurado.",
                "Acorta el video o aumenta el límite en Ajustes.",
            )
        ctx.write_json("analysis.json", probe)
        ctx.progress("analysis", 1.0, "Metadatos verificados")
        ctx.stage_done("analysis", f"{probe['width']}×{probe['height']} · {probe['duration']:.1f}s")
        self.probe = probe

    def _stage_extraction(self) -> None:
        ctx = self.ctx
        audio_full = ctx.job_dir / "audio" / "original.wav"
        audio_asr = ctx.job_dir / "audio" / "asr.wav"
        if audio_full.exists() and audio_asr.exists() and ctx.stage_status.get("extraction") == "completed":
            ctx.stage_done("extraction", "Audio ya extraído", skipped=True)
            return
        ctx.stage_start("extraction", "Extrayendo audio sin recodificar el video")
        audio_full.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.extract_audio(
            ctx.project["source_path"], str(audio_full), sample_rate=48000, channels=2,
            duration=self.duration,
            progress_cb=lambda p, m: ctx.progress("extraction", p * 0.6, m),
            cancel_check=ctx.check_cancel,
        )
        ffmpeg.extract_audio(
            ctx.project["source_path"], str(audio_asr), sample_rate=16000, channels=1,
            duration=self.duration,
            progress_cb=lambda p, m: ctx.progress("extraction", 0.6 + p * 0.4, m),
            cancel_check=ctx.check_cancel,
        )
        ctx.stage_done("extraction", f"Audio 48 kHz y 16 kHz listo ({_fmt_time(self.duration)})")

    def _stage_asr(self) -> None:
        ctx = self.ctx
        stored = SegmentsRepo.list(ctx.job_id)
        transcript = ctx.read_json("transcript.json")
        if stored and transcript and any(s.get("text_src") for s in stored):
            self.segments = stored
            info = transcript.get("info", {}) if isinstance(transcript, dict) else {}
            ctx.stats.update({
                "language": info.get("language"),
                "language_probability": info.get("language_probability"),
                "asr_model": info.get("model"),
                "asr_seconds": info.get("elapsed_s"),
            })
            ctx.stage_done("asr", f"{len(stored)} segmentos reutilizados", skipped=True)
            return

        preset = ctx.settings.get("preset", "balanced")
        requested = ctx.settings.get("asr_model", "auto")
        model = (models_manager.resolve_asr_model(preset) if requested in ("auto", None, "")
                 else models_manager.get_model(requested))
        if not models_manager.is_installed(model):
            raise MediaError(
                f"El modelo {model['name']} no está instalado.",
                "Abre «Modelos» para descargarlo o elige otro modelo en Ajustes.",
            )
        ctx.ensure_memory(int(model.get("ram_estimate_mb", 800)) + 500, "asr")
        ctx.stage_start("asr", f"Transcribiendo con {model['name']}")
        ctx.stats["asr_model"] = model["id"]
        device = ctx.settings.get("device", "auto")
        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        language = ctx.settings.get("source_language", "auto")

        result = asr.transcribe(
            str(ctx.job_dir / "audio" / "asr.wav"),
            model_dir=str(models_manager.model_dir(model)),
            model_name=model["id"],
            language=None if language in ("auto", None, "") else language,
            threads=ctx.threads, device=device, compute_type=compute,
            duration=self.duration,
            cancel_check=ctx.check_cancel,
            progress=lambda p, m: ctx.progress("asr", 0.05 + p * 0.95, m),
        )
        self.segments = [
            {"start": s["start"], "end": s["end"], "text_src": s["text"],
             "text_es": "", "status": "transcribed"}
            for s in result.segments
        ]
        SegmentsRepo.replace_all(ctx.job_id, self.segments)
        ctx.write_json("transcript.json", {
            "info": {
                "language": result.language,
                "language_probability": result.language_probability,
                "model": model["id"],
                "elapsed_s": result.elapsed_s,
                "requested_language": language,
            },
            "segments": result.segments,
        })
        ctx.stats.update({
            "language": result.language,
            "language_probability": result.language_probability,
            "asr_seconds": result.elapsed_s,
            "segments": len(result.segments),
        })
        if language in ("auto", None, "") and result.language_probability < 0.6:
            ctx.warn(
                f"Detección de idioma poco segura ({result.language}, "
                f"{result.language_probability:.0%}). Revisa la transcripción o elige el "
                "idioma de origen manualmente y reprocesa."
            )
        ctx.stage_done(
            "asr",
            f"{len(self.segments)} segmentos · idioma {result.language} "
            f"({result.language_probability:.0%}) · {result.elapsed_s:.0f}s",
        )
        asr.unload_all()

    def _stage_translation(self) -> None:
        ctx = self.ctx
        if not self.segments:
            self.segments = SegmentsRepo.list(ctx.job_id)
        if not self.segments:
            raise MediaError("No hay transcripción para traducir.",
                             "Vuelve a ejecutar el reconocimiento de voz.")
        existing = ctx.read_json("translation.json")
        if existing and all(s.get("text_es") for s in self.segments):
            ctx.stage_done("translation", f"{len(self.segments)} segmentos reutilizados", skipped=True)
            ctx.stats.setdefault("translation_model", existing.get("model") if isinstance(existing, dict) else None)
            return

        language = (ctx.settings.get("source_language") or "auto")
        if language in ("auto", None, ""):
            language = ctx.stats.get("language") or "en"
        requested_engine = ctx.settings.get("translation_engine", "auto")
        if requested_engine in ("auto", None, ""):
            try:
                model = models_manager.resolve_translation_model(language, ctx.settings.get("preset", "balanced"))
            except Exception:
                raise
            engine = model["engine"]
        else:
            engine = requested_engine
            candidates = [m for m in models_manager.all_models()
                          if m.get("stage") == "translation" and m.get("engine") == engine
                          and models_manager.is_installed(m)]
            if engine == "marian":
                candidates = [m for m in candidates if m.get("source_lang") == language] or candidates
            if not candidates:
                raise MediaError(
                    f"No hay un modelo {engine} instalado para {language}.",
                    "Abre «Modelos» y descarga el modelo adecuado, o usa «auto».",
                )
            model = candidates[0]

        ctx.ensure_memory(int(model.get("ram_estimate_mb", 1200)) + 400, "translation")
        ctx.stage_start("translation", f"Traduciendo {len(self.segments)} segmentos con {model['name']}")
        texts = [s.get("text_src", "") for s in self.segments]
        result = translation.translate(
            texts, engine=engine, model_dir=str(models_manager.model_dir(model)),
            threads=ctx.threads, quantize=bool(ctx.settings.get("quantize_translation")),
            source_lang=language, target_lang="es",
            cancel_check=ctx.check_cancel,
            progress=lambda p, m: ctx.progress("translation", p, m),
        )
        for seg, translated in zip(self.segments, result.texts):
            seg["text_es"] = translated
            seg["status"] = "translated"
        SegmentsRepo.replace_all(ctx.job_id, self.segments)
        ctx.write_json("translation.json", {
            "engine": result.engine, "model": result.model,
            "elapsed_s": result.elapsed_s, "source_language": language,
            "segments": self.segments,
        })
        ctx.stats.update({
            "translation_model": model["id"],
            "translation_engine": result.engine,
            "translation_seconds": result.elapsed_s,
        })
        ctx.stage_done("translation", f"{len(self.segments)} segmentos en {result.elapsed_s:.0f}s")
        translation.unload_all()

    def _stage_separation(self) -> None:
        ctx = self.ctx
        enabled = bool(ctx.settings.get("separation"))
        stems = ctx.job_dir / "stems" / "background.wav"
        if not enabled:
            ctx.stage_done("separation", "Desactivada; se usará atenuación del audio original",
                           skipped=True)
            return
        if stems.exists() and ctx.stage_status.get("separation") in ("completed", "skipped"):
            ctx.stage_done("separation", "Fondo separado reutilizado", skipped=True)
            return
        ctx.stage_start("separation", "Separando diálogo y fondo (opcional)")
        try:
            result = separation.separate(
                str(ctx.job_dir / "audio" / "original.wav"),
                str(ctx.job_dir / "stems"),
                method=ctx.settings.get("separation_method", "auto"),
                cancel_check=ctx.check_cancel,
                progress=lambda p, m: ctx.progress("separation", p, m),
            )
            ctx.warn(result["warning"])
            ctx.stats["separation_method"] = result["method"]
            ctx.stage_done("separation", f"Método: {result['method']}")
        except CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - optional stage must not kill the job
            ctx.warn(
                "No se pudo separar el fondo: se conservará el audio original atenuado. "
                f"Detalle: {getattr(exc, 'message', str(exc))}"
            )
            ctx.stage_done("separation", "Omitida por error; se usará audio original", skipped=True)

    def _stage_tts(self) -> None:
        ctx = self.ctx
        if not self.segments:
            self.segments = SegmentsRepo.list(ctx.job_id)
        if not self.segments:
            raise MediaError("No hay segmentos traducidos para generar voz.",
                             "Revisa la traducción antes de continuar.")
        voice_id = ctx.settings.get("voice") or "es_MX-ald-medium"
        model = models_manager.resolve_tts_model(voice_id)
        if model["voice"]["id"] != voice_id:
            ctx.warn(
                f"La voz «{voice_id}» no está instalada; se usará «{model['voice']['label']}»."
            )
        ctx.stage_start("tts", f"Generando voz con {model['voice']['label']}")
        tts_dir = ctx.job_dir / "tts"
        tts_dir.mkdir(parents=True, exist_ok=True)
        rate = float(ctx.settings.get("speech_rate") or 1.0)
        volume = float(ctx.settings.get("volume") or 1.0)
        total = len(self.segments)
        done = 0
        failures = 0
        for index, seg in enumerate(self.segments):
            ctx.check_cancel()
            text = (seg.get("text_es") or "").strip()
            if not text:
                ctx.warn(f"Segmento {index + 1} sin traducción; se omite en el doblaje.")
                SegmentsRepo.update(ctx.job_id, index, status="empty")
                done += 1
                continue
            key = hashlib.sha1(
                f"{text}|{model['voice']['id']}|{rate}|{volume}".encode("utf-8")
            ).hexdigest()[:10]
            target = tts_dir / f"{index:04d}_{key}.wav"
            if target.exists() and seg.get("tts_path") == str(target):
                seg["tts_duration"] = seg.get("tts_duration") or ffmpeg.wav_duration(str(target))
                done += 1
                continue
            try:
                result = tts.synthesize(
                    text, str(target), model=model, rate=rate, volume=volume,
                    cancel_check=ctx.check_cancel,
                )
            except CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                failures += 1
                ctx.warn(
                    f"No se pudo generar el segmento {index + 1}: "
                    f"{getattr(exc, 'message', str(exc))}"
                )
                SegmentsRepo.update(ctx.job_id, index, status="tts_error")
                done += 1
                continue
            seg["tts_path"] = result["path"]
            seg["tts_duration"] = result["duration"]
            seg["status"] = "voiced"
            if result["engine"] != "piper" and "sapi_fallback" not in ctx.stats:
                ctx.stats["sapi_fallback"] = True
                ctx.warn(
                    "Piper no está disponible: se usó la voz integrada de Windows (SAPI). "
                    "La pronunciación es inteligible pero menos natural. Ejecuta "
                    "scripts/setup.ps1 para habilitar Piper."
                )
            SegmentsRepo.update(
                ctx.job_id, index, tts_path=result["path"],
                tts_duration=result["duration"], status="voiced",
            )
            ctx.stats["tts_engine"] = result["engine"]
            done += 1
            ctx.progress("tts", done / total,
                         f"Generando voz {done}/{total} (segmento {index + 1})")
        if failures == total:
            raise MediaError(
                "No se pudo generar ninguna voz en español.",
                "Comprueba la instalación de Piper y la voz seleccionada. El texto y la "
                "traducción se conservan para reintentar.",
            )
        ctx.stats["tts_engine"] = ctx.stats.get("tts_engine") or "piper"
        ctx.stats["tts_voice"] = model["voice"]["id"]
        ctx.stage_done("tts", f"{total - failures}/{total} segmentos con voz")

    def _stage_sync(self) -> None:
        ctx = self.ctx
        if not self.segments:
            self.segments = SegmentsRepo.list(ctx.job_id)
        voiced = [s for s in self.segments if s.get("tts_path")]
        if not voiced:
            raise MediaError("No hay audio generado para sincronizar.",
                             "Vuelve a generar la voz.")
        ctx.stage_start("sync", "Ajustando velocidad y silencios")
        gap = alignment.clamp_gap(ctx.settings.get("gap_ms", 80))
        max_speedup = float(ctx.settings.get("max_speedup") or 1.18)
        result = alignment.build_dub(
            voiced, str(ctx.job_dir / "dub.wav"),
            total_duration=self.duration, gap_ms=gap, max_speedup=max_speedup,
            cancel_check=ctx.check_cancel,
            progress=lambda p, m: ctx.progress("sync", p, m),
        )
        for warning in result.warnings:
            ctx.warn(warning)
        for place in result.placements:
            SegmentsRepo.update(
                ctx.job_id, place["index"],
                status="overlong" if place["warning"] else "ready",
                warning=place["warning"],
            )
        ctx.write_json("sync.json", {
            "placements": result.placements, "warnings": result.warnings,
            "max_speed": result.max_speed, "gap_ms": gap, "max_speedup": max_speedup,
        })
        ctx.stats.update({
            "sync_max_speed": result.max_speed,
            "sync_overlong": result.overlong,
            "sync_trimmed": result.trimmed,
            "dub_duration": result.duration,
        })
        detail = f"{len(result.placements)} segmentos sincronizados"
        if result.overlong:
            detail += f" · {result.overlong} con advertencia de duración"
        ctx.stage_done("sync", detail)

    def _stage_mix(self) -> None:
        ctx = self.ctx
        mode = ctx.settings.get("mode", "dub_plus_background")
        dub = ctx.job_dir / "dub.wav"
        if not dub.exists():
            raise MediaError("No existe el audio doblado.", "Vuelve a sincronizar el audio.")
        background = None
        if mode != "dub_only":
            separated = ctx.job_dir / "stems" / "background.wav"
            if separated.exists():
                background = str(separated)
            else:
                background = str(ctx.job_dir / "audio" / "original.wav")
                if mode == "dub_plus_background":
                    ctx.warn(
                        "No se usó separación de fuentes: el doblaje se mezcla con el audio "
                        "original atenuado. La música y los efectos se conservan, pero también "
                        "puede oírse el diálogo original de fondo."
                    )
        ctx.stage_start("mix", f"Mezclando doblaje ({mixing.MODES.get(mode, mode)})")
        result = mixing.mix_audio(
            str(dub), str(ctx.job_dir / "mix.wav"),
            background_path=background, mode=mode,
            loudness_lufs=float(ctx.settings.get("loudness_lufs") or -16.0),
            ducking=bool(ctx.settings.get("ducking", True)),
            duration=self.duration, cancel_check=ctx.check_cancel,
        )
        ctx.stats.update({"mix_mode": mode, "mix_background": result["background"]})
        ctx.progress("mix", 1.0, "Mezcla lista")
        ctx.stage_done("mix", "Doblaje + fondo" if result["background"] else "Solo doblaje")

    def _stage_render(self) -> dict:
        ctx = self.ctx
        ctx.stage_start("render", "Combinando video original y audio doblado")
        output = ctx.job_dir / "output.mp4"
        mode = ctx.settings.get("mode", "dub_plus_background")
        result = mixing.render_video(
            ctx.project["source_path"], str(ctx.job_dir / "mix.wav"), str(output),
            mode=mode, duration=self.duration,
            audio_bitrate=ctx.settings.get("audio_bitrate", "192k"),
            include_original=mode == "dual", cancel_check=ctx.check_cancel,
            progress=lambda p, m: ctx.progress("render", p, m),
        )
        for warning in result.get("warnings", []):
            ctx.warn(warning)
        try:
            exports = config.exports_dir
            exports.mkdir(parents=True, exist_ok=True)
            slug = _slug(ctx.project["name"]) or "video"
            export_path = exports / f"{slug}_es_{ctx.job_id[:8]}.mp4"
            shutil.copy2(output, export_path)
            ctx.stats["export_path"] = str(export_path)
        except OSError as exc:
            ctx.warn(f"No se pudo copiar el archivo a la carpeta de exportaciones: {exc}")

        subtitles_dir = ctx.job_dir / "subtitles"
        subtitles_dir.mkdir(exist_ok=True)
        segments = SegmentsRepo.list(ctx.job_id)
        (subtitles_dir / "es.srt").write_text(subtitles.to_srt(segments), encoding="utf-8")
        (subtitles_dir / "es.vtt").write_text(subtitles.to_vtt(segments), encoding="utf-8")
        (ctx.job_dir / "transcript.txt").write_text(
            subtitles.to_transcript(segments), encoding="utf-8"
        )

        ctx.stats.update({
            "output_size_bytes": result["size_bytes"],
            "output_duration": result["duration"],
            "output_width": result["width"],
            "output_height": result["height"],
            "output_fps": result["fps"],
            "output_video_codec": result["video_codec"],
            "output_audio_codec": result["audio_codec"],
            "elapsed_s": round(time.monotonic() - ctx.started, 1),
        })
        ctx.stage_done("render", f"MP4 listo · {result['size_bytes'] / 1024 / 1024:.1f} MB")
        JobsRepo.update(
            ctx.job_id, output_path=str(output), stats=ctx.stats,
            warnings=ctx.warnings, progress=100,
        )
        return result

    # -------------------------------------------------------------- cleanup
    def cleanup(self) -> None:
        ctx = self.ctx
        if ctx.settings.get("keep_temp"):
            return
        for folder in ("audio/asr.wav", "mix.wav"):
            try:
                (ctx.job_dir / folder).unlink(missing_ok=True)
            except OSError:
                pass


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _slug(name: str) -> str:
    import re

    value = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", value)[:60]


def check_resources() -> list[str]:
    messages = []
    mem = psutil.virtual_memory()
    if mem.available / (1024 ** 3) < 1.5:
        messages.append("Poca memoria RAM disponible; cierra otras aplicaciones antes de procesar.")
    if ffmpeg.available_disk_gb(config.data_dir) < 2:
        messages.append("Queda poco espacio en disco para audio temporal y exportaciones.")
    return messages
