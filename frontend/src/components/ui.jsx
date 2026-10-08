import { useApp } from "../state.jsx";
import { t } from "../i18n.js";
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
    return (
      <Page>
        <Card>
          <p className="text-[var(--text-secondary)]">{t("noField", lang)}</p>
        </Card>
      </Page>
    );
  }
  return children;
}

export function SyntheticBadge({ show }) {
  const { lang } = useApp();
  if (!show) return null;
  return (
    <span className="rounded border border-[var(--status-critical)] px-1.5 py-0.5 text-[11px] font-semibold text-[var(--status-critical)]">
      ⚠ {t("synthetic", lang)}
    </span>
  );
}

export function CropBadge({ season }) {
  const { lang } = useApp();
  if (!season?.crop) return <span className="text-[var(--text-muted)]">?</span>;
  const pct = season.crop_confidence != null ? Math.round(season.crop_confidence * 100) : null;
  const uncertain = season.crop_status === "uncertain";
  return (
    <span className="inline-flex items-center gap-1">
      <span className="font-medium capitalize">{season.crop}</span>
      {season.crop_confirmed_by_farmer ? (
        <span className="rounded bg-green-50 px-1 text-[11px] text-green-800">✓ farmer</span>
      ) : (
        pct != null && (
          <span className={`rounded px-1 text-[11px] ${uncertain ? "bg-amber-50 text-amber-900" : "bg-green-50 text-green-800"}`}>
            {pct}%{uncertain ? ` · ${t("uncertain", lang)}` : ""}
          </span>
        )
      )}
    </span>
  );
}

const EVENT_STYLE = {
  dry_spell: { icon: "☀", label: "Dry spell", color: C.serious },
  waterlogging: { icon: "≋", label: "Waterlogging", color: C.warning },
  flood: { icon: "≋", label: "Flood", color: C.critical },
  heat_stress: { icon: "▲", label: "Heat stress", color: C.serious },
  sudden_damage: { icon: "✕", label: "Sudden damage", color: C.critical },
};

export function eventStyle(type) {
  return EVENT_STYLE[type] || { icon: "•", label: type.replace(/_/g, " "), color: C.muted };
}

export function EventTag({ event }) {
  const s = eventStyle(event.event_type);
  return (
    <span className="inline-flex items-center gap-1 text-sm">
      <span aria-hidden style={{ color: s.color }}>{s.icon}</span>
      <span>{s.label}</span>
    </span>
  );
}

/** Low–mid–high on a shared scale: a thin range with a mid tick. */
export function RangeBar({ low, mid, high, max, unit = "t/ha" }) {
  if (low == null || high == null) return <span className="text-[var(--text-muted)]">—</span>;
  const pct = (v) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div className="flex items-center gap-2" title={`${low} – ${high} ${unit} (mid ${mid})`}>
      <div className="relative h-3 w-32 rounded-full bg-[var(--grid)]">
        <div className="absolute top-0 h-3 rounded-full bg-[var(--series-1)]/35"
             style={{ left: pct(low), width: `calc(${pct(high)} - ${pct(low)})` }} />
        <div className="absolute top-[-2px] h-4 w-0.5 bg-[var(--series-1)]" style={{ left: pct(mid) }} />
      </div>
      <span className="tabular text-sm">{low.toFixed(1)}–{high.toFixed(1)} <span className="text-[var(--text-muted)]">{unit}</span></span>
    </div>
  );
}

export function SeasonSelect({ seasons, value, onChange }) {
  return (
    <select className="rounded border border-black/15 bg-white px-2 py-1 text-sm" value={value || ""}
            onChange={(e) => onChange(e.target.value)}>
      {seasons.map((s) => (
        <option key={s.id} value={s.id}>
          {s.season} {s.year} · {s.crop || "?"}{s.in_progress ? " (now)" : ""}
        </option>
      ))}
    </select>
  );
}

export const rs = (v) => (v == null ? "—" : `₹${Math.round(v).toLocaleString("en-IN")}`);
