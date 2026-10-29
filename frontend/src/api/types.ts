export type StageStatus =
  | "pending"
  | "running"
  | "completed"
  | "skipped"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface Stage {
  stage: string;
  label: string;
  status: StageStatus;
  progress: number;
  detail?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface Project {
  id: string;
  name: string;
  original_filename: string;
  source_path?: string;
  size_bytes: number;
  duration: number;
  width: number;
  height: number;
  fps?: number;
  video_codec?: string;
  audio_codec?: string;
  has_audio: boolean;
  created_at: string;
  updated_at: string;
  thumbnail?: boolean;
  latest_job_id?: string | null;
  latest_job_status?: string | null;
  has_output?: boolean;
  active_job?: boolean;
  source_exists?: boolean;
  jobs?: Job[];
}

export interface JobSettings {
  source_language: string;
  target_language: string;
  target_variant: string;
  voice: string;
  mode: string;
  preset: string;
  separation: boolean;
  separation_method: string;
  asr_model: string;
  translation_engine: string;
  speech_rate: number;
  volume: number;
  max_speedup: number;
  gap_ms: number;
  loudness_lufs: number;
  ducking: boolean;
  keep_temp: boolean;
  threads: number;
  device: string;
  compute_type: string;
  quantize_translation: boolean;
  max_duration_s: number;
  audio_bitrate: string;
  resume?: boolean;
}

export interface Job {
  id: string;
  project_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted" | "cancelling";
  stage: string | null;
  progress: number;
  message: string | null;
  error: string | null;
  error_hint: string | null;
  warnings: string[];
  settings: JobSettings;
  stats: Record<string, unknown>;
  output_path?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_s?: number;
  stages: Stage[];
  project: Project | null;
  queue?: { current: string | null; pending: number };
}

export interface Segment {
  idx: number;
  job_id: string;
  start: number;
  end: number;
  text_src: string;
  text_es: string;
  tts_path?: string | null;
  tts_duration?: number | null;
  status: string;
  warning?: string | null;
}

export interface Voice {
  id: string;
  label: string;
  model_id: string;
  variant: string;
  gender?: string;
  installed: boolean;
  license?: string;
  size_mb?: number;
  quality?: string;
  sample_rate?: number;
}

export interface DownloadInfo {
  status: string;
  progress: number;
  message: string;
  total_bytes: number;
  downloaded_bytes: number;
}

export interface Model {
  id: string;
  stage: "asr" | "translation" | "tts";
  name: string;
  engine: string;
  repo_id: string;
  local_dir: string;
  license: string;
  license_url: string;
  commercial_use: boolean;
  approx_size_mb: number;
  ram_estimate_mb: number;
  runtime: string;
  languages: string;
  quality: string;
  notes: string;
  installed: boolean;
  downloaded_size_mb?: number;
  download?: DownloadInfo | null;
  voice?: Voice;
  source_lang?: string;
  recommended_for?: string[];
}

export interface Hardware {
  os: string;
  cpu: string;
  physical_cores: number;
  logical_cores: number;
  ram_total_gb: number;
  ram_available_gb: number;
  ram_used_gb?: number;
  ram_percent?: number;
  cpu_percent?: number;
  gpu: { available: boolean; name: string | null; vram_gb: number | null };
  disk_free_gb: number;
  ffmpeg: boolean;
  ffmpeg_version?: string | null;
  recommended_threads: number;
}

export interface SystemInfo {
  app: { name: string; version: string; offline: boolean };
  hardware: Hardware;
  recommendation: {
    profile: string;
    asr_model: string;
    voice: string;
    separation: boolean;
    reason: string;
  };
  models: {
    installed: number;
    total: number;
    disk_gb: number;
    missing_required: string[];
  };
  storage: { free_gb: number; total_gb: number };
  queue: { current: string | null; pending: number };
  capabilities: {
    separation: { demucs: boolean; center_cancel: boolean; note: string };
    tts: { piper: boolean; sapi: boolean; espeak: boolean };
    cuda: boolean;
  };
  privacy: string;
}

export interface HealthCheck {
  id: string;
  status: "ok" | "warn" | "error";
  label: string;
  detail: string;
}

export interface Health {
  status: "ok" | "degraded" | "error";
  version: string;
  offline_ready: boolean;
  checks: HealthCheck[];
  queue: { current: string | null; pending: number };
}

export interface AppSettings {
  [key: string]: number | string | boolean;
}

export interface Options {
  languages: { value: string; label: string }[];
  targets: { value: string; label: string }[];
  modes: { value: string; label: string }[];
  presets: { value: string; label: string }[];
  voices: Voice[];
  separation: {
    demucs: boolean;
    center_cancel: boolean;
    recommended: string;
    note: string;
  };
  max_upload_mb: number;
}

export interface LogEvent {
  id: number;
  ts: string;
  level: "info" | "warning" | "error";
  message: string;
}
