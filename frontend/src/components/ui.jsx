import { Link, useLocation } from "react-router-dom";
import { ALL_PAGES } from "../nav.js";
import { MapPin, Sprout, Volume2 } from "lucide-react";
import { useApp } from "../state.jsx";
import { cropName, t } from "../i18n.js";
import { FieldScene, CropIcon } from "./art.jsx";
import { C } from "./tokens.jsx";

const TONES = {
  leaf: "bg-[var(--leaf-50)] text-[var(--brand)]",
  gold: "bg-[var(--gold-50)] text-[#9a6a06]",
  sky: "bg-[var(--sky-50)] text-[var(--sky)]",
  soil: "bg-[var(--soil-50)] text-[var(--soil)]",
  red: "bg-red-50 text-[var(--status-critical)]",
};

export function IconBadge({ icon: Icon, tone = "leaf", size = 18 }) {
  if (!Icon) return null;
  return <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl ${TONES[tone]}`}><Icon size={size} strokeWidth={2.1} /></span>;
}

export function Card({ title, icon, tone = "leaf", children, className = "", actions }) {
  return (
    <section className={`k-card k-rise p-4 sm:p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="flex items-center gap-2 text-lg font-semibold leading-tight"><IconBadge icon={icon} tone={tone} />{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Page({ title, icon, subtitle, children, wide = false }) {
  const { pathname } = useLocation();
  icon = icon || ALL_PAGES.find((p) => p.path === pathname)?.icon;
  return (
    <div className={`mx-auto w-full ${wide ? "max-w-6xl" : "max-w-4xl"} space-y-4 px-4 py-5 sm:px-6`}>
      {title && (
        <div className="flex items-center gap-3">
          {icon && <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[var(--brand)] text-white shadow-sm">{(() => { const I = icon; return <I size={22} />; })()}</span>}
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold leading-tight">{title}</h1>
            {subtitle && <p className="truncate text-sm text-[var(--text-secondary)]">{subtitle}</p>}
          </div>
        </div>
      )}
      {children}
    </div>
  );
}

export function StatTile({ label, value, sub, icon, tone = "leaf" }) {
  return (
    <div className="k-card k-rise p-3.5">
      <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">{icon && <IconBadge icon={icon} tone={tone} size={15} />}{label}</div>
      <div className="font-display mt-1.5 text-2xl font-bold">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-[var(--text-muted)]">{sub}</div>}
    </div>
  );
}

export function Loading({ lines = 3 }) {
  const { lang } = useApp();
  return (
    <div className="space-y-2" aria-busy="true" aria-label={t("loading", lang)}>
      <div className="k-skeleton h-24" />
      {Array.from({ length: lines - 1 }).map((_, i) => <div key={i} className="k-skeleton h-4" style={{ width: `${85 - i * 20}%` }} />)}
    </div>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-2xl border border-[var(--status-critical)]/30 bg-red-50 px-4 py-2.5 text-sm text-red-900">
      {String(error.message || error)}
    </div>
  );
}

/** Shown when a page needs a field and none is chosen. */
export function NeedField({ children }) {
  const { fieldId, fields, selectField, lang } = useApp();
  if (fieldId) return children;
  return (
    <Page>
      <div className="k-card overflow-hidden">
        <FieldScene className="h-36 w-full" />
        <div className="space-y-3 p-5">
          <h2 className="text-xl font-bold">{t(fields.length ? "start.pick" : "start.title", lang)}</h2>
          {fields.length > 0 ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {fields.map((f) => (
                <button key={f.id} onClick={() => selectField(f.id)}
                        className="flex items-center gap-3 rounded-xl border border-black/10 bg-white p-3 text-left hover:border-[var(--leaf)]">
                  <IconBadge icon={Sprout} /><span><b>{f.name || "Field"}</b><span className="block text-xs text-[var(--text-muted)]">{f.area_ha?.toFixed(2)} ha · {f.district || ""}</span></span>
                </button>
              ))}
            </div>
          ) : (
            <Link to="/map" className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-4 py-2.5 text-white"><MapPin size={18} />{t("start.add", lang)}</Link>
          )}
        </div>
      </div>
    </Page>
  );
}

export function CropBadge({ season }) {
  const { lang } = useApp();
  if (!season?.crop) return <span className="text-[var(--text-muted)]">?</span>;
  const pct = season.crop_confidence != null ? Math.round(season.crop_confidence * 100) : null;
  const uncertain = season.crop_status === "uncertain";
  return (
    <span className="inline-flex items-center gap-1.5">
      <CropIcon crop={season.crop} size={20} />
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
    <select className="rounded-xl border border-black/10 bg-white px-3 py-2 text-sm shadow-sm" value={value || ""}
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
            className="inline-flex items-center gap-1 rounded-full border border-black/10 bg-white px-2.5 py-1 text-xs hover:border-[var(--leaf)]"><Volume2 size={14} /> {t("listen", lang)}</button>
  );
}

export const rs = (v) => (v == null ? "—" : `₹${Math.round(v).toLocaleString("en-IN")}`);
