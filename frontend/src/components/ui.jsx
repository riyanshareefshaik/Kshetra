import { useApp } from "../state.jsx";
import { cropName, t } from "../i18n.js";
import { C } from "./tokens.jsx";

export function Card({ title, children, className = "", actions }) {
  return (
    <section className={`rounded-lg border border-black/10 bg-[var(--surface-1)] p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Page({ title, children, wide = false }) {
  return (
    <div className={`mx-auto w-full ${wide ? "max-w-6xl" : "max-w-4xl"} space-y-4 px-4 py-5`}>
      {title && <h1 className="text-xl font-semibold">{title}</h1>}
      {children}
    </div>
  );
}

export function StatTile({ label, value, sub }) {
  return (
    <div className="rounded-lg border border-black/10 bg-[var(--surface-1)] p-3">
      <div className="text-xs text-[var(--text-secondary)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-[var(--text-muted)]">{sub}</div>}
    </div>
  );
}

export function Loading() {
  const { lang } = useApp();
  return <p className="text-sm text-[var(--text-secondary)]">{t("loading", lang)}</p>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border border-[var(--status-critical)]/40 bg-red-50 px-3 py-2 text-sm text-red-900">
      {String(error.message || error)}
    </div>
  );
}

export function NeedField({ children }) {
  const { fieldId, lang } = useApp();
  if (!fieldId) {
    return <Page><Card><p className="text-[var(--text-secondary)]">{t("noField", lang)}</p></Card></Page>;
  }
  return children;
}

export function CropBadge({ season }) {
  const { lang } = useApp();
  if (!season?.crop) return <span className="text-[var(--text-muted)]">?</span>;
  const pct = season.crop_confidence != null ? Math.round(season.crop_confidence * 100) : null;
  const uncertain = season.crop_status === "uncertain";
  return (
    <span className="inline-flex items-center gap-1">
      <span className="font-medium">{cropName(season.crop, lang)}</span>
      {season.crop_confirmed_by_farmer ? (
        <span className="rounded bg-green-50 px-1 text-[11px] text-green-800">✓ {t("confirmedByFarmer", lang)}</span>
      ) : pct != null && (
        <span className={`rounded px-1 text-[11px] ${uncertain ? "bg-amber-50 text-amber-900" : "bg-green-50 text-green-800"}`}>
          {pct}%{uncertain ? ` · ${t("uncertain", lang)}` : ""}
        </span>
      )}
    </span>
  );
}

const EVENT_STYLE = {
  dry_spell: { icon: "☀", color: C.serious },
  waterlogging: { icon: "≋", color: C.warning },
  flood: { icon: "≋", color: C.critical },
  heat_stress: { icon: "▲", color: C.serious },
  sudden_damage: { icon: "✕", color: C.critical },
};

export function eventStyle(type) {
  return EVENT_STYLE[type] || { icon: "•", color: C.muted };
}

export function EventTag({ event }) {
  const { lang } = useApp();
  const s = eventStyle(event.event_type);
  return (
    <span className="inline-flex items-center gap-1 text-sm">
      <span aria-hidden style={{ color: s.color }}>{s.icon}</span>
      <span>{t(`ev.${event.event_type}`, lang)}</span>
    </span>
  );
}

const LEVEL = {
  critical: { icon: "■", color: C.critical }, high: { icon: "■", color: C.critical },
  warning: { icon: "▲", color: C.warning }, medium: { icon: "▲", color: C.warning },
  info: { icon: "●", color: C.series1 }, low: { icon: "●", color: C.good },
};

/** Status shape + colour; always shown next to a text label. */
export function LevelIcon({ level }) {
  const l = LEVEL[level] || LEVEL.info;
  return <span aria-hidden style={{ color: l.color }}>{l.icon}</span>;
}

export function RangeBar({ low, mid, high, max }) {
  const { lang } = useApp();
  if (low == null || high == null) return <span className="text-[var(--text-muted)]">—</span>;
  const pct = (v) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div className="flex items-center gap-2" title={`${low} – ${high} (${mid})`}>
      <div className="relative h-3 w-28 rounded-full bg-[var(--grid)]">
        <div className="absolute top-0 h-3 rounded-full bg-[var(--series-1)]/35"
             style={{ left: pct(low), width: `calc(${pct(high)} - ${pct(low)})` }} />
        <div className="absolute top-[-2px] h-4 w-0.5 bg-[var(--series-1)]" style={{ left: pct(mid) }} />
      </div>
      <span className="tabular text-sm">{low.toFixed(1)}–{high.toFixed(1)} <span className="text-[var(--text-muted)]">{t("tHa", lang)}</span></span>
    </div>
  );
}

export function SeasonSelect({ seasons, value, onChange }) {
  const { lang } = useApp();
  return (
    <select className="rounded border border-black/15 bg-white px-2 py-1 text-sm" value={value || ""}
            onChange={(e) => onChange(e.target.value)}>
      {seasons.map((s) => (
        <option key={s.id} value={s.id}>
          {t(s.season, lang)} {s.year} · {cropName(s.crop, lang)}{s.in_progress ? ` (${t("inField", lang)})` : ""}
        </option>
      ))}
    </select>
  );
}

export function ListenButton({ text }) {
  const { lang } = useApp();
  return (
    <button onClick={() => import("./speech.js").then((m) => m.speak(text, lang)).catch(() => {})}
            className="rounded border border-black/10 px-2 py-0.5 text-xs">🔊 {t("listen", lang)}</button>
  );
}

export const rs = (v) => (v == null ? "—" : `₹${Math.round(v).toLocaleString("en-IN")}`);
