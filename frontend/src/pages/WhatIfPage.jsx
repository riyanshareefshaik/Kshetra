import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { C, GapBar, axisProps } from "../components/tokens.jsx";
import { Card, ErrorBox, Loading, NeedField, Page, StatTile, rs } from "../components/ui.jsx";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

const IRRIGATION = { rainfed: "Rainfed", supplemental: "Some irrigation", full: "Full irrigation" };
const RISK_ICON = { low: "●", medium: "▲", high: "■" };
const RISK_COLOR = { low: C.good, medium: C.warning, high: C.critical };

function md(mmdd, offsetDays) {
  const [m, d] = mmdd.split("-").map(Number);
  const dt = new Date(Date.UTC(2001, m - 1, d + offsetDays));
  return `${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
}
const label = (mmdd) => new Date(`2001-${mmdd}T00:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });

export default function WhatIfPage() {
  return <NeedField><WhatIf /></NeedField>;
}

function WhatIf() {
  const { fieldId, field, lang } = useApp();
  const [varieties, setVarieties] = useState(null);
  const [key, setKey] = useState(null);                 // "crop|season|variety"
  const [offset, setOffset] = useState(0);
  const [n, setN] = useState(120);
  const [irrigation, setIrrigation] = useState("rainfed");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const ctrl = useRef(null);

  useEffect(() => {
    api.varieties().then((v) => {
      setVarieties(v);
      const first = v.find((x) => x.crop === "paddy" && x.season === "kharif") || v[0];
      if (first) { setKey(`${first.crop}|${first.season}|${first.variety}`); setN(first.recommended_n_kg_ha || 0); }
    }).catch(setError);
  }, []);

  const v = useMemo(() => varieties?.find((x) => `${x.crop}|${x.season}|${x.variety}` === key), [varieties, key]);
  const sowing = v ? md(v.sowing_window_start, offset) : null;

  useEffect(() => {
    if (!v) return undefined;
    const timer = setTimeout(async () => {
      ctrl.current?.abort();
      ctrl.current = new AbortController();
      setBusy(true);
      try {
        setResult(await api.whatIf(fieldId, { crop: v.crop, season: v.season, variety: v.variety, sowing_date: sowing,
                                              n_kg_ha: n, irrigation }, ctrl.current.signal));
        setError(null);
      } catch (e) {
        if (e.name !== "AbortError") { setError(e); setResult(null); }
      } finally {
        setBusy(false);
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [fieldId, v, sowing, n, irrigation]);

  if (!varieties) return <Page><ErrorBox error={error} /><Loading /></Page>;
  const windowDays = v ? Math.round((new Date(`2001-${v.sowing_window_end}`) - new Date(`2001-${v.sowing_window_start}`)) / 864e5 + 365) % 365 : 60;

  return (
    <Page title={t("whatIf", lang)} wide>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <Card title="Your plan">
          <div className="space-y-4 text-sm">
            <label className="block">{t("crop", lang)} & variety
              <select className="mt-1 w-full rounded border border-black/15 px-2 py-1" value={key || ""}
                      onChange={(e) => { setKey(e.target.value); setOffset(0); const nv = varieties.find((x) => `${x.crop}|${x.season}|${x.variety}` === e.target.value); setN(nv?.recommended_n_kg_ha || 0); }}>
                {varieties.map((x) => {
                  const k = `${x.crop}|${x.season}|${x.variety}`;
                  return <option key={k} value={k}>{x.crop} · {x.variety} ({x.season})</option>;
                })}
              </select>
            </label>
            <label className="block">{t("sowing", lang)}: <b>{sowing && label(sowing)}</b>
              <input type="range" className="mt-1 w-full accent-[var(--series-1)]" min={-30} max={windowDays + 30} step={1}
                     value={offset} onChange={(e) => setOffset(Number(e.target.value))} />
              <span className="text-xs text-[var(--text-muted)]">Recommended window: {v && `${label(v.sowing_window_start)} – ${label(v.sowing_window_end)}`}</span>
            </label>
            <label className="block">Nitrogen: <b className="tabular">{n} kg/ha</b> <span className="text-[var(--text-muted)]">(≈ {Math.round(n / 0.46 / 45 * 10) / 10} bags urea/ha)</span>
              <input type="range" className="mt-1 w-full accent-[var(--series-1)]" min={0} max={300} step={5}
                     value={n} onChange={(e) => setN(Number(e.target.value))} />
              <span className="text-xs text-[var(--text-muted)]">Recommended: {v?.recommended_n_kg_ha} kg/ha</span>
            </label>
            <fieldset>
              <legend>Irrigation</legend>
              <div className="mt-1 flex flex-wrap gap-1">
                {Object.entries(IRRIGATION).map(([k, lab]) => (
                  <button key={k} onClick={() => setIrrigation(k)}
                          className={`rounded border px-2 py-1 ${irrigation === k ? "border-[var(--brand)] bg-[var(--brand)] text-white" : "border-black/15"}`}>{lab}</button>
                ))}
              </div>
            </fieldset>
          </div>
        </Card>

        <div className="space-y-4">
          <ErrorBox error={error} />
          {!result ? (busy ? <Loading /> : null) : (
            <>
              <div className={`grid grid-cols-1 gap-3 sm:grid-cols-3 transition-opacity ${busy ? "opacity-60" : ""}`}>
                <StatTile label={t("yieldRange", lang)} value={`${result.yield_t_ha.low.toFixed(1)}–${result.yield_t_ha.high.toFixed(1)}`}
                          sub={`t/ha · middle ${result.yield_t_ha.mid.toFixed(1)}`} />
                <StatTile label={t("risk", lang)}
                          value={<span className="capitalize"><span style={{ color: RISK_COLOR[result.risk.level] }} aria-hidden>{RISK_ICON[result.risk.level]} </span>{result.risk.level}</span>}
                          sub={`Past years: ${Math.round(result.risk.share_of_years_low_yield * 100)}% low yield · ${Math.round(result.risk.share_of_years_long_dry_spell * 100)}% long dry spell · ${Math.round(result.risk.share_of_years_heavy_rain_near_harvest * 100)}% heavy rain before harvest`} />
                <StatTile label={`${t("profit", lang)} / ha`} value={rs(result.profit.mid_rs_ha)}
                          sub={result.profit.mid_rs_ha != null ? `${rs(result.profit.low_rs_ha)} to ${rs(result.profit.high_rs_ha)}${result.profit.mid_rs_field != null ? ` · whole field ${rs(result.profit.mid_rs_field)}` : ""}` : result.profit.price.source} />
              </div>
              <Card title={`If you had grown this in each past year (${field?.name || "this field"})`}>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={result.per_year} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                    <CartesianGrid stroke={C.grid} vertical={false} />
                    <XAxis dataKey="year" {...axisProps} />
                    <YAxis {...axisProps} unit=" t" />
                    <Bar dataKey="yield_mid_t_ha" fill={C.series1} radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false} />
                    <Tooltip cursor={{ fill: C.band }} formatter={(val) => [`${val.toFixed(2)} t/ha (middle estimate)`, "Yield"]} />
                  </BarChart>
                </ResponsiveContainer>
                <p className="text-xs text-[var(--text-muted)]">Each bar replays that year's real weather on this field.</p>
              </Card>
              <Card title="How this was worked out">
                <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
                  {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                  <li>Price: ₹{result.profit.price.rs_per_qtl?.toLocaleString("en-IN") ?? "—"}/quintal ({result.profit.price.source}). Costs ₹{result.profit.cost_rs_ha.toLocaleString("en-IN")}/ha: {result.profit.cost_note}</li>
                  <li>Yield method: {result.method === "model" ? "trained yield model" : "district yield history with weather penalties"}; computed in {result.elapsed_ms} ms.</li>
                </ul>
              </Card>
            </>
          )}
        </div>
      </div>
    </Page>
  );
}
