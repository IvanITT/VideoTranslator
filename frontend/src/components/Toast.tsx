import { createContext, useCallback, useContext, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useToastQueue } from "../hooks/useApi";

type Tone = "error" | "success" | "info";

interface ToastApi {
  push: (title: string, description?: string, tone?: Tone) => void;
}

const ToastContext = createContext<ToastApi>({ push: () => undefined });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const { toasts, push, dismiss } = useToastQueue();

  const stablePush = useCallback(
    (title: string, description?: string, tone: Tone = "info") => push(title, description, tone),
    [push],
  );

  return (
    <ToastContext.Provider value={{ push: stablePush }}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[100] flex w-[min(92vw,380px)] flex-col gap-2">
        {toasts.map((toast) => {
          const Icon = toast.tone === "error" ? AlertTriangle : toast.tone === "success" ? CheckCircle2 : Info;
          const tone =
            toast.tone === "error"
              ? "border-red-500/30 bg-red-950/90"
              : toast.tone === "success"
                ? "border-emerald-500/25 bg-emerald-950/90"
                : "border-white/10 bg-ink-850/95";
          return (
            <div
              key={toast.id}
              className={`pointer-events-auto flex items-start gap-3 rounded-xl border p-3.5 shadow-2xl backdrop-blur ${tone}`}
            >
              <Icon
                size={17}
                className={
                  toast.tone === "error"
                    ? "mt-0.5 text-red-400"
                    : toast.tone === "success"
                      ? "mt-0.5 text-emerald-400"
                      : "mt-0.5 text-amber-400"
                }
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-100">{toast.title}</p>
                {toast.description && (
                  <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{toast.description}</p>
                )}
              </div>
              <button
                onClick={() => dismiss(toast.id)}
                className="rounded-md p-1 text-slate-500 hover:bg-white/5 hover:text-slate-300"
                aria-label="Cerrar notificación"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
