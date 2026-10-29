import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Download,
  HardDrive,
  Languages,
  Trash2,
  Volume2,
} from "lucide-react";
import type { Model } from "../api/types";
import { Badge, Button, Progress } from "./ui";

const STAGE_META: Record<string, { label: string; tone: "blue" | "amber" | "green" }> = {
  asr: { label: "Reconocimiento", tone: "blue" },
  translation: { label: "Traducción", tone: "amber" },
  tts: { label: "Voz", tone: "green" },
};

export function ModelCard({
  model,
  onDownload,
  onRemove,
  busy,
}: {
  model: Model;
  onDownload: () => void;
  onRemove: () => void;
  busy?: boolean;
}) {
  const meta = STAGE_META[model.stage];
  const download = model.download;
  const downloading = download?.status === "downloading" || download?.status === "started";
  const progress = download?.progress ? Math.round(download.progress * 100) : 0;
  const Icon = model.stage === "tts" ? Volume2 : model.stage === "translation" ? Languages : Cpu;

  return (
    <div className="flex h-full flex-col rounded-xl border border-white/[0.07] bg-ink-900/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.03] text-slate-300">
            <Icon size={16} />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium leading-snug text-slate-100">{model.name}</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <Badge tone={meta?.tone ?? "slate"}>{meta?.label ?? model.stage}</Badge>
              {model.voice && <span className="chip">{model.voice.variant}</span>}
              <span className="chip">{model.quality}</span>
            </div>
          </div>
        </div>
        {model.installed ? (
          <Badge tone="green" dot>Instalado</Badge>
        ) : downloading ? (
          <Badge tone="amber" dot>Descargando</Badge>
        ) : null}
      </div>

      <p className="mt-3 text-xs leading-relaxed text-slate-500">{model.notes}</p>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
        <div>
          <dt className="text-slate-600">Descarga</dt>
          <dd className="mt-0.5 flex items-center gap-1 font-mono text-slate-300">
            <HardDrive size={11} /> ~{model.approx_size_mb} MB
          </dd>
        </div>
        <div>
          <dt className="text-slate-600">RAM estimada</dt>
          <dd className="mt-0.5 font-mono text-slate-300">~{model.ram_estimate_mb} MB</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-slate-600">Idiomas</dt>
          <dd className="mt-0.5 text-slate-400">{model.languages}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-slate-600">Licencia</dt>
          <dd className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <a
              href={model.license_url}
              target="_blank"
              rel="noreferrer"
              className="text-slate-300 underline decoration-white/20 underline-offset-2 hover:text-white"
            >
              {model.license}
            </a>
            {!model.commercial_use && (
              <span className="flex items-center gap-1 text-amber-400/80">
                <AlertTriangle size={11} /> Solo uso no comercial
              </span>
            )}
          </dd>
        </div>
      </dl>

      {downloading && (
        <div className="mt-3">
          <Progress value={progress} />
          <p className="mt-1 text-[11px] text-amber-300/80">
            {download?.message} {progress > 0 ? `· ${progress}%` : ""}
          </p>
        </div>
      )}

      {download?.status === "failed" && (
        <p className="mt-3 rounded-lg border border-red-500/20 bg-red-500/[0.06] px-2.5 py-2 text-[11px] text-red-200/80">
          {download.message}
        </p>
      )}

      <div className="mt-auto pt-4">
        {model.installed ? (
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[11px] text-emerald-400/80">
              <CheckCircle2 size={13} /> Listo para usar
            </span>
            <Button size="sm" variant="ghost" onClick={onRemove} disabled={busy}>
              <Trash2 size={13} /> Eliminar
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            className="w-full"
            onClick={onDownload}
            disabled={busy || downloading}
            loading={downloading}
          >
            {!downloading && <Download size={13} />}
            {downloading ? "Descargando…" : "Descargar modelo"}
          </Button>
        )}
      </div>
    </div>
  );
}
