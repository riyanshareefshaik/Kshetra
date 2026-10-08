import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, LevelIcon, Loading, NeedField, Page, RangeBar, rs } from "../components/ui.jsx";
import { cropName, fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

const dayLabel = (mmdd, lang) => fmtDate(`2001-${mmdd}T00:00:00Z`, lang, { day: "numeric", month: "short", timeZone: "UTC" });

export default function PlannerPage() {
  return <NeedField><Planner /></NeedField>;
}

function Planner() {
  const { fieldId, lang } = useApp();
  const [season, setSeason] = useState("");
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setPlan(null);
    api.plan(fieldId, season || undefined).then((p) => { setPlan(p); setError(null); }).catch(setError);
  }, [fieldId, season]);

  const maxY = Math.max(1, ...(plan?.options || []).map((o) => o.yield_t_ha?.high || 0));
  return (
    <Page title={t("pl.title", lang)}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span>{t("season", lang)}</span>
        {["", "kharif", "rabi", "zaid"].map((s) => (
          <button key={s} onClick={() => setSeason(s)}
                  className={`rounded border px-2.5 py-1 ${season === s ? "border-[var(--brand)] bg-[var(--brand)] text-white" : "border-black/15 bg-white"}`}>
            {t(s || "next", lang)}
          </button>
        ))}
      </div>
      <ErrorBox error={error} />
      {!plan ? <Loading /> : plan.options.length === 0 ? (
        <Card><p className="text-sm text-[var(--text-secondary)]">{t("pl.none", lang)}</p></Card>
      ) : (
        <>
          <p className="text-sm text-[var(--text-secondary)]">{t("pl.best", lang, { season: `${t(plan.season, lang)}${plan.year ? ` ${plan.year}` : ""}` })}</p>
          <div className="grid gap-3 md:grid-cols-3">
            {plan.options.map((o, i) => {
              const [from, to] = o.sowing_window.split(" to ");
              return (
                <Card key={`${o.crop}-${o.variety}`} title={<span><span className="text-[var(--text-muted)]">#{i + 1}</span> {cropName(o.crop, lang)}</span>}>
                  <div className="space-y-2 text-sm">
                    <div className="text-[var(--text-secondary)]">{o.variety} · {o.duration_days} {t("days", lang)}</div>
                    <div><div className="text-xs text-[var(--text-secondary)]">{t("pl.window", lang)}</div>{dayLabel(from, lang)} – {dayLabel(to, lang)}</div>
                    <div><div className="text-xs text-[var(--text-secondary)]">{t("yieldRange", lang)}</div>
                      <RangeBar low={o.yield_t_ha.low} mid={o.yield_t_ha.mid} high={o.yield_t_ha.high} max={maxY} /></div>
                    <div><div className="text-xs text-[var(--text-secondary)]">{t("profit", lang)} ({t("perHa", lang)})</div>
                      <span className="text-lg font-semibold">{rs(o.profit.mid_rs_ha)}</span>
                      {o.profit.mid_rs_ha != null && <span className="text-xs text-[var(--text-muted)]"> ({rs(o.profit.low_rs_ha)} – {rs(o.profit.high_rs_ha)})</span>}
                    </div>
                    <div><LevelIcon level={o.risk.level} /> {t("pl.riskLevel", lang, { level: t(o.risk.level, lang) })}</div>
                    <details className="text-xs text-[var(--text-muted)]"><summary>{t("pl.assumptions", lang)}</summary>
                      <ul className="mt-1 list-disc pl-4" lang="en">{o.assumptions.map((a, j) => <li key={j}>{a}</li>)}<li>{o.profit.price.source}</li></ul>
                    </details>
                  </div>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </Page>
  );
}
