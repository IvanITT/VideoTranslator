import {
  Activity,
  AudioWaveform,
  Check,
  CircleDashed,
  FileSearch,
  Languages,
  Loader2,
  Mic,
  Scissors,
  ShieldCheck,
  Sparkles,
  Video,
  X,
} from "lucide-react";
import type { Job, Stage } from "../api/types";
import { formatDuration } from "../lib/format";
import { Badge, Progress } from "./ui";

const ICONS: Record<string, typeof Video> = {
  analysis: FileSearch,
  extraction: AudioWaveform,
  asr: Mic,
  translation: Languages,
  separation: Scissors,
  tts: Sparkles,
  sync: Activity,
  mix: AudioWaveform,
  render: Video,
};

function StageRow({ stage, index, current }: { stage: Stage; index: number; current: boolean }) {
  const Icon = ICONS[stage.stage] ?? CircleDashed;
  const done = stage.status === "completed" || stage.status === "skipped";
  const failed = stage.status === "failed" || stage.status === "cancelled" || stage.status === "interrupted";
  const running = stage.status === "running";

  const circle = done
    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
    : failed
      ? "border-red-400/30 bg-red-400/10 text-red-300"
      : running
        ? "border-amber-400/40 bg-amber-400/10 text-amber-300"
        : "border-white/10 bg-white/[0.03] text-slate-500";

  return (
    <li className="relative flex gap-4 pb-5 last:pb-0">
      <div className="relative flex flex-col items-center">
        <span className={`z-10 flex h-9 w-9 items-center justify-center rounded-xl border ${circle}`}>
          {done ? (
            <Check size={15} strokeWidth={2.5} />
          ) : failed ? (
            <X size={15} />
          ) : running ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Icon size={15} />
          )}
        </span>
        {index < 8 && <span className="absolute top-9 h-full w-px bg-white/[0.06]" />}
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className={`text-sm font-medium ${running || current ? "text-white" : done ? "text-slate-300" : "text-slate-500"}`}>
            {stage.label}
          </p>
          <span className="text-[11px] text-slate-600">
            {stage.status === "skipped"
              ? "Reutilizado"
              : done
                ? "Listo"
                : running
                  ? `${Math.round(stage.progress * 100)}%`
                  : failed
                    ? "Detenido"
                    : "Pendiente"}
          </span>
        </div>
        {stage.detail && (
          <p className="mt-0.5 truncate text-xs text-slate-500" title={stage.detail}>
            {stage.detail}
          </p>
        )}
        {running && <Progress value={stage.progress * 100} className="mt-2 h-1" />}
      </div>
    </li>
  );
}

export function StageTracker({ job }: { job: Job }) {
  const elapsed = job.started_at
    ? Math.max(
        0,
        ((job.finished_at ? new Date(job.finished_at).getTime() : Date.now()) -
          new Date(job.started_at).getTime()) /
          1000,
      )
    : 0;
  const active = job.status === "running";
  const stages = job.stages ?? [];

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge
            tone={active ? "amber" : job.status === "completed" ? "green" : "slate"}
            dot
          >
            {active ? "Procesando" : job.status === "completed" ? "Completado" : job.status}
          </Badge>
          {job.settings?.preset && (
            <span className="text-[11px] text-slate-500">perfil {job.settings.preset}</span>
          )}
        </div>
        <div className="flex gap-4 font-mono text-[11px] text-slate-500">
          <span>⏱ {formatDuration(elapsed)}</span>
          <span>{Math.round(job.progress)}%</span>
        </div>
      </div>
      <Progress value={job.progress} className="mb-6" tone={job.status === "completed" ? "green" : "amber"} />
      <ol className="max-h-[420px] overflow-y-auto pr-1">
        {stages.map((stage, index) => (
          <StageRow
            key={stage.stage}
            stage={stage}
            index={index}
            current={job.stage === stage.stage}
          />
        ))}
      </ol>
      {job.message && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5 text-xs text-slate-400">
          {job.status === "completed" ? (
            <ShieldCheck size={14} className="mt-0.5 shrink-0 text-emerald-400" />
          ) : (
            <Loader2 size={14} className={`mt-0.5 shrink-0 text-amber-400 ${active ? "animate-spin" : ""}`} />
          )}
          {job.message}
        </div>
      )}
    </div>
  );
}
