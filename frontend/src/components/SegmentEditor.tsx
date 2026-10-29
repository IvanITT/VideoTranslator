import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2, Pause, Play, RefreshCw, Save } from "lucide-react";
import { api, ApiError } from "../api/client";
import type { Segment } from "../api/types";
import { formatTimecode, STATUS_LABEL, statusTone } from "../lib/format";
import { Badge, Button } from "./ui";
import { useToast } from "./Toast";

export function SegmentEditor({
  jobId,
  segments,
  disabled,
  onChanged,
}: {
  jobId: string;
  segments: Segment[];
  disabled?: boolean;
  onChanged: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const toast = useToast();

  useEffect(() => {
    setDrafts({});
  }, [segments.length, jobId]);

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  const stop = () => {
    audioRef.current?.pause();
    audioRef.current = null;
    setPlaying(null);
  };

  const play = (idx: number) => {
    if (playing === idx) {
      stop();
      return;
    }
    stop();
    const audio = new Audio(api.segmentAudioUrl(jobId, idx));
    audioRef.current = audio;
    audio.onended = () => setPlaying(null);
    audio.onerror = () => {
      setPlaying(null);
      toast.push("No se pudo reproducir el audio del segmento.",
        "Regenera el segmento para crear el archivo de voz.", "error");
    };
    audio.play().then(() => setPlaying(idx)).catch(() => {
      setPlaying(null);
      toast.push("Reproducción bloqueada por el navegador.",
        "Vuelve a pulsar reproducir.", "error");
    });
  };

  const save = async (segment: Segment) => {
    const text = drafts[segment.idx] ?? segment.text_es;
    setSaving(segment.idx);
    try {
      await api.updateSegment(jobId, segment.idx, { text_es: text });
      toast.push("Traducción guardada",
        "Pulsa «Regenerar» para actualizar la voz y el video de este segmento.", "success");
      onChanged();
    } catch (error) {
      toast.push("No se pudo guardar", (error as ApiError).message, "error");
    } finally {
      setSaving(null);
    }
  };

  const regenerate = async (segment: Segment) => {
    const text = drafts[segment.idx] ?? segment.text_es;
    if (!text.trim()) {
      toast.push("El texto está vacío", "Escribe la traducción antes de regenerar.", "error");
      return;
    }
    setSaving(segment.idx);
    try {
      await api.regenerateSegment(jobId, segment.idx, text);
      toast.push("Regeneración en cola",
        "Se generará la nueva voz y se volverá a renderizar el video.", "success");
      onChanged();
    } catch (error) {
      toast.push("No se pudo regenerar", (error as ApiError).message, "error");
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-3">
      {segments.map((segment) => {
        const draft = drafts[segment.idx] ?? segment.text_es;
        const dirty = draft !== segment.text_es;
        return (
          <div
            key={segment.idx}
            className={`rounded-xl border p-4 transition-colors ${
              segment.warning
                ? "border-amber-400/20 bg-amber-400/[0.025]"
                : "border-white/[0.06] bg-white/[0.015]"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-[11px] text-slate-600">
                  #{String(segment.idx + 1).padStart(2, "0")}
                </span>
                <span className="rounded-md bg-white/[0.05] px-2 py-0.5 font-mono text-[11px] text-slate-400">
                  {formatTimecode(segment.start)} → {formatTimecode(segment.end)}
                </span>
                <Badge tone={statusTone(segment.status)}>
                  {STATUS_LABEL[segment.status] ?? segment.status}
                </Badge>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => play(segment.idx)}
                  disabled={!segment.tts_path}
                  title={segment.tts_path ? "Escuchar voz generada" : "Genera la voz primero"}
                >
                  {playing === segment.idx ? <Pause size={14} /> : <Play size={14} />}
                  {playing === segment.idx ? "Pausar" : "Escuchar"}
                </Button>
              </div>
            </div>

            <p className="mt-3 text-sm leading-relaxed text-slate-500">
              <span className="mr-2 text-[10px] font-semibold uppercase tracking-wider text-slate-600">
                Original
              </span>
              {segment.text_src}
            </p>

            <textarea
              className="input mt-2 min-h-[62px] resize-y leading-relaxed"
              value={draft}
              disabled={disabled || saving === segment.idx}
              onChange={(event) =>
                setDrafts((current) => ({ ...current, [segment.idx]: event.target.value }))
              }
              rows={2}
              placeholder="Traducción al español"
            />

            {segment.warning && (
              <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-300/80">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                {segment.warning}
              </p>
            )}

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] text-slate-600">
                {segment.tts_duration ? `Audio: ${segment.tts_duration.toFixed(1)}s · ` : ""}
                {segment.end - segment.start > 0
                  ? `Ventana: ${(segment.end - segment.start).toFixed(1)}s`
                  : ""}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="subtle"
                  onClick={() => save(segment)}
                  disabled={disabled || saving === segment.idx || !dirty}
                  loading={saving === segment.idx && !dirty}
                >
                  <Save size={13} /> Guardar
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => regenerate(segment)}
                  disabled={disabled || saving === segment.idx}
                  title="Genera de nuevo la voz de este segmento y actualiza el video"
                >
                  {saving === segment.idx ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <RefreshCw size={13} />
                  )}
                  Regenerar
                </Button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
