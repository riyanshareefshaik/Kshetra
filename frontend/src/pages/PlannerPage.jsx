import { useEffect, useState } from "react";
import { api } from "../api.js";
import { C } from "../components/tokens.jsx";
import { Card, ErrorBox, Loading, NeedField, Page, RangeBar, rs } from "../components/ui.jsx";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

const RISK_COLOR = { low: C.good, medium: C.warning, high: C.critical };
const md = (mmdd) => new Date(`2001-${mmdd}T00:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
const window_ = (w) => w.split(" to ").map(md).join(" – ");
const RISK_ICON = { low: "●", medium: "▲", high: "■" };

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
    <Page title={t("planner", lang)}>
      <div className="flex items-center gap-2 text-sm">
        <span>Season</span>
        {["", "kharif", "rabi", "zaid"].map((s) => (
          <button key={s} onClick={() => setSeason(s)}
                  className={`rounded border px-2.5 py-1 capitalize ${season === s ? "border-[var(--brand)] bg-[var(--brand)] text-white" : "border-black/15 bg-white"}`}>
            {s || "next"}
          </button>
        ))}
      </div>
      <ErrorBox error={error} />
      {!plan ? <Loading /> : plan.options.length === 0 ? (
        <Card><p className="text-sm text-[var(--text-secondary)]">No options could be simulated yet. The field needs at least one year of weather and district yield data (or a trained model).</p></Card>
      ) : (
        <>
          <p className="text-sm text-[var(--text-secondary)]">Best options for <b className="capitalize">{plan.season}</b>{plan.year ? ` ${plan.year}` : ""} on this field. {plan.note}</p>
          <div className="grid gap-3 md:grid-cols-3">
            {plan.options.map((o, i) => (
              <Card key={`${o.crop}-${o.variety}`} title={<span><span className="text-[var(--text-muted)]">#{i + 1}</span> <span className="capitalize">{o.crop}</span></span>}>
                <div className="space-y-2 text-sm">
                  <div className="text-[var(--text-secondary)]">{o.variety} · {o.duration_days} days</div>
                  <div><div className="text-xs text-[var(--text-secondary)]">{t("sowing", lang)} window</div>{window_(o.sowing_window)}</div>
                  <div><div className="text-xs text-[var(--text-secondary)]">{t("yieldRange", lang)}</div>
                    <RangeBar low={o.yield_t_ha.low} mid={o.yield_t_ha.mid} high={o.yield_t_ha.high} max={maxY} /></div>
                  <div><div className="text-xs text-[var(--text-secondary)]">{t("profit", lang)} per ha</div>
                    <span className="text-lg font-semibold">{rs(o.profit.mid_rs_ha)}</span>
                    {o.profit.mid_rs_ha != null && <span className="text-xs text-[var(--text-muted)]"> ({rs(o.profit.low_rs_ha)} to {rs(o.profit.high_rs_ha)})</span>}
                  </div>
                  <div className="capitalize"><span aria-hidden style={{ color: RISK_COLOR[o.risk.level] }}>{RISK_ICON[o.risk.level]} </span>{o.risk.level} risk</div>
                  <details className="text-xs text-[var(--text-muted)]"><summary>Assumptions</summary>
                    <ul className="mt-1 list-disc pl-4">{o.assumptions.map((a, j) => <li key={j}>{a}</li>)}<li>{o.profit.price.source}</li></ul>
                  </details>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </Page>
  );
}
