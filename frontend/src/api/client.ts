import type {
  AppSettings,
  Health,
  Job,
  LogEvent,
  Model,
  Options,
  Project,
  Segment,
  SystemInfo,
  Voice,
} from "./types";

const BASE = "/api";
const CLIENT_HEADER = { "X-VTS-Client": "web" };

export class ApiError extends Error {
  code: string;
  hint?: string | null;
  status: number;

  constructor(message: string, status = 0, code = "network_error", hint?: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.hint = hint;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (init.method && init.method !== "GET") {
    Object.entries(CLIENT_HEADER).forEach(([k, v]) => headers.set(k, v));
  }
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch (error) {
    throw new ApiError(
      "No se pudo conectar con el backend local.",
      0,
      "connection_failed",
      "Comprueba que la aplicación esté iniciada (scripts/start.ps1).",
    );
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail = payload?.error ?? payload?.detail;
    let message = "La operación falló.";
    let hint: string | null = null;
    let code = "http_error";
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      message = detail.message || message;
      hint = detail.hint ?? null;
      code = detail.code || code;
    } else if (Array.isArray(detail)) {
      message = detail.map((d: { msg?: string }) => d.msg).join(" · ");
    }
    throw new ApiError(message, response.status, code, hint);
  }
  return payload as T;
}

export const api = {
  health: () => request<Health>("/health"),
  system: () => request<SystemInfo>("/system"),
  options: () => request<Options>("/options"),

  projects: () => request<{ projects: Project[] }>("/projects"),
  project: (id: string) => request<Project>(`/projects/${id}`),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  startJob: (projectId: string, settings: Partial<Record<string, unknown>>) =>
    request<Job>(`/projects/${projectId}/jobs`, {
      method: "POST",
      body: JSON.stringify(settings),
    }),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  jobs: (activeOnly = false) =>
    request<{ jobs: Job[] }>(`/jobs?limit=50&active_only=${activeOnly}`),
  cancelJob: (id: string) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
  resumeJob: (id: string) => request<Job>(`/jobs/${id}/resume`, { method: "POST" }),
  rerender: (id: string) => request<Job>(`/jobs/${id}/rerender`, { method: "POST" }),
  events: (id: string) => request<{ events: LogEvent[] }>(`/jobs/${id}/events`),

  segments: (jobId: string) =>
    request<{ segments: Segment[]; duration: number }>(`/jobs/${jobId}/segments`),
  updateSegment: (jobId: string, idx: number, body: Record<string, unknown>) =>
    request<Segment>(`/jobs/${jobId}/segments/${idx}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  regenerateSegment: (jobId: string, idx: number, textEs?: string) =>
    request<{ status: string }>(`/jobs/${jobId}/segments/${idx}/regenerate`, {
      method: "POST",
      body: JSON.stringify({ text_es: textEs }),
    }),

  models: () => request<{ models: Model[]; recommendation: Record<string, unknown>; storage: string }>("/models"),
  downloadModel: (id: string) =>
    request<{ status: string }>(`/models/${id}/download`, { method: "POST" }),
  removeModel: (id: string) =>
    request<{ status: string }>(`/models/${id}`, { method: "DELETE" }),
  unloadModels: () =>
    request<{ status: string }>("/models/unload", { method: "POST" }),

  settings: () =>
    request<{
      settings: AppSettings;
      defaults: AppSettings;
      recommendation: Record<string, unknown>;
      paths: Record<string, string>;
      voices: Voice[];
      capabilities: Record<string, unknown>;
    }>("/settings"),
  updateSettings: (values: Record<string, unknown>) =>
    request<{ settings: AppSettings }>("/settings", {
      method: "PUT",
      body: JSON.stringify(values),
    }),
  cleanup: (days = 7) =>
    request<{ removed: number; freed_mb: number }>(`/maintenance/cleanup?days=${days}`, {
      method: "POST",
    }),

  mediaUrl: (jobId: string, kind: "original" | "output" | "dub" | "mix" | "background") =>
    `${BASE}/jobs/${jobId}/media/${kind}`,
  segmentAudioUrl: (jobId: string, idx: number) =>
    `${BASE}/jobs/${jobId}/segments/${idx}/audio`,
  downloadUrl: (jobId: string) => `${BASE}/jobs/${jobId}/download`,
  subtitleUrl: (jobId: string, fmt: "srt" | "vtt" | "txt") =>
    `${BASE}/jobs/${jobId}/subtitles/${fmt}`,
};

export function uploadProject(
  file: File,
  name: string,
  onProgress: (percent: number) => void,
): Promise<Project> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/projects`);
    xhr.setRequestHeader("X-VTS-Client", "web");
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress((event.loaded / event.total) * 100);
    };
    xhr.onerror = () =>
      reject(new ApiError("No se pudo subir el archivo.", 0, "upload_failed",
        "Comprueba que el backend esté en ejecución."));
    xhr.onload = () => {
      let payload: any = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        resolve(payload as Project);
      } else {
        const error = payload?.error;
        reject(new ApiError(
          error?.message || "No se pudo subir el video.",
          xhr.status,
          error?.code || "upload_failed",
          error?.hint,
        ));
      }
    };
    const form = new FormData();
    form.append("file", file);
    form.append("name", name || file.name.replace(/\.[^.]+$/, ""));
    xhr.send(form);
  });
}
