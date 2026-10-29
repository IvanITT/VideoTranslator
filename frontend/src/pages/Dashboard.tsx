import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Boxes,
  CheckCircle2,
  Clock,
  Cpu,
  Film,
  Gauge,
  HardDrive,
  Languages,
  Mic2,
  Play,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { useModels, useOptions, useProjects, useSystem } from "../hooks/useApi";
import { UploadDropzone } from "../components/UploadDropzone";
import { Badge, Card, EmptyState, SectionHeading, Spinner, StatTile, StatusBadge } from "../components/ui";
import { formatBytes, formatDate, formatDuration } from "../lib/format";

const PROFILE_LABEL: Record<string, string> = {
  low: "Bajo consumo",
  balanced: "Equilibrado",
  high: "Alta calidad",
};

export function Dashboard() {
  const navigate = useNavigate();
  const system = useSystem();
  const projects = useProjects();
  const models = useModels();
  const options = useOptions();

  const hw = system.data?.hardware;
  const missing = system.data?.models.missing_required ?? [];
  const recent = projects.data?.projects ?? [];
  const activeJobs = recent.filter((project) =>
    ["queued", "running", "cancelling"].includes(project.latest_job_status ?? ""),
  );

  return (
    <div className="space-y-9">
      <section className="relative overflow-hidden rounded-3xl border border-white/[0.07] bg-gradient-to-br from-ink-850 via-ink-900 to-ink-950 p-6 sm:p-9">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-amber-400/[0.08] blur-3xl" />
        <div className="pointer-events-none absolute -bottom-20 left-1/3 h-48 w-48 rounded-full bg-teal-400/[0.05] blur-3xl" />
        <div className="relative grid gap-8 lg:grid-cols-[1.15fr_1fr] lg:items-center">
          <div>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <Badge tone="amber" dot>Estudio local</Badge>
              <span className="chip">
                <ShieldCheck size={11} className="text-emerald-400" /> 100% en tu equipo
              </span>
            </div>
            <h1 className="text-balance text-3xl font-semibold leading-tight tracking-tight text-white sm:text-[38px]">
              Dobla cualquier video al español,
              <span className="text-amber-300"> sin la nube.</span>
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400">
              Sube un MP4, detecta el idioma, traduce el diálogo y genera una voz en
              español (México) con sincronización automática. Whisper, MarianMT y Piper
              ejecutándose en tu propio hardware.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
              <span className="flex items-center gap-1.5"><Mic2 size={13} className="text-sky-400/80" /> Whisper</span>
              <span className="flex items-center gap-1.5"><Languages size={13} className="text-amber-400/80" /> MarianMT / NLLB</span>
              <span className="flex items-center gap-1.5"><Sparkles size={13} className="text-emerald-400/80" /> Piper es-MX</span>
              <span className="flex items-center gap-1.5"><Film size={13} className="text-slate-400" /> FFmpeg</span>
            </div>
          </div>
          <div className="rounded-2xl border border-white/[0.07] bg-ink-950/40 p-4 sm:p-5">
            <UploadDropzone
              maxMb={options.data?.max_upload_mb ?? 2048}
              onUploaded={(project) => navigate(`/projects/${project.id}`)}
            />
          </div>
        </div>
      </section>

      {missing.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-400/20 bg-amber-400/[0.05] px-5 py-4">
          <div className="flex items-start gap-3">
            <Boxes size={18} className="mt-0.5 text-amber-300" />
            <div>
              <p className="text-sm font-medium text-amber-100">Faltan modelos esenciales</p>
              <p className="mt-0.5 text-xs text-amber-200/60">
                Necesitas al menos un modelo de reconocimiento, traducción y voz. Descárgalos
                solo cuando quieras: nada se descarga automáticamente.
              </p>
            </div>
          </div>
          <Link
            to="/models"
            className="inline-flex items-center gap-1.5 rounded-lg bg-amber-400 px-3.5 py-2 text-xs font-semibold text-ink-950 hover:bg-amber-300"
          >
            Abrir modelos <ArrowRight size={13} />
          </Link>
        </div>
      )}

      <section className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          <SectionHeading
            title="Proyectos recientes"
            description="Videos procesados en este equipo. Nada se comparte con terceros."
            action={
              projects.data && projects.data.projects.length > 0 ? (
                <span className="text-xs text-slate-500">{projects.data.projects.length} proyectos</span>
              ) : undefined
            }
          />
          {projects.loading ? (
            <Card><Spinner label="Cargando proyectos…" /></Card>
          ) : recent.length === 0 ? (
            <Card>
              <EmptyState
                icon={<Film size={30} />}
                title="Todavía no hay proyectos"
                description="Sube tu primer MP4 arriba para transcribirlo, traducirlo y doblarlo al español."
              />
            </Card>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {recent.map((project) => (
                <Link
                  key={project.id}
                  to={`/projects/${project.id}`}
                  className="group flex gap-3 rounded-xl border border-white/[0.06] bg-ink-900/60 p-3 transition-all hover:border-amber-400/25 hover:bg-ink-850"
                >
                  <div className="relative flex h-[68px] w-[104px] shrink-0 items-center justify-center overflow-hidden rounded-lg border border-white/[0.06] bg-ink-950">
                    {project.thumbnail ? (
                      <img
                        src={`/api/projects/${project.id}/thumbnail`}
                        alt=""
                        className="h-full w-full object-cover opacity-80 transition group-hover:opacity-100"
                        onError={(event) => {
                          event.currentTarget.style.display = "none";
                        }}
                      />
                    ) : (
                      <Film size={20} className="text-slate-700" />
                    )}
                    <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 py-0.5 font-mono text-[9px] text-white">
                      {formatDuration(project.duration)}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-100 group-hover:text-white">
                      {project.name}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-500">
                      {project.width}×{project.height} · {formatBytes(project.size_bytes)}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <StatusBadge status={project.latest_job_status ?? undefined} />
                      <span className="text-[10px] text-slate-600">{formatDate(project.created_at)}</span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {activeJobs.length > 0 && (
            <Card className="p-4">
              <div className="mb-3 flex items-center gap-2 text-xs font-medium text-amber-300">
                <Zap size={14} /> Cola de procesamiento
              </div>
              <div className="space-y-2">
                {activeJobs.map((project) => (
                  <Link
                    key={project.id}
                    to={`/projects/${project.id}`}
                    className="flex items-center justify-between rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-xs hover:bg-white/[0.04]"
                  >
                    <span className="truncate text-slate-300">{project.name}</span>
                    <span className="flex items-center gap-2 text-[11px] text-amber-300/80">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
                      {project.latest_job_status === "queued" ? "En cola" : "Procesando"}
                    </span>
                  </Link>
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <SectionHeading title="Tu equipo" description="Detección automática del hardware." />
          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="label">Perfil recomendado</span>
              <Badge tone="amber">
                {PROFILE_LABEL[system.data?.recommendation.profile ?? ""] ?? "—"}
              </Badge>
            </div>
            <p className="text-xs leading-relaxed text-slate-500">
              {system.data?.recommendation.reason ?? "Detectando hardware…"}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <StatTile
                label="CPU"
                value={hw ? `${hw.physical_cores}C` : "—"}
                hint={hw ? `${hw.logical_cores} hilos` : undefined}
                icon={<Cpu size={13} />}
              />
              <StatTile
                label="RAM"
                value={hw ? `${hw.ram_total_gb} GB` : "—"}
                hint={hw ? `${hw.ram_available_gb} GB libres` : undefined}
                icon={<Gauge size={13} />}
              />
              <StatTile
                label="GPU"
                value={hw?.gpu.available ? "CUDA" : "CPU"}
                hint={hw?.gpu.name ?? "Sin aceleración"}
                icon={<Zap size={13} />}
              />
              <StatTile
                label="Disco"
                value={hw ? `${hw.disk_free_gb} GB` : "—"}
                hint="espacio libre"
                icon={<HardDrive size={13} />}
              />
            </div>
          </Card>

          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="label">Modelos instalados</span>
              <Link to="/models" className="text-[11px] text-amber-300/80 hover:text-amber-200">
                Gestionar
              </Link>
            </div>
            <div className="flex items-end gap-2">
              <span className="font-mono text-2xl text-white">
                {system.data?.models.installed ?? 0}
              </span>
              <span className="pb-1 text-xs text-slate-500">
                de {system.data?.models.total ?? 0} · {system.data?.models.disk_gb ?? 0} GB
              </span>
            </div>
            <div className="mt-3 space-y-1.5">
              {["asr", "translation", "tts"].map((stage) => {
                const ready = (models.data?.models ?? []).some(
                  (model) => model.stage === stage && model.installed,
                );
                return (
                  <div key={stage} className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-500">
                      {stage === "asr" ? "Reconocimiento de voz" : stage === "translation" ? "Traducción" : "Voz en español"}
                    </span>
                    <span className={ready ? "flex items-center gap-1 text-emerald-400" : "text-slate-600"}>
                      {ready ? <CheckCircle2 size={11} /> : <Clock size={11} />}
                      {ready ? "Listo" : "Falta"}
                    </span>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card className="border-emerald-400/10 bg-emerald-400/[0.025] p-4">
            <div className="flex items-center gap-2 text-xs font-medium text-emerald-300">
              <ShieldCheck size={14} /> Privacidad por diseño
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
              El backend escucha solo en 127.0.0.1. No hay telemetría, analíticas ni APIs de
              inferencia remotas. La única conexión posible es la descarga manual de modelos.
            </p>
          </Card>

          {system.data?.capabilities.separation && (
            <Card className="p-4">
              <div className="flex items-center justify-between">
                <span className="label">Separación de voz</span>
                <Badge tone={system.data.capabilities.separation.demucs ? "green" : "slate"}>
                  {system.data.capabilities.separation.demucs ? "Demucs" : "Básica"}
                </Badge>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
                {system.data.capabilities.separation.note}
              </p>
            </Card>
          )}
        </div>
      </section>

      <section>
        <SectionHeading
          title="Cómo funciona"
          description="Cinco etapas locales, con resultados persistentes en cada paso."
        />
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            { icon: Film, title: "1. Sube", text: "MP4 local; metadata y audio verificados." },
            { icon: Mic2, title: "2. Transcribe", text: "Whisper detecta idioma y tiempos." },
            { icon: Languages, title: "3. Traduce", text: "MarianMT o NLLB al español." },
            { icon: Sparkles, title: "4. Dobla", text: "Piper es-MX con ajuste de ritmo." },
            { icon: Play, title: "5. Exporta", text: "MP4 validado y subtítulos SRT/VTT." },
          ].map((step) => (
            <div key={step.title} className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-4">
              <step.icon size={17} className="text-amber-400/80" />
              <p className="mt-2.5 text-sm font-medium text-slate-200">{step.title}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{step.text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
