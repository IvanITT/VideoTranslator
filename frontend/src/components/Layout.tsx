import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  AudioLines,
  Boxes,
  Cpu,
  HardDrive,
  LayoutDashboard,
  Lock,
  Settings,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useHealth, useSystem } from "../hooks/useApi";
import { Badge } from "./ui";

const NAV = [
  { to: "/", label: "Panel", icon: LayoutDashboard, end: true },
  { to: "/models", label: "Modelos", icon: Boxes },
  { to: "/settings", label: "Ajustes", icon: Settings },
];

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${
              isActive
                ? "bg-amber-400/[0.09] text-amber-200 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.16)]"
                : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
            }`
          }
        >
          {({ isActive }) => (
            <>
              <item.icon
                size={17}
                className={isActive ? "text-amber-400" : "text-slate-500 group-hover:text-slate-300"}
              />
              {item.label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export function Layout() {
  const health = useHealth();
  const system = useSystem();
  const location = useLocation();
  const hw = system.data?.hardware;
  const isStudio = location.pathname.startsWith("/projects/");

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[264px] flex-col border-r border-white/[0.06] bg-ink-950/80 px-4 py-5 backdrop-blur-xl lg:flex">
        <NavLink to="/" className="mb-8 flex items-center gap-3 px-2">
          <span className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-300 to-amber-500 text-ink-950 shadow-lg shadow-amber-500/20">
            <AudioLines size={21} strokeWidth={2.4} />
            <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-ink-950 bg-emerald-400" />
          </span>
          <span>
            <span className="block text-[15px] font-semibold leading-tight tracking-tight text-white">
              Doblaje Studio
            </span>
            <span className="block text-[10px] font-medium uppercase tracking-[0.22em] text-slate-500">
              IA local · es-MX
            </span>
          </span>
        </NavLink>

        <NavItems />
        {isStudio && (
          <NavLink
            to="/"
            className="mt-3 flex items-center gap-3 rounded-xl px-3 py-2 text-xs text-slate-500 hover:bg-white/[0.04] hover:text-slate-300"
          >
            <Sparkles size={14} /> Nuevo proyecto
          </NavLink>
        )}

        <div className="mt-auto space-y-3">
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Hardware
              </span>
              <Badge tone={hw?.gpu?.available ? "green" : "slate"} dot>
                {hw?.gpu?.available ? "GPU" : "CPU"}
              </Badge>
            </div>
            <div className="mt-2.5 space-y-1.5 text-[11px] text-slate-400">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-slate-500">
                  <Cpu size={11} /> RAM
                </span>
                <span className="font-mono text-slate-300">
                  {hw ? `${hw.ram_used_gb ?? "—"}/${hw.ram_total_gb} GB` : "—"}
                </span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                <div
                  className="h-full rounded-full bg-amber-400/70 transition-all"
                  style={{ width: `${Math.min(100, hw?.ram_percent ?? 0)}%` }}
                />
              </div>
              <div className="flex items-center justify-between pt-0.5">
                <span className="flex items-center gap-1.5 text-slate-500">
                  <HardDrive size={11} /> Libre
                </span>
                <span className="font-mono text-slate-300">
                  {hw ? `${hw.disk_free_gb} GB` : "—"}
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-emerald-400/10 bg-emerald-400/[0.035] p-3">
            <div className="flex items-center gap-2 text-[11px] font-medium text-emerald-300">
              <ShieldCheck size={13} /> 100% local
            </div>
            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
              Tus videos y transcripciones nunca salen de este equipo.
            </p>
          </div>

          <div className="flex items-center justify-between px-1 text-[10px] text-slate-600">
            <span className="flex items-center gap-1.5">
              <Lock size={10} /> 127.0.0.1
            </span>
            <span>v{health.data?.version ?? "1.0.0"}</span>
          </div>
        </div>
      </aside>

      <div className="lg:pl-[264px]">
        <header className="sticky top-0 z-30 border-b border-white/[0.05] bg-ink-950/80 backdrop-blur-xl">
          <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-8">
            <div className="flex items-center gap-3 lg:hidden">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-300 to-amber-500 text-ink-950">
                <AudioLines size={16} />
              </span>
              <span className="text-sm font-semibold text-white">Doblaje Studio</span>
            </div>
            <div className="hidden items-center gap-2 text-xs text-slate-500 lg:flex">
              <AudioLines size={14} className="text-amber-400/70" />
              Traducción y doblaje al español con modelos locales
            </div>
            <div className="flex items-center gap-2">
              <Badge
                tone={
                  health.data?.status === "ok"
                    ? "green"
                    : health.data?.status === "degraded"
                      ? "amber"
                      : health.data
                        ? "red"
                        : "slate"
                }
                dot
              >
                {health.data?.status === "ok"
                  ? "Sistema listo"
                  : health.data?.status === "degraded"
                    ? "Revisar configuración"
                    : health.data
                      ? "Con errores"
                      : "Conectando…"}
              </Badge>
              <span className="hidden rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-slate-400 sm:inline">
                Sin nube
              </span>
            </div>
          </div>
          <div className="flex gap-1 overflow-x-auto border-t border-white/[0.04] px-3 py-2 lg:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs ${
                    isActive ? "bg-amber-400/10 text-amber-300" : "text-slate-400"
                  }`
                }
              >
                <item.icon size={14} /> {item.label}
              </NavLink>
            ))}
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1320px] px-4 py-7 sm:px-8 sm:py-9">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
