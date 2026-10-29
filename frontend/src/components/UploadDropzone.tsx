import { useRef, useState } from "react";
import { FileVideo, Lock, UploadCloud, X } from "lucide-react";
import { uploadProject, ApiError } from "../api/client";
import type { Project } from "../api/types";
import { formatBytes } from "../lib/format";
import { Button, Progress } from "./ui";
import { useToast } from "./Toast";

export function UploadDropzone({
  maxMb,
  onUploaded,
}: {
  maxMb: number;
  onUploaded: (project: Project) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const pick = (selected: File | null | undefined) => {
    setError(null);
    if (!selected) return;
    if (!/\.(mp4|m4v)$/i.test(selected.name)) {
      setError({
        message: "Formato no soportado.",
        hint: "Selecciona un archivo MP4 (H.264 + AAC recomendado).",
      });
      return;
    }
    if (selected.size > maxMb * 1024 * 1024) {
      setError({
        message: `El archivo supera los ${maxMb} MB.`,
        hint: "Comprime el video o aumenta el límite en Ajustes.",
      });
      return;
    }
    setFile(selected);
    setName(selected.name.replace(/\.[^.]+$/, ""));
  };

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    setProgress(0);
    setError(null);
    try {
      const project = await uploadProject(file, name, setProgress);
      toast.push("Video subido", "Configura el doblaje para comenzar.", "success");
      onUploaded(project);
    } catch (err) {
      const apiError = err as ApiError;
      setError({ message: apiError.message, hint: apiError.hint ?? undefined });
      setUploading(false);
    }
  };

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!uploading) pick(event.dataTransfer.files?.[0]);
        }}
        className={`relative overflow-hidden rounded-2xl border border-dashed p-7 transition-all ${
          dragging
            ? "border-amber-400/70 bg-amber-400/[0.06]"
            : "border-white/15 bg-white/[0.015] hover:border-white/25 hover:bg-white/[0.03]"
        }`}
      >
        {!file ? (
          <div className="flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-amber-300">
              <UploadCloud size={24} />
            </div>
            <p className="text-[15px] font-medium text-slate-100">
              Arrastra tu video MP4 aquí
            </p>
            <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-slate-500">
              o selecciónalo desde tu equipo. Hasta {maxMb} MB. El procesamiento es local.
            </p>
            <Button
              variant="secondary"
              size="sm"
              className="mt-4"
              onClick={() => inputRef.current?.click()}
            >
              Elegir archivo
            </Button>
            <p className="mt-4 flex items-center gap-1.5 text-[10px] text-slate-600">
              <Lock size={10} /> El video nunca se sube a internet
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300">
              <FileVideo size={22} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-slate-100">{file.name}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                {formatBytes(file.size)} · MP4
              </p>
              {uploading && (
                <div className="mt-2.5">
                  <Progress value={progress} tone="amber" />
                  <p className="mt-1.5 text-[11px] text-amber-300/80">
                    Subiendo… {Math.round(progress)}%
                  </p>
                </div>
              )}
            </div>
            {!uploading && (
              <button
                onClick={() => {
                  setFile(null);
                  if (inputRef.current) inputRef.current.value = "";
                }}
                className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-slate-200"
                aria-label="Quitar archivo"
              >
                <X size={16} />
              </button>
            )}
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,.mp4,.m4v"
          className="hidden"
          onChange={(event) => pick(event.target.files?.[0])}
        />
      </div>

      {file && !uploading && (
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1">
            <span className="label mb-2 block">Nombre del proyecto</span>
            <input
              className="input"
              value={name}
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              placeholder="Mi video"
            />
          </label>
          <Button variant="primary" onClick={upload} disabled={!name.trim()}>
            <UploadCloud size={16} /> Subir y configurar
          </Button>
        </div>
      )}

      {error && (
        <div className="mt-4 rounded-xl border border-red-500/25 bg-red-500/[0.07] px-4 py-3">
          <p className="text-sm font-medium text-red-200">{error.message}</p>
          {error.hint && <p className="mt-1 text-xs text-red-200/60">{error.hint}</p>}
        </div>
      )}
    </div>
  );
}
