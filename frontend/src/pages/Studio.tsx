import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Boxes,
  Check,
  ChevronDown,
  CirclePlay,
  Clock,
  Download,
  FileText,
  Film,
  Languages,
  Loader2,
  Mic2,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wand2,
  XCircle,
} from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Job, JobSettings, Segment } from "../api/types";
import { useJob, useOptions, useProject, useSegments, useSettingsData, useSystem } from "../hooks/useApi";
import { StageTracker } from "../components/StageTracker";
import { SegmentEditor } from "../components/SegmentEditor";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Progress,
  Select,
  Slider,
  Spinner,
  StatTile,
  StatusBadge,
  Toggle,
} from "../components/ui";
import { useToast } from "../components/Toast";
import { formatBytes, formatDate, formatDuration, formatTimecode, STATUS_LABEL } from "../lib/format";

const DEFAULT_SETTINGS: JobSettings = {
  source_language: "auto",
  target_language: "es",
  target_variant: "es-MX",
  voice: "es_MX-ald-medium",
  mode: "dub_plus_background",
  preset: "balanced",
  separation: false,
  separation_method: "auto",
  asr_model: "auto",
  translation_engine: "auto",
  speech_rate: 1.0,
  volume: 1.0,
  max_speedup: 1.18,
  gap_ms: 80,
  loudness_lufs: -16,
  ducking: true,
  keep_temp: false,
  threads: 0,
  device: "auto",
  compute_type: "int8",
  quantize_translation: false,
  max_duration_s: 3600,
  audio_bitrate: "192k",
};

const PRESET_INFO: Record<string, { title: string; text: string }> = {
  low: { title: "Bajo consumo", text: "Whisper Tiny, menos RAM, secuencial." },
  balanced: { title: "Equilibrado", text: "Whisper Base, buena calidad y velocidad." },
  high: { title: "Alta calidad", text: "Whisper Small, más lento en CPU." },
};

