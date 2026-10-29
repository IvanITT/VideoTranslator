import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  FolderCog,
  Gauge,
  HardDrive,
  Info,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Volume2,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import { useModels, useSettingsData, useSystem } from "../hooks/useApi";
import { useToast } from "../components/Toast";
import {
  Badge,
  Button,
  Card,
  Field,
  SectionHeading,
  Select,
  Slider,
  Spinner,
  Toggle,
} from "../components/ui";

type Value = string | number | boolean;
type Values = Record<string, Value>;

const EDITABLE = [
  "preset", "cpu_threads", "device", "compute_type", "quantize_translation",
  "source_language", "target_variant", "voice", "mode", "separation", "keep_temp",
  "speech_rate", "volume", "max_speedup", "gap_ms", "loudness_lufs", "ducking",
  "max_upload_mb", "max_duration_s", "cleanup_days",
];

export function SettingsPage() {
  const settingsQ = useSettingsData();
  const modelsQ = useModels();
  const system = useSystem();
  const toast = useToast();
  const [values, setValues] = useState<Values>({});
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  useEffect(() => {
    if (settingsQ.data && !dirty) {
      setValues({ ...settingsQ.data.settings });
    }
  }, [settingsQ.data, dirty]);

  const set = (key: string, value: Value) => {
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload: Record<string, Value> = {};
      for (const key of EDITABLE) {
        if (values[key] !== undefined) payload[key] = values[key];
      }
      await api.updateSettings(payload);
      setDirty(false);
      settingsQ.refresh();
      toast.push("Ajustes guardados", "Se aplicarán a los próximos trabajos.", "success");
    } catch (error) {
      toast.push("No se pudieron guardar", (error as ApiError).message, "error");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    if (!settingsQ.data) return;
    setValues({ ...settingsQ.data.defaults });
    setDirty(true);
  };

  const applyRecommendation = () => {
    const recommendation = settingsQ.data?.recommendation as
      | { profile?: string; asr_model?: string; voice?: string; separation?: boolean }
      | undefined;
    if (!recommendation) return;
    setValues((current) => ({
      ...current,
      preset: recommendation.profile ?? current.preset,
      voice: recommendation.voice ?? current.voice,
      separation: Boolean(recommendation.separation),
    }));
    setDirty(true);
    toast.push("Recomendación aplicada", "Pulsa «Guardar cambios» para conservarla.", "info");
  };

  const cleanup = async () => {
    setCleaning(true);
    try {
      const result = await api.cleanup(Number(values.cleanup_days ?? 7));
      toast.push("Limpieza completada", `${result.removed} archivos eliminados · ${result.freed_mb} MB liberados.`, "success");
    } catch (error) {
      toast.push("No se pudo limpiar", (error as ApiError).message, "error");
    } finally {
      setCleaning(false);
    }
  };

  if (settingsQ.loading && !settingsQ.data) {
    return <Card><Spinner label="Cargando ajustes…" /></Card>;
  }
  if (!settingsQ.data) {
    return (
      <Card className="p-5">
        <p className="text-sm text-red-200">
          No se pudieron cargar los ajustes. {(settingsQ.error as Error)?.message}
        </p>
      </Card>
    );
  }

  const voices = settingsQ.data.voices.filter((voice) => voice.installed);
  const installedAsr = (modelsQ.data?.models ?? []).filter((m) => m.stage === "asr" && m.installed);
  const installedTranslation = (modelsQ.data?.models ?? []).filter((m) => m.stage === "translation" && m.installed);
  const gpu = system.data?.hardware.gpu;

  return (
    <div className="space-y-7">
      <SectionHeading
        eyebrow="Configuración"
        title="Ajustes del estudio"
        description="Valores por defecto para nuevos doblajes. Los trabajos existentes conservan su configuración."
        action={
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={reset}>Restaurar</Button>
            <Button variant="primary" size="sm" onClick={save} loading={saving} disabled={!dirty}>
              <Save size={14} /> Guardar cambios
            </Button>
          </div>
        }
      />

      <div className="grid gap-5 xl:grid-cols-2">
        <Card className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <Gauge size={15} className="text-amber-400" />
            <h3 className="text-sm font-medium text-slate-100">Rendimiento</h3>
          </div>
          <div className="space-y-4">
            <Field label="Perfil por defecto">
              <Select value={String(values.preset ?? "balanced")} onChange={(event) => set("preset", event.target.value)}>
                <option value="low">Bajo consumo · Whisper Tiny</option>
                <option value="balanced">Equilibrado · Whisper Base</option>
                <option value="high">Alta calidad · Whisper Small</option>
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Hilos de CPU" hint="0 = automático (núcleos físicos, máx. 4).">
                <input
                  type="number"
                  min={0}
                  max={32}
                  className="input"
                  value={Number(values.cpu_threads ?? 0)}
                  onChange={(event) => set("cpu_threads", Number(event.target.value))}
                />
              </Field>
              <Field label="Dispositivo" hint={gpu?.available ? `GPU: ${gpu.name}` : "No se detectó CUDA; CPU es la opción segura."}>
                <Select value={String(values.device ?? "auto")} onChange={(event) => set("device", event.target.value)}>
                  <option value="auto">Automático</option>
                  <option value="cpu">CPU</option>
                  <option value="cuda" disabled={!gpu?.available}>CUDA (GPU)</option>
                </Select>
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Modelo de reconocimiento">
                <Select value={String(values.asr_model ?? "auto")} onChange={(event) => set("asr_model", event.target.value)}>
                  <option value="auto">Automático según perfil</option>
                  {installedAsr.map((model) => (
                    <option key={model.id} value={model.id}>{model.name}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Motor de traducción">
                <Select value={String(values.translation_engine ?? "auto")} onChange={(event) => set("translation_engine", event.target.value)}>
                  <option value="auto">Automático (Marian, luego NLLB)</option>
                  <option value="marian">MarianMT</option>
                  <option value="nllb">NLLB-200</option>
                </Select>
              </Field>
            </div>
            <Toggle
              checked={Boolean(values.quantize_translation)}
              onChange={(value) => set("quantize_translation", value)}
              label="Cuantización INT8 de la traducción"
              description="Menos RAM y algo más de velocidad; puede reducir ligeramente la calidad."
            />
            <div className="flex items-start gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
              <Info size={13} className="mt-0.5 shrink-0 text-sky-400/70" />
              <p className="text-[11px] leading-relaxed text-slate-500">
                Solo se ejecuta un trabajo a la vez para no agotar la RAM. ASR, traducción y
                voz se cargan por etapas y se liberan al terminar.
              </p>
            </div>
            <Button variant="secondary" size="sm" onClick={applyRecommendation}>
              <Sparkles size={13} /> Aplicar recomendación del equipo
            </Button>
          </div>
        </Card>

        <Card className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <Volume2 size={15} className="text-emerald-400" />
            <h3 className="text-sm font-medium text-slate-100">Voz y audio</h3>
          </div>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Voz por defecto">
                <Select value={String(values.voice ?? "")} onChange={(event) => set("voice", event.target.value)}>
                  {voices.map((voice) => (
                    <option key={voice.id} value={voice.id}>{voice.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Variante de español">
                <Select value={String(values.target_variant ?? "es-MX")} onChange={(event) => set("target_variant", event.target.value)}>
                  <option value="es-MX">Español (México)</option>
                  <option value="es-ES">Español (España)</option>
                  <option value="es-001">Español neutro</option>
                </Select>
              </Field>
            </div>
            <Field label="Modo de audio por defecto">
              <Select value={String(values.mode ?? "dub_plus_background")} onChange={(event) => set("mode", event.target.value)}>
                <option value="dub_plus_background">Doblaje + fondo</option>
                <option value="replace_dialogue">Reemplazar diálogo</option>
                <option value="dub_only">Solo doblaje</option>
                <option value="dual">Doblaje + original (dos pistas)</option>
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Slider
                label="Velocidad de habla"
                value={Number(values.speech_rate ?? 1)}
                min={0.7}
                max={1.5}
                step={0.05}
                onChange={(value) => set("speech_rate", value)}
                format={(value) => `x${value.toFixed(2)}`}
              />
              <Slider
                label="Volumen de voz"
                value={Number(values.volume ?? 1)}
                min={0.5}
                max={1.5}
                step={0.05}
                onChange={(value) => set("volume", value)}
                format={(value) => `${Math.round(value * 100)}%`}
              />
              <Slider
                label="Aceleración máxima"
                value={Number(values.max_speedup ?? 1.18)}
                min={1.0}
                max={1.4}
                step={0.01}
                onChange={(value) => set("max_speedup", value)}
                format={(value) => `x${value.toFixed(2)}`}
              />
              <Slider
                label="Pausa entre segmentos"
                value={Number(values.gap_ms ?? 80)}
                min={0}
                max={400}
                step={10}
                onChange={(value) => set("gap_ms", value)}
                format={(value) => `${value} ms`}
              />
            </div>
            <Slider
              label="Sonoridad objetivo"
              value={Number(values.loudness_lufs ?? -16)}
              min={-24}
              max={-10}
              step={1}
              onChange={(value) => set("loudness_lufs", value)}
              format={(value) => `${value} LUFS`}
              hint="Estándar para web: -16 LUFS. Se aplica un limitador para evitar saturación."
            />
            <Toggle
              checked={Boolean(values.ducking)}
              onChange={(value) => set("ducking", value)}
              label="Atenuar fondo bajo la voz"
              description="Reduce música y ambiente mientras habla el doblaje."
            />
            <Toggle
              checked={Boolean(values.separation)}
              onChange={(value) => set("separation", value)}
              label="Separar voz y fondo por defecto"
              description="Opcional. Puede introducir artefactos; si falla se usa el audio original atenuado."
            />
          </div>
        </Card>

        <Card className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <HardDrive size={15} className="text-sky-400" />
            <h3 className="text-sm font-medium text-slate-100">Límites y almacenamiento</h3>
          </div>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Tamaño máximo de subida (MB)">
                <input
                  type="number"
                  min={16}
                  max={10240}
                  className="input"
                  value={Number(values.max_upload_mb ?? 2048)}
                  onChange={(event) => set("max_upload_mb", Number(event.target.value))}
                />
              </Field>
              <Field label="Duración máxima (minutos)" hint="Se valida al subir el video.">
                <input
                  type="number"
                  min={1}
                  max={360}
                  className="input"
                  value={Math.round(Number(values.max_duration_s ?? 3600) / 60)}
                  onChange={(event) => set("max_duration_s", Number(event.target.value) * 60)}
                />
              </Field>
            </div>
            <Toggle
              checked={Boolean(values.keep_temp)}
              onChange={(value) => set("keep_temp", value)}
              label="Conservar audio intermedio"
              description="Útil para depurar; ocupa más disco y no es necesario para exportar."
            />
            <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
              <Field label="Días antes de limpiar temporales">
                <input
                  type="number"
                  min={1}
                  max={365}
                  className="input"
                  value={Number(values.cleanup_days ?? 7)}
                  onChange={(event) => set("cleanup_days", Number(event.target.value))}
                />
              </Field>
              <Button variant="secondary" onClick={cleanup} loading={cleaning}>
                <Trash2 size={14} /> Limpiar ahora
              </Button>
            </div>
          </div>
        </Card>

        <div className="space-y-5">
          <Card className="p-5">
            <div className="mb-4 flex items-center gap-2">
              <FolderCog size={15} className="text-amber-400" />
              <h3 className="text-sm font-medium text-slate-100">Carpetas locales</h3>
            </div>
            <div className="space-y-3">
              {Object.entries(settingsQ.data.paths).map(([key, value]) => (
                <div key={key}>
                  <p className="label mb-1">{key.replace(/_/g, " ")}</p>
                  <code className="block break-all rounded-lg border border-white/[0.06] bg-ink-950/60 px-2.5 py-2 font-mono text-[10px] text-slate-400">
                    {value}
                  </code>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[10px] leading-relaxed text-slate-600">
              Las carpetas se configuran con VTS_DATA_DIR y VTS_MODELS_DIR antes de iniciar
              la aplicación (ver docs/INSTALL.md).
            </p>
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck size={15} className="text-emerald-400" />
                <h3 className="text-sm font-medium text-slate-100">Privacidad y seguridad</h3>
              </div>
              <Badge tone="green" dot>Local</Badge>
            </div>
            <ul className="mt-3 space-y-2 text-[11px] leading-relaxed text-slate-500">
              <li className="flex gap-2"><CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400/70" /> Escucha únicamente en 127.0.0.1.</li>
              <li className="flex gap-2"><CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400/70" /> Sin telemetría, analíticas ni CDNs externos.</li>
              <li className="flex gap-2"><CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400/70" /> Protección de origen y cabecera de cliente en operaciones de escritura.</li>
              <li className="flex gap-2"><CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400/70" /> Rutas validadas dentro de las carpetas del proyecto.</li>
              <li className="flex gap-2"><CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400/70" /> Sin APIs de pago ni envío de audio a la nube.</li>
            </ul>
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-400/20 bg-amber-400/[0.04] px-2.5 py-2">
              <AlertTriangle size={12} className="mt-0.5 shrink-0 text-amber-300" />
              <p className="text-[10px] leading-relaxed text-amber-200/70">
                La separación de voz no es perfecta. Revisa siempre el resultado antes de
                publicarlo. Consulta las licencias en THIRD_PARTY_NOTICES.md.
              </p>
            </div>
          </Card>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => settingsQ.refresh()}>
              <RefreshCw size={14} /> Recargar
            </Button>
            <Button variant="primary" onClick={save} loading={saving} disabled={!dirty}>
              <Save size={14} /> Guardar cambios
            </Button>
          </div>
        </div>
      </div>

      {dirty && (
        <div className="fixed bottom-5 left-1/2 z-40 flex -translate-x-1/2 items-center gap-3 rounded-xl border border-amber-400/25 bg-ink-850/95 px-4 py-2.5 shadow-2xl backdrop-blur">
          <span className="flex items-center gap-1.5 text-[11px] text-amber-200/80">
            <SlidersHorizontal size={12} /> Cambios sin guardar
          </span>
          <Button size="sm" variant="primary" onClick={save} loading={saving}>
            <Save size={12} /> Guardar
          </Button>
        </div>
      )}

      <div className="flex items-center gap-2 text-[10px] text-slate-600">
        <Cpu size={11} /> {system.data?.hardware.cpu} · {system.data?.hardware.ram_total_gb} GB RAM ·
        <Gauge size={11} /> perfil recomendado: {String(system.data?.recommendation.profile ?? "—")}
      </div>
    </div>
  );
}
