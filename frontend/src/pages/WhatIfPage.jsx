import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { C, axisProps } from "../components/tokens.jsx";
import { Card, ErrorBox, LevelIcon, Loading, NeedField, Page, StatTile, rs } from "../components/ui.jsx";
import { cropName, fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

const IRRIGATION = ["rainfed", "supplemental", "full"];

function md(mmdd, offsetDays) {
  const [m, d] = mmdd.split("-").map(Number);
  const dt = new Date(Date.UTC(2001, m - 1, d + offsetDays));
  return `${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
}
const dayLabel = (mmdd, lang) => fmtDate(`2001-${mmdd}T00:00:00Z`, lang, { day: "numeric", month: "short", timeZone: "UTC" });

export default function WhatIfPage() {
  return <NeedField><WhatIf /></NeedField>;
}

function WhatIf() {
  const { fieldId, lang } = useApp();
  const [varieties, setVarieties] = useState(null);
  const [key, setKey] = useState(null);
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
  const r = result;

  return (
    <Page title={t("wi.title", lang)} wide>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <Card title={t("wi.plan", lang)}>
          <div className="space-y-4 text-sm">
            <label className="block">{t("wi.cropVariety", lang)}
              <select className="mt-1 w-full rounded border border-black/15 px-2 py-1" value={key || ""}
                      onChange={(e) => { setKey(e.target.value); setOffset(0); const nv = varieties.find((x) => `${x.crop}|${x.season}|${x.variety}` === e.target.value); setN(nv?.recommended_n_kg_ha || 0); }}>
                {varieties.map((x) => {
                  const k = `${x.crop}|${x.season}|${x.variety}`;
                  return <option key={k} value={k}>{cropName(x.crop, lang)} · {x.variety} ({t(x.season, lang)})</option>;
                })}
              </select>
            </label>
            <label className="block">{t("sowing", lang)}: <b>{sowing && dayLabel(sowing, lang)}</b>
              <input type="range" className="mt-1 w-full accent-[var(--series-1)]" min={-30} max={windowDays + 30} step={1}
                     value={offset} onChange={(e) => setOffset(Number(e.target.value))} />
              <span className="text-xs text-[var(--text-muted)]">{v && t("wi.window", lang, { from: dayLabel(v.sowing_window_start, lang), to: dayLabel(v.sowing_window_end, lang) })}</span>
            </label>
            <label className="block">{t("wi.nitrogen", lang)}: <b className="tabular">{n} kg/ha</b> <span className="text-[var(--text-muted)]">({t("wi.bags", lang, { n: Math.round(n / 0.46 / 45 * 10) / 10 })})</span>
              <input type="range" className="mt-1 w-full accent-[var(--series-1)]" min={0} max={300} step={5}
                     value={n} onChange={(e) => setN(Number(e.target.value))} />
              <span className="text-xs text-[var(--text-muted)]">{t("wi.recommended", lang, { n: v?.recommended_n_kg_ha })}</span>
            </label>
            <fieldset>
              <legend>{t("map.irrigation", lang)}</legend>
              <div className="mt-1 flex flex-wrap gap-1">
                {IRRIGATION.map((k) => (
                  <button key={k} onClick={() => setIrrigation(k)}
                          className={`rounded border px-2 py-1 ${irrigation === k ? "border-[var(--brand)] bg-[var(--brand)] text-white" : "border-black/15"}`}>{t(`irr.${k}`, lang)}</button>
                ))}
              </div>
            </fieldset>
          </div>
        </Card>

        <div className="space-y-4">
          <ErrorBox error={error} />
          {!r ? (busy ? <Loading /> : null) : (
            <>
              <div className={`grid grid-cols-1 gap-3 transition-opacity sm:grid-cols-3 ${busy ? "opacity-60" : ""}`}>
                <StatTile label={t("yieldRange", lang)} value={`${r.yield_t_ha.low.toFixed(1)}–${r.yield_t_ha.high.toFixed(1)}`}
                          sub={t("wi.middle", lang, { n: r.yield_t_ha.mid.toFixed(1) })} />
                <StatTile label={t("risk", lang)}
                          value={<span><LevelIcon level={r.risk.level} /> {t(r.risk.level, lang)}</span>}
                          sub={t("wi.riskSub", lang, { a: Math.round(r.risk.share_of_years_low_yield * 100), b: Math.round(r.risk.share_of_years_long_dry_spell * 100), c: Math.round(r.risk.share_of_years_heavy_rain_near_harvest * 100) })} />
                <StatTile label={`${t("profit", lang)} (${t("perHa", lang)})`} value={rs(r.profit.mid_rs_ha)}
                          sub={r.profit.mid_rs_ha != null ? t("wi.profitSub", lang, { low: rs(r.profit.low_rs_ha), high: rs(r.profit.high_rs_ha), field: rs(r.profit.mid_rs_field) }) : r.profit.price.source} />
              </div>
              <Card title={t("wi.eachYear", lang)}>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={r.per_year} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                    <CartesianGrid stroke={C.grid} vertical={false} />
                    <XAxis dataKey="year" {...axisProps} />
                    <YAxis {...axisProps} unit=" t" />
                    <Bar dataKey="yield_mid_t_ha" fill={C.series1} radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false} />
                    <Tooltip cursor={{ fill: C.band }} formatter={(val) => [`${val.toFixed(2)} ${t("tHa", lang)}`, t("yieldRange", lang)]} />
                  </BarChart>
                </ResponsiveContainer>
                <p className="text-xs text-[var(--text-muted)]">{t("wi.eachYearNote", lang)}</p>
              </Card>
              <Card title={t("wi.how", lang)}>
                <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
                  <li>{t("wi.price", lang, { p: r.profit.price.rs_per_qtl?.toLocaleString("en-IN") ?? "—", src: r.profit.price.source, c: r.profit.cost_rs_ha.toLocaleString("en-IN") })}</li>
                  {r.assumptions.map((a, i) => <li key={i} lang="en">{a}</li>)}
                </ul>
              </Card>
            </>
          )}
        </div>
      </div>
    </Page>
  );
}