export function Studio() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const projectQ = useProject(projectId);
  const system = useSystem();
  const options = useOptions();
  const settingsQ = useSettingsData();
  const toast = useToast();

  const project = projectQ.data;
  const [jobId, setJobId] = useState<string | null>(null);
  const [tab, setTab] = useState<"result" | "editor" | "details">("result");
  const [showConfig, setShowConfig] = useState(false);
  const [starting, setStarting] = useState(false);
  const [form, setForm] = useState<JobSettings>(DEFAULT_SETTINGS);
  const [advanced, setAdvanced] = useState(false);
  const [ab, setAb] = useState<"dub" | "original">("dub");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!jobId && project?.jobs && project.jobs.length > 0) {
      setJobId(project.jobs[0].id);
    }
  }, [project, jobId]);

  useEffect(() => {
    if (!settingsQ.data) return;
    const stored = settingsQ.data.settings;
    setForm((current) => ({
      ...current,
      ...Object.fromEntries(
        Object.keys(DEFAULT_SETTINGS)
          .filter((key) => stored[key] !== undefined)
          .map((key) => [key, stored[key]]),
      ),
    }));
  }, [settingsQ.data]);

  const { job, error: jobError, events, refresh } = useJob(jobId);
  const segmentsQ = useSegments(jobId, Boolean(jobId), job?.status ?? "");

  const voiceOptions = useMemo(() => {
    const voices = options.data?.voices ?? [];
    const installed = voices.filter((voice) => voice.installed);
    return installed.length > 0 ? installed : voices;
  }, [options.data]);

  const effectiveSettings = useMemo<JobSettings>(() => {
    if (job?.settings) return { ...DEFAULT_SETTINGS, ...job.settings };
    return form;
  }, [job, form]);

  const startJob = async () => {
    if (!projectId) return;
    setStarting(true);
    try {
      const created = await api.startJob(projectId, {
        ...form,
        threads: form.threads || settingsQ.data?.settings.cpu_threads || 0,
      });
      setJobId(created.id);
      setShowConfig(false);
      setTab("result");
      projectQ.refresh();
      toast.push("Doblaje en cola", "El procesamiento comenzó en tu equipo.", "success");
    } catch (err) {
      const apiError = err as ApiError;
      toast.push("No se pudo iniciar el doblaje", `${apiError.message} ${apiError.hint ?? ""}`, "error");
    } finally {
      setStarting(false);
    }
  };

  const resume = async () => {
    if (!job) return;
    try {
      await api.resumeJob(job.id);
      refresh();
      toast.push("Trabajo reanudado", "Se reutilizarán las etapas completadas.", "success");
    } catch (err) {
      toast.push("No se pudo reanudar", (err as ApiError).message, "error");
    }
  };

  const rerender = async () => {
    if (!job) return;
    try {
      await api.rerender(job.id);
      refresh();
      toast.push("Regenerando video", "Se aplicarán los cambios del guion.", "success");
    } catch (err) {
      toast.push("No se pudo regenerar", (err as ApiError).message, "error");
    }
  };

  const cancel = async () => {
    if (!job) return;
    try {
      await api.cancelJob(job.id);
      toast.push("Cancelación solicitada", "El progreso completado se conserva.", "info");
      refresh();
    } catch (err) {
      toast.push("No se pudo cancelar", (err as ApiError).message, "error");
    }
  };

  const removeProject = async () => {
    if (!projectId) return;
    if (!window.confirm("¿Eliminar este proyecto y todos sus archivos generados?")) return;
    setDeleting(true);
    try {
      await api.deleteProject(projectId);
      navigate("/");
    } catch (err) {
      toast.push("No se pudo eliminar", (err as ApiError).message, "error");
      setDeleting(false);
    }
  };

  if (projectQ.loading && !project) {
    return <Card><Spinner label="Cargando proyecto…" /></Card>;
  }
  if (!project) {
    return (
      <Card>
        <EmptyState
          icon={<Film size={30} />}
          title="Proyecto no encontrado"
          description="Puede que se haya eliminado o que el enlace no sea válido."
          action={<Button variant="primary" onClick={() => navigate("/")}>Volver al panel</Button>}
        />
      </Card>
    );
  }

  const status = job?.status ?? "idle";
  const active = ["queued", "running", "cancelling"].includes(status);
  const showResults = status === "completed" && !showConfig;
  const showFailure = ["failed", "cancelled", "interrupted"].includes(status) && !showConfig;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            to="/"
            className="mb-3 inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300"
          >
            <ArrowLeft size={13} /> Todos los proyectos
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight text-white">{project.name}</h1>
            {job ? <StatusBadge status={job.status} /> : <Badge tone="slate">Sin procesar</Badge>}
          </div>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span>{project.width}×{project.height}</span>
            <span>{project.fps ?? "—"} fps</span>
            <span>{formatDuration(project.duration)}</span>
            <span>{formatBytes(project.size_bytes)}</span>
            <span className="text-slate-600">{formatDate(project.created_at)}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {showResults && (
            <Button variant="ghost" size="sm" onClick={() => setShowConfig((value) => !value)}>
              <Wand2 size={14} /> {showConfig ? "Ver resultado" : "Nuevo doblaje"}
            </Button>
          )}
          {job && (
            <Button variant="ghost" size="sm" onClick={removeProject} disabled={deleting || active}>
              <Trash2 size={14} /> Eliminar
            </Button>
          )}
        </div>
      </div>

      {showConfig && (
        <ConfigPanel
          form={form}
          setForm={setForm}
          options={options.data}
          projectDuration={project.duration}
          projectId={project.id}
          advanced={advanced}
          setAdvanced={setAdvanced}
          starting={starting}
          onStart={startJob}
          onCancel={() => setShowConfig(false)}
          hardware={system.data?.hardware}
        />
      )}

      {!showConfig && active && job && (
        <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
          <Card className="p-5 sm:p-6">
            <StageTracker job={job} />
            <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-4">
              <Button variant="danger" size="sm" onClick={cancel} disabled={status === "cancelling"}>
                <XCircle size={14} /> {status === "cancelling" ? "Cancelando…" : "Cancelar"}
              </Button>
              <span className="text-[11px] text-slate-600">
                Puedes cerrar esta pestaña; el trabajo continúa en el equipo.
              </span>
            </div>
          </Card>
          <div className="space-y-4">
            <Card className="overflow-hidden">
              <div className="relative aspect-video bg-black">
                <img
                  src={`/api/projects/${project.id}/thumbnail`}
                  alt=""
                  className="h-full w-full object-cover opacity-70"
                  onError={(event) => { event.currentTarget.style.display = "none"; }}
                />
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-t from-black/80 via-black/20 to-transparent">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full border border-amber-400/30 bg-amber-400/10 backdrop-blur">
                    <Loader2 size={20} className="animate-spin text-amber-300" />
                  </div>
                  <p className="mt-3 max-w-[85%] text-center text-xs text-slate-300">{job.message}</p>
                </div>
              </div>
              <div className="grid grid-cols-3 divide-x divide-white/[0.06] text-center">
                <div className="py-2.5">
                  <p className="font-mono text-sm text-white">{formatDuration(job.elapsed_s ?? 0)}</p>
                  <p className="text-[10px] uppercase tracking-wider text-slate-600">transcurrido</p>
                </div>
                <div className="py-2.5">
                  <p className="font-mono text-sm text-white">{Math.round(job.progress)}%</p>
                  <p className="text-[10px] uppercase tracking-wider text-slate-600">completado</p>
                </div>
                <div className="py-2.5">
                  <p className="font-mono text-sm text-white">{job.queue?.pending ?? 0}</p>
                  <p className="text-[10px] uppercase tracking-wider text-slate-600">en cola</p>
                </div>
              </div>
            </Card>
            {job.warnings.length > 0 && <WarningsCard warnings={job.warnings} />}
            <JobLog events={events} live />
          </div>
        </div>
      )}

      {!showConfig && !job && (
        <ConfigPanel
          form={form}
          setForm={setForm}
          options={options.data}
          projectDuration={project.duration}
          projectId={project.id}
          advanced={advanced}
          setAdvanced={setAdvanced}
          starting={starting}
          onStart={startJob}
          hardware={system.data?.hardware}
        />
      )}

      {showFailure && job && (
        <div className="space-y-5">
          <Card className="p-5 sm:p-6">
            <ErrorBanner
              title={job.status === "cancelled" ? "Trabajo cancelado" : job.status === "interrupted" ? "Procesamiento interrumpido" : "El procesamiento falló"}
              message={job.error ?? job.message ?? "El trabajo se detuvo."}
              hint={job.error_hint ?? "Puedes reanudar el trabajo: las etapas completadas se reutilizan."}
              action={
                <div className="flex gap-2">
                  <Button variant="primary" size="sm" onClick={resume}>
                    <RotateCcw size={14} /> Reanudar
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setShowConfig(true)}>
                    Reconfigurar
                  </Button>
                </div>
              }
            />
            <div className="mt-4">
              <StageTracker job={job} />
            </div>
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">
            <JobLog events={events} />
            {job.warnings.length > 0 ? <WarningsCard warnings={job.warnings} /> : <Card className="p-5 text-xs text-slate-500">Sin advertencias adicionales.</Card>}
          </div>
        </div>
      )}

      {showResults && job && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-1 rounded-xl border border-white/[0.06] bg-ink-900/60 p-1">
            {[
              { id: "result" as const, label: "Resultado" },
              { id: "editor" as const, label: "Guion y voces" },
              { id: "details" as const, label: "Detalles" },
            ].map((item) => (
              <button
                key={item.id}
                onClick={() => setTab(item.id)}
                className={`rounded-lg px-4 py-2 text-xs font-medium transition ${
                  tab === item.id
                    ? "bg-amber-400/10 text-amber-200 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.15)]"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {tab === "result" && (
            <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
              <div className="space-y-4">
                <Card className="overflow-hidden">
                  <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5">
                    <div className="flex gap-1 rounded-lg bg-ink-950/60 p-0.5">
                      <button
                        onClick={() => setAb("dub")}
                        className={`rounded-md px-3 py-1.5 text-[11px] font-medium ${ab === "dub" ? "bg-amber-400 text-ink-950" : "text-slate-400 hover:text-slate-200"}`}
                      >
                        Doblaje español
                      </button>
                      <button
                        onClick={() => setAb("original")}
                        className={`rounded-md px-3 py-1.5 text-[11px] font-medium ${ab === "original" ? "bg-white/10 text-white" : "text-slate-400 hover:text-slate-200"}`}
                      >
                        Original
                      </button>
                    </div>
                    <Badge tone="green" dot>MP4 validado</Badge>
                  </div>
                  <video
                    key={`${job.id}-${ab}`}
                    className="aspect-video w-full bg-black"
                    controls
                    preload="metadata"
                    src={
                      ab === "dub"
                        ? `${api.mediaUrl(job.id, "output")}?v=${job.finished_at ?? ""}`
                        : api.mediaUrl(job.id, "original")
                    }
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] px-4 py-3">
                    <span className="text-[11px] text-slate-500">
                      {formatDuration(project.duration)} · audio AAC · video sin recodificar
                    </span>
                    <a
                      href={api.downloadUrl(job.id)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-amber-400 px-3 py-1.5 text-[11px] font-semibold text-ink-950 hover:bg-amber-300"
                    >
                      <Download size={13} /> Descargar MP4
                    </a>
                  </div>
                </Card>

                <div className="grid gap-3 sm:grid-cols-3">
                  <DownloadCard
                    title="Subtítulos SRT"
                    hint="Compatible con la mayoría de reproductores"
                    href={api.subtitleUrl(job.id, "srt")}
                    icon={<FileText size={16} />}
                  />
                  <DownloadCard
                    title="Subtítulos VTT"
                    hint="Para web y HTML5"
                    href={api.subtitleUrl(job.id, "vtt")}
                    icon={<FileText size={16} />}
                  />
                  <DownloadCard
                    title="Transcripción"
                    hint="Original y traducción"
                    href={api.subtitleUrl(job.id, "txt")}
                    icon={<Languages size={16} />}
                  />
                </div>

                {job.warnings.length > 0 && <WarningsCard warnings={job.warnings} />}
              </div>

              <div className="space-y-4">
                <Card className="p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="label">Resumen del doblaje</span>
                    <Badge tone="amber">{job.settings.target_variant}</Badge>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <StatTile label="Segmentos" value={String(job.stats.segments ?? segmentsQ.segments.length)} />
                    <StatTile label="Idioma" value={String(job.stats.language ?? "—").toUpperCase()} hint={`${Math.round(Number(job.stats.language_probability ?? 1) * 100)}% confianza`} />
                    <StatTile label="Voz" value={String(job.stats.tts_voice ?? job.settings.voice).replace("es_MX-", "")} hint={String(job.stats.tts_engine ?? "")} />
                    <StatTile label="Duración" value={formatDuration(Number(job.stats.output_duration ?? project.duration))} />
                    <StatTile label="Velocidad máx." value={`x${Number(job.stats.sync_max_speed ?? 1).toFixed(2)}`} hint="ajuste de ritmo" />
                    <StatTile label="Archivo" value={formatBytes(Number(job.stats.output_size_bytes ?? 0))} />
                  </div>
                  <div className="mt-3 space-y-1.5 border-t border-white/[0.06] pt-3 text-[11px]">
                    <Row label="Reconocimiento" value={String(job.stats.asr_model ?? "—")} />
                    <Row label="Traducción" value={String(job.stats.translation_model ?? "—")} />
                    <Row label="Mezcla" value={String(job.stats.mix_mode ?? "—")} />
                    <Row label="Tiempo total" value={formatDuration(Number(job.stats.elapsed_s ?? 0))} />
                  </div>
                </Card>

                <Card className="p-4">
                  <div className="mb-3 flex items-center gap-2 text-xs font-medium text-slate-200">
                    <CirclePlay size={14} className="text-amber-400" /> Comparar audio
                  </div>
                  <div className="space-y-3">
                    <div>
                      <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-600">Doblaje (solo voz)</p>
                      <audio controls preload="none" className="h-9 w-full" src={api.mediaUrl(job.id, "dub")} />
                    </div>
                    <div>
                      <p className="mb-1 text-[10px] uppercase tracking-wider text-slate-600">Mezcla final</p>
                      <audio controls preload="none" className="h-9 w-full" src={api.mediaUrl(job.id, "mix")} />
                    </div>
                  </div>
                </Card>

                <Card className="p-4">
                  <div className="flex items-center gap-2 text-xs font-medium text-slate-200">
                    <ShieldCheck size={14} className="text-emerald-400" /> Entrega local
                  </div>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
                    El video final se guardó en{" "}
                    <code className="rounded bg-white/[0.05] px-1 py-0.5 text-[10px] text-slate-300">
                      storage/exports/
                    </code>{" "}
                    y el proyecto conserva el original intacto.
                  </p>
                </Card>
              </div>
            </div>
          )}

          {tab === "editor" && (
            <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr]">
              <div>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-slate-200">
                      {segmentsQ.segments.length} segmentos
                    </p>
                    <p className="text-[11px] text-slate-500">
                      Edita la traducción y regenera solo lo necesario.
                    </p>
                  </div>
                  <Button variant="secondary" size="sm" onClick={rerender}>
                    <RefreshCw size={13} /> Regenerar video
                  </Button>
                </div>
                {segmentsQ.loading ? (
                  <Card><Spinner label="Cargando segmentos…" /></Card>
                ) : segmentsQ.segments.length === 0 ? (
                  <Card><EmptyState title="Sin segmentos" description="El trabajo no generó diálogo editable." /></Card>
                ) : (
                  <SegmentEditor
                    jobId={job.id}
                    segments={segmentsQ.segments}
                    onChanged={() => {
                      refresh();
                      projectQ.refresh();
                      segmentsQ.reload();
                    }}
                  />
                )}
              </div>
              <div className="space-y-4">
                <Card className="p-4">
                  <p className="label mb-2">Cómo funciona la edición</p>
                  <ul className="space-y-2 text-[11px] leading-relaxed text-slate-500">
                    <li>• «Guardar» cambia el texto y los subtítulos, sin tocar el audio.</li>
                    <li>• «Regenerar» vuelve a sintetizar ese segmento y rehace la mezcla y el video.</li>
                    <li>• Los demás segmentos se reutilizan: no se repite la transcripción ni la traducción.</li>
                    <li>• Si un segmento no cabe en su ventana, ajusta el texto o aumenta la velocidad máxima en Ajustes.</li>
                  </ul>
                </Card>
                <Card className="p-4">
                  <p className="label mb-2">Vista rápida</p>
                  <div className="space-y-1.5">
                    {segmentsQ.segments.slice(0, 8).map((segment) => (
                      <div key={segment.idx} className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="truncate text-slate-400">{segment.text_es || "—"}</span>
                        <span className="shrink-0 font-mono text-slate-600">{formatTimecode(segment.start)}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </div>
          )}

          {tab === "details" && job && (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="p-5">
                <p className="label mb-3">Configuración utilizada</p>
                <div className="space-y-2">
                  <Row label="Idioma de origen" value={effectiveSettings.source_language === "auto" ? `Auto (${String(job.stats.language ?? "—")})` : effectiveSettings.source_language} />
                  <Row label="Variante" value={effectiveSettings.target_variant} />
                  <Row label="Voz" value={effectiveSettings.voice} />
                  <Row label="Modo de audio" value={effectiveSettings.mode} />
                  <Row label="Perfil" value={effectiveSettings.preset} />
                  <Row label="Separación" value={effectiveSettings.separation ? "Activada" : "Desactivada"} />
                  <Row label="Velocidad de habla" value={`x${effectiveSettings.speech_rate}`} />
                  <Row label="Límite de aceleración" value={`x${effectiveSettings.max_speedup}`} />
                  <Row label="Pausa entre segmentos" value={`${effectiveSettings.gap_ms} ms`} />
                  <Row label="Ducking" value={effectiveSettings.ducking ? "Sí" : "No"} />
                  <Row label="Hilos de CPU" value={effectiveSettings.threads ? String(effectiveSettings.threads) : "Auto"} />
                </div>
              </Card>
              <div className="space-y-4">
                <Card className="p-5">
                  <p className="label mb-3">Etapas</p>
                  <div className="space-y-2">
                    {job.stages.map((stage) => (
                      <div key={stage.stage} className="flex items-center justify-between gap-3 text-xs">
                        <span className="flex items-center gap-2 text-slate-400">
                          {stage.status === "completed" || stage.status === "skipped" ? (
                            <Check size={12} className="text-emerald-400" />
                          ) : (
                            <span className="h-3 w-3 rounded-full border border-slate-700" />
                          )}
                          {stage.label}
                        </span>
                        <span className="truncate text-[11px] text-slate-600" title={stage.detail ?? ""}>
                          {stage.detail ?? STATUS_LABEL[stage.status] ?? stage.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
                <JobLog events={events} />
              </div>
            </div>
          )}
        </div>
      )}

      {showResults && job && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-4 text-[11px] text-slate-600">
          <span className="flex items-center gap-1.5">
            <Clock size={12} /> Finalizado {formatDate(job.finished_at)}
          </span>
          <span className="flex items-center gap-1.5">
            <Boxes size={12} /> {String(job.stats.asr_model ?? "")} · {String(job.stats.translation_model ?? "")} · {String(job.stats.tts_voice ?? "")}
          </span>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------ config panel */
function ConfigPanel({
  form,
  setForm,
  options,
  projectDuration,
  projectId,
  advanced,
  setAdvanced,
  starting,
  onStart,
  onCancel,
  hardware,
}: {
  form: JobSettings;
  setForm: React.Dispatch<React.SetStateAction<JobSettings>>;
  options: ReturnType<typeof useOptions>["data"];
  projectDuration: number;
  projectId: string;
  advanced: boolean;
  setAdvanced: (value: boolean) => void;
  starting: boolean;
  onStart: () => void;
  onCancel?: () => void;
  hardware?: { physical_cores: number; ram_total_gb: number; ram_available_gb: number; gpu: { available: boolean } };
}) {
  const update = <K extends keyof JobSettings>(key: K, value: JobSettings[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const installedVoices = (options?.voices ?? []).filter((voice) => voice.installed);
  const noVoices = installedVoices.length === 0;
  const estimateMinutes = Math.max(1, Math.round((projectDuration / 60) * 2.2));

  return (
    <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
      <Card raised className="overflow-hidden">
        <div className="border-b border-white/[0.06] px-5 py-4 sm:px-6">
          <div className="flex items-center gap-2">
            <Sparkles size={15} className="text-amber-400" />
            <h2 className="text-sm font-semibold text-white">Configurar doblaje</h2>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Traducción al español y voz local. Puedes ajustar todo antes de procesar.
          </p>
        </div>
        <div className="space-y-5 p-5 sm:p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Idioma original" hint="«Auto» usa detección de Whisper; puedes forzarlo si la detección falla.">
              <Select
                value={form.source_language}
                onChange={(event) => update("source_language", event.target.value)}
              >
                {(options?.languages ?? [{ value: "auto", label: "Detectar automáticamente" }]).map((language) => (
                  <option key={language.value} value={language.value}>{language.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Español de destino" hint="La variante define el acento de la voz instalada.">
              <Select
                value={form.target_variant}
                onChange={(event) => {
                  update("target_variant", event.target.value);
                  const match = installedVoices.find((voice) => voice.variant === event.target.value);
                  if (match) update("voice", match.id);
                }}
              >
                {(options?.targets ?? [{ value: "es-MX", label: "Español (México)" }]).map((target) => (
                  <option key={target.value} value={target.value}>{target.label}</option>
                ))}
              </Select>
            </Field>
          </div>

          <Field
            label="Voz en español"
            hint={
              noVoices
                ? "No hay voces instaladas. Descarga una voz en «Modelos»."
                : "La misma voz se usa en todo el video para mantener coherencia."
            }
          >
            <Select
              value={form.voice}
              onChange={(event) => update("voice", event.target.value)}
              disabled={noVoices}
            >
              {installedVoices.map((voice) => (
                <option key={voice.id} value={voice.id}>
                  {voice.label} · {voice.quality}
                </option>
              ))}
              {noVoices && <option value="">Sin voces instaladas</option>}
            </Select>
          </Field>

          <Field label="Modo de audio" hint="La separación de fuentes es opcional y puede introducir artefactos.">
            <Select value={form.mode} onChange={(event) => update("mode", event.target.value)}>
              {(options?.modes ?? []).map((mode) => (
                <option key={mode.value} value={mode.value}>{mode.label}</option>
              ))}
            </Select>
          </Field>

          <div>
            <span className="label mb-2 block">Perfil de calidad</span>
            <div className="grid gap-2 sm:grid-cols-3">
              {(["low", "balanced", "high"] as const).map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => update("preset", preset)}
                  className={`rounded-xl border p-3 text-left transition ${
                    form.preset === preset
                      ? "border-amber-400/40 bg-amber-400/[0.06] shadow-glow"
                      : "border-white/[0.07] bg-white/[0.015] hover:border-white/15"
                  }`}
                >
                  <p className={`text-xs font-medium ${form.preset === preset ? "text-amber-200" : "text-slate-300"}`}>
                    {PRESET_INFO[preset].title}
                  </p>
                  <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
                    {PRESET_INFO[preset].text}
                  </p>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-3.5">
            <Toggle
              checked={form.separation}
              onChange={(value) => update("separation", value)}
              label="Separar voz y fondo (opcional)"
              description={
                options?.separation?.demucs
                  ? "Demucs separará la voz del fondo para conservar música y efectos."
                  : "Sin Demucs se usa cancelación de canal central (rápida pero aproximada). Si no se puede separar, se atenúa el audio original."
              }
            />
          </div>

          <button
            type="button"
            onClick={() => setAdvanced(!advanced)}
            className="flex w-full items-center justify-between rounded-lg px-1 py-1 text-xs text-slate-400 hover:text-slate-200"
          >
            <span className="label">Ajustes avanzados</span>
            <ChevronDown size={14} className={`transition-transform ${advanced ? "rotate-180" : ""}`} />
          </button>
          {advanced && (
            <div className="grid gap-5 rounded-xl border border-white/[0.06] bg-white/[0.015] p-4 sm:grid-cols-2">
              <Slider
                label="Velocidad de habla base"
                value={form.speech_rate}
                min={0.7}
                max={1.5}
                step={0.05}
                onChange={(value) => update("speech_rate", value)}
                format={(value) => `x${value.toFixed(2)}`}
                hint="Más rápido = menos necesidad de acelerar después."
              />
              <Slider
                label="Volumen de la voz"
                value={form.volume}
                min={0.5}
                max={1.5}
                step={0.05}
                onChange={(value) => update("volume", value)}
                format={(value) => `${Math.round(value * 100)}%`}
              />
              <Slider
                label="Aceleración máxima permitida"
                value={form.max_speedup}
                min={1.0}
                max={1.4}
                step={0.01}
                onChange={(value) => update("max_speedup", value)}
                format={(value) => `x${value.toFixed(2)}`}
                hint="Por encima de x1.2 la voz puede sonar artificial."
              />
              <Slider
                label="Pausa entre segmentos"
                value={form.gap_ms}
                min={0}
                max={400}
                step={10}
                onChange={(value) => update("gap_ms", value)}
                format={(value) => `${value} ms`}
              />
              <Toggle
                checked={form.ducking}
                onChange={(value) => update("ducking", value)}
                label="Atenuar el fondo bajo la voz"
                description="Reduce música y efectos mientras habla el doblaje (sidechain)."
              />
              <Toggle
                checked={form.keep_temp}
                onChange={(value) => update("keep_temp", value)}
                label="Conservar archivos intermedios"
                description="Mantiene audio temporal para depurar; ocupa más disco."
              />
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-4">
            <div className="text-[11px] text-slate-500">
              <p>Duración: {formatDuration(projectDuration)}</p>
              <p className="mt-0.5">
                Estimado: ~{estimateMinutes} min en este equipo
                {hardware ? ` · ${hardware.physical_cores} núcleos · ${hardware.ram_total_gb} GB` : ""}
              </p>
            </div>
            <div className="flex gap-2">
              {onCancel && <Button variant="ghost" onClick={onCancel}>Cancelar</Button>}
              <Button variant="primary" onClick={onStart} loading={starting} disabled={noVoices}>
                <Sparkles size={16} /> Iniciar doblaje
              </Button>
            </div>
          </div>
          {noVoices && (
            <p className="rounded-lg border border-amber-400/20 bg-amber-400/[0.05] px-3 py-2 text-[11px] text-amber-200/80">
              Necesitas una voz instalada. <Link to="/models" className="underline">Abrir Modelos</Link>.
            </p>
          )}
        </div>
      </Card>

      <div className="space-y-4">
        <Card className="overflow-hidden">
          <video
            className="aspect-video w-full bg-black"
            controls
            preload="metadata"
            src={`/api/projects/${projectId}/video`}
          />
          <div className="p-4">
            <p className="text-xs font-medium text-slate-300">Vista previa del original</p>
            <p className="mt-1 text-[11px] text-slate-500">
              El video no se recodifica; solo se reemplaza la pista de audio.
            </p>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-200">
            <Mic2 size={14} className="text-sky-400" /> Qué ocurrirá
          </div>
          <ol className="mt-3 space-y-2.5">
            {[
              "Se extrae el audio y se transcribe con marcas de tiempo.",
              "Cada segmento se traduce al español con contexto local.",
              "Se sintetiza la voz y se ajusta al tiempo original.",
              "Se mezcla con el fondo (si aplica) y se exporta el MP4.",
            ].map((step, index) => (
              <li key={step} className="flex gap-2.5 text-[11px] leading-relaxed text-slate-500">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-white/[0.06] text-[9px] text-slate-400">
                  {index + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </Card>
        <Card className="border-emerald-400/10 bg-emerald-400/[0.02] p-4">
          <div className="flex items-center gap-2 text-[11px] font-medium text-emerald-300">
            <ShieldCheck size={13} /> Sin costos ni cuentas
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
            No se usan APIs de pago. Los modelos se ejecutan en tu CPU/GPU y la aplicación
            funciona sin internet una vez instalados.
          </p>
        </Card>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- fragments */
function WarningsCard({ warnings }: { warnings: string[] }) {
  return (
    <Card className="border-amber-400/15 bg-amber-400/[0.025] p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-amber-200">
        <AlertTriangle size={14} /> Advertencias de calidad
      </div>
      <ul className="mt-2.5 space-y-1.5">
        {warnings.map((warning, index) => (
          <li key={index} className="flex gap-2 text-[11px] leading-relaxed text-amber-200/60">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-400/60" />
            {warning}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function DownloadCard({ title, hint, href, icon }: { title: string; hint: string; href: string; icon: React.ReactNode }) {
  return (
    <a
      href={href}
      className="group rounded-xl border border-white/[0.06] bg-white/[0.015] p-3.5 transition hover:border-amber-400/25 hover:bg-amber-400/[0.03]"
    >
      <div className="flex items-center justify-between">
        <span className="text-amber-400/80">{icon}</span>
        <Download size={13} className="text-slate-600 group-hover:text-amber-300" />
      </div>
      <p className="mt-2 text-xs font-medium text-slate-200">{title}</p>
      <p className="mt-0.5 text-[10px] text-slate-500">{hint}</p>
    </a>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <span className="text-slate-500">{label}</span>
      <span className="truncate text-right font-mono text-slate-300">{value}</span>
    </div>
  );
}

function JobLog({ events, live = false }: { events: { id: number; ts: string; level: string; message: string }[]; live?: boolean }) {
  const [open, setOpen] = useState(live);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && live && ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [events, open, live]);

  useEffect(() => {
    setOpen(live);
  }, [live]);

  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-xs text-slate-400 hover:text-slate-200"
      >
        <span className="flex items-center gap-2">
          <FileText size={13} /> Registro ({events.length})
        </span>
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div ref={ref} className="max-h-64 overflow-y-auto border-t border-white/[0.06] bg-ink-950/60 px-4 py-3 font-mono text-[10px] leading-relaxed">
          {events.length === 0 && <p className="text-slate-600">Sin eventos todavía.</p>}
          {events.map((event) => (
            <div
              key={event.id}
              className={
                event.level === "error"
                  ? "text-red-300/80"
                  : event.level === "warning"
                    ? "text-amber-300/80"
                    : "text-slate-500"
              }
            >
              <span className="text-slate-700">{new Date(event.ts).toLocaleTimeString("es-MX")} </span>
              {event.message}
            </div>
          ))}
          {live && <div className="mt-1 h-1 w-1 animate-pulse rounded-full bg-amber-400" />}
        </div>
      )}
    </Card>
  );
}
