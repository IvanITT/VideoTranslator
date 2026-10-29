import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AppSettings, Health, Job, LogEvent, Model, Options, Project, Segment, SystemInfo } from "../api/types";

interface PollingState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refresh: () => void;
}

export function usePolling<T>(
  loader: () => Promise<T>,
  intervalMs: number,
  enabled = true,
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const refresh = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const run = async () => {
      try {
        const result = await loaderRef.current();
        if (alive) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(err as Error);
      } finally {
        if (alive) setLoading(false);
      }
    };
    run();
    if (enabled && intervalMs > 0) {
      timer = window.setInterval(run, intervalMs);
    }
    return () => {
      alive = false;
      if (timer) window.clearInterval(timer);
    };
  }, [intervalMs, enabled, tick]);

  return { data, error, loading, refresh };
}

export function useHealth() {
  return usePolling<Health>(() => api.health(), 15000);
}

export function useSystem() {
  return usePolling<SystemInfo>(() => api.system(), 5000);
}

export function useProjects() {
  return usePolling<{ projects: Project[] }>(() => api.projects(), 8000);
}

export function useModels() {
  return usePolling<{ models: Model[]; recommendation: Record<string, unknown>; storage: string }>(
    () => api.models(),
    3000,
  );
}

export function useOptions() {
  return usePolling<Options>(() => api.options(), 0);
}

export function useSettingsData() {
  return usePolling(() => api.settings(), 0);
}

export function useProject(projectId?: string) {
  return usePolling<Project | null>(
    () => (projectId ? api.project(projectId) : Promise.resolve(null)),
    5000,
    Boolean(projectId),
  );
}

const ACTIVE = new Set(["queued", "running", "cancelling"]);

export function useJob(jobId?: string | null) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [events, setEvents] = useState<LogEvent[]>([]);
  const active = job ? ACTIVE.has(job.status) : true;

  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    let timer: number | undefined;

    const load = async () => {
      try {
        const next = await api.job(jobId);
        if (!alive) return;
        setJob(next);
        setError(null);
        if (next.status !== "queued" && next.status !== "running") {
          const log = await api.events(jobId);
          if (alive) setEvents(log.events);
        }
      } catch (err) {
        if (alive) setError(err as Error);
      }
    };

    load();
    if (active) {
      timer = window.setInterval(load, 1200);
    }
    return () => {
      alive = false;
      if (timer) window.clearInterval(timer);
    };
  }, [jobId, active]);

  useEffect(() => {
    if (!jobId || !job) return;
    let alive = true;
    const load = async () => {
      try {
        const log = await api.events(jobId);
        if (alive) setEvents(log.events.slice(-200));
      } catch {
        /* logs are best-effort */
      }
    };
    load();
    if (ACTIVE.has(job.status)) {
      const timer = window.setInterval(load, 2500);
      return () => {
        alive = false;
        window.clearInterval(timer);
      };
    }
  }, [jobId, job?.status]);

  return { job, error, events, refresh: () => jobId && api.job(jobId).then(setJob) };
}

export function useSegments(jobId?: string | null, enabled = true, version = "") {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [duration, setDuration] = useState(0);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const result = await api.segments(jobId);
      setSegments(result.segments);
      setDuration(result.duration || 0);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !enabled) return;
    reload();
  }, [jobId, enabled, reload, version]);

  return { segments, setSegments, duration, loading, reload };
}

export function useToastQueue() {
  const [toasts, setToasts] = useState<{ id: number; title: string; description?: string; tone: "error" | "success" | "info" }[]>([]);
  const push = useCallback((title: string, description?: string, tone: "error" | "success" | "info" = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, title, description, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 6500);
  }, []);
  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);
  return { toasts, push, dismiss };
}

export type { AppSettings };
