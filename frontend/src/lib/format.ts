export function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatBytes(bytes?: number | null): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("es-MX", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function formatTimecode(seconds: number): string {
  const total = Math.max(0, seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = Math.floor(total % 60);
  const ms = Math.floor((total - Math.floor(total)) * 10);
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${ms}`
    : `${m}:${String(s).padStart(2, "0")}.${ms}`;
}

export const STATUS_LABEL: Record<string, string> = {
  queued: "En cola",
  running: "Procesando",
  completed: "Completado",
  failed: "Error",
  cancelled: "Cancelado",
  interrupted: "Interrumpido",
  cancelling: "Cancelando",
  pending: "Pendiente",
  skipped: "Omitido",
  ready: "Listo",
  overlong: "Revisar",
  voiced: "Con voz",
  translated: "Traducido",
  transcribed: "Transcrito",
  edited: "Editado",
  empty: "Vacío",
  tts_error: "Error de voz",
};

export const STAGE_ICON_LABEL: Record<string, string> = {
  analysis: "Análisis del video",
  extraction: "Extracción de audio",
  asr: "Reconocimiento de voz",
  translation: "Traducción al español",
  separation: "Separación de fondo",
  tts: "Generación de voz",
  sync: "Sincronización",
  mix: "Mezcla de audio",
  render: "Renderizado final",
};

export function statusTone(status?: string | null): "green" | "amber" | "red" | "slate" | "blue" {
  switch (status) {
    case "completed":
    case "ok":
    case "ready":
    case "installed":
      return "green";
    case "running":
    case "voiced":
    case "translated":
      return "blue";
    case "queued":
    case "cancelling":
    case "pending":
    case "overlong":
    case "warn":
      return "amber";
    case "failed":
    case "error":
    case "tts_error":
      return "red";
    default:
      return "slate";
  }
}

export function estimateRemaining(job: {
  progress: number;
  started_at?: string | null;
  status: string;
}): number | null {
  if (job.status !== "running" || !job.started_at || job.progress <= 2) return null;
  const elapsed = (Date.now() - new Date(job.started_at).getTime()) / 1000;
  const remaining = (elapsed / job.progress) * (100 - job.progress);
  if (!Number.isFinite(remaining) || remaining < 0) return null;
  return remaining;
}
