import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CheckCircle2,
  Cpu,
  Download,
  HardDrive,
  Info,
  Loader2,
  ShieldCheck,
  Sparkles,
  Unplug,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Model } from "../api/types";
import { ModelCard } from "../components/ModelCard";
import { useModels, useSystem } from "../hooks/useApi";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, SectionHeading, Spinner } from "../components/ui";
import { formatBytes } from "../lib/format";

const TABS = [
  { id: "all", label: "Todos" },
  { id: "asr", label: "Reconocimiento" },
  { id: "translation", label: "Traducción" },
  { id: "tts", label: "Voces" },
] as const;

const ESSENTIAL = ["whisper-base", "marian-en-es", "piper-es-mx-ald-medium"];

export function Models() {
  const modelsQ = useModels();
  const system = useSystem();
  const toast = useToast();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("all");
  const [busy, setBusy] = useState<string | null>(null);

  const models = modelsQ.data?.models ?? [];
  const filtered = useMemo(
    () => (tab === "all" ? models : models.filter((model) => model.stage === tab)),
    [models, tab],
  );
  const missingEssentials = ESSENTIAL.filter((id) => {
    const model = models.find((item) => item.id === id);
    return model && !model.installed;
  });
  const essentialsSize = models
    .filter((model) => missingEssentials.includes(model.id))
    .reduce((total, model) => total + model.approx_size_mb, 0);

  const download = async (model: Model) => {
    setBusy(model.id);
    try {
      await api.downloadModel(model.id);
      toast.push("Descarga iniciada", `${model.name} · ~${model.approx_size_mb} MB desde Hugging Face.`, "success");
      modelsQ.refresh();
    } catch (error) {
      toast.push("No se pudo descargar", (error as ApiError).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (model: Model) => {
    if (!window.confirm(`¿Eliminar «${model.name}» del disco?`)) return;
    setBusy(model.id);
    try {
      await api.removeModel(model.id);
      toast.push("Modelo eliminado", "Puedes volver a descargarlo cuando quieras.", "success");
      modelsQ.refresh();
    } catch (error) {
      toast.push("No se pudo eliminar", (error as ApiError).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const unload = async () => {
    try {
      await api.unloadModels();
      toast.push("Memoria liberada", "Los modelos se cargarán de nuevo al procesar.", "success");
    } catch (error) {
      toast.push("No se pudo liberar", (error as ApiError).message, "error");
    }
  };

  if (modelsQ.loading && models.length === 0) {
    return <Card><Spinner label="Consultando modelos…" /></Card>;
  }

  return (
    <div className="space-y-7">
      <SectionHeading
        eyebrow="Biblioteca local"
        title="Modelos de IA"
        description="Descarga solo lo que necesites. Nada se instala automáticamente y todo el procesamiento queda en tu equipo."
        action={
          <Button variant="ghost" size="sm" onClick={unload}>
            <Unplug size={14} /> Liberar memoria
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles size={15} className="text-amber-400" />
                <p className="text-sm font-medium text-slate-100">Kit esencial recomendado</p>
                <Badge tone="amber">Primer uso</Badge>
              </div>
              <p className="mt-1 max-w-lg text-xs leading-relaxed text-slate-500">
                Tres modelos ligeros bastan para empezar: reconocimiento, traducción
                inglés→español y una voz mexicana. Total aproximado:{" "}
                <span className="font-mono text-slate-300">{essentialsSize || 518} MB</span>.
              </p>
            </div>
            <Badge tone="green" dot>
              Perfil: {String(system.data?.recommendation.profile ?? "balanced")}
            </Badge>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            {ESSENTIAL.map((id) => {
              const model = models.find((item) => item.id === id);
              if (!model) return null;
              return (
                <div key={id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                  <p className="truncate text-[11px] font-medium text-slate-300">{model.name}</p>
                  <p className="mt-0.5 font-mono text-[10px] text-slate-600">~{model.approx_size_mb} MB</p>
                  <div className="mt-2">
                    {model.installed ? (
                      <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                        <CheckCircle2 size={11} /> Instalado
                      </span>
                    ) : model.download?.status === "downloading" ? (
                      <span className="flex items-center gap-1 text-[10px] text-amber-300">
                        <Loader2 size={11} className="animate-spin" /> {Math.round(model.download.progress * 100)}%
                      </span>
                    ) : (
                      <Button size="sm" variant="subtle" className="w-full" onClick={() => download(model)}>
                        <Download size={11} /> Descargar
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <span className="label">Almacenamiento</span>
            <span className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <HardDrive size={12} /> {system.data?.hardware.disk_free_gb ?? "—"} GB libres
            </span>
          </div>
          <div className="mt-3 flex items-end gap-2">
            <span className="font-mono text-2xl text-white">{modelsQ.data?.models.filter((m) => m.installed).length ?? 0}</span>
            <span className="pb-1 text-xs text-slate-500">modelos · {system.data?.models.disk_gb ?? 0} GB en disco</span>
          </div>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-amber-400 to-amber-300"
              style={{
                width: `${Math.min(100, ((system.data?.models.disk_gb ?? 0) / Math.max(1, system.data?.hardware.disk_free_gb ?? 1)) * 100)}%`,
              }}
            />
          </div>
          <p className="mt-3 break-all text-[10px] leading-relaxed text-slate-600">
            {modelsQ.data?.storage ?? "models/"}
          </p>
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-2">
            <Info size={12} className="mt-0.5 shrink-0 text-sky-400/70" />
            <p className="text-[10px] leading-relaxed text-slate-500">
              Los modelos se descargan de repositorios oficiales de Hugging Face. Después,
              la app funciona sin conexión.
            </p>
          </div>
        </Card>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1 rounded-xl border border-white/[0.06] bg-ink-900/60 p-1">
          {TABS.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-medium transition ${
                tab === item.id
                  ? "bg-amber-400/10 text-amber-200 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.15)]"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-slate-600">
          {filtered.length} modelos · verifica la licencia antes de un uso comercial
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map((model) => (
          <ModelCard
            key={model.id}
            model={model}
            busy={busy === model.id}
            onDownload={() => download(model)}
            onRemove={() => remove(model)}
          />
        ))}
      </div>

      {missingEssentials.length > 0 && (
        <Card className="border-amber-400/15 bg-amber-400/[0.03] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <AlertTriangle size={16} className="mt-0.5 text-amber-300" />
              <div>
                <p className="text-xs font-medium text-amber-100">Aún faltan piezas del kit esencial</p>
                <p className="mt-0.5 text-[11px] text-amber-200/60">
                  Sin los tres modelos no se puede completar el flujo de doblaje.
                </p>
              </div>
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={async () => {
                for (const id of missingEssentials) {
                  const model = models.find((item) => item.id === id);
                  if (model) await download(model);
                }
              }}
            >
              <Download size={13} /> Descargar los {missingEssentials.length} restantes
            </Button>
          </div>
        </Card>
      )}

      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-[11px] font-medium text-slate-300">
            <ShieldCheck size={13} className="text-emerald-400" /> Descargas controladas
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
            Solo se descargan los archivos declarados en el manifiesto, desde repositorios
            oficiales. No se ejecuta código remoto de los repositorios.
          </p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-[11px] font-medium text-slate-300">
            <Cpu size={13} className="text-sky-400" /> Ajuste al hardware
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
            En equipos con poca RAM, usa Whisper Tiny y la voz Ald. Los modelos se cargan
            solo durante la etapa que los necesita y se liberan al terminar.
          </p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-[11px] font-medium text-slate-300">
            <Boxes size={13} className="text-amber-400" /> Licencias
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
            Whisper y Marian son permisivos (MIT / Apache-2.0). NLLB-200 es CC-BY-NC-4.0:
            no apto para uso comercial. Consulta THIRD_PARTY_NOTICES.md.
          </p>
        </Card>
      </div>

      <p className="flex items-center gap-1.5 text-[10px] text-slate-600">
        <ArrowRight size={11} /> Los pesos no forman parte del código fuente y nunca se
        incluyen en el repositorio.
      </p>
    </div>
  );
}
