import { useEffect, useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api.js";
import { C, GapBar, axisProps } from "../components/tokens.jsx";
import { Card, CropBadge, ErrorBox, EventTag, Loading, NeedField, Page, RangeBar, eventStyle } from "../components/ui.jsx";
import { t } from "../i18n.js";
import { useApp } from "../state.jsx";

const RANGES = { "1y": 365, "3y": 365 * 3, all: null };
const CROPS = ["paddy", "maize", "cotton", "pulses", "chilli", "sugarcane"];
const fmtDate = (ms) => new Date(ms).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
const fullDate = (ms) => new Date(ms).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const ms = (d) => new Date(d).getTime();

function NdviTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded border border-black/10 bg-white px-2 py-1 text-xs shadow-sm">
      <div className="font-medium">{fullDate(p.t)}</div>
      {p.ndvi_smoothed != null && <div>NDVI (smoothed): <span className="tabular">{p.ndvi_smoothed.toFixed(2)}</span></div>}
      {p.obs != null && <div style={{ color: "var(--series-1)" }}>● Sentinel-2: <span className="tabular">{p.obs.toFixed(2)}</span></div>}
      {p.fill != null && <div style={{ color: "var(--series-2)" }}>● From radar: <span className="tabular">{p.fill.toFixed(2)}</span></div>}
    </div>
  );
}

export default function TimelinePage() {
  return <NeedField><Timeline /></NeedField>;
}

function Timeline() {
  const { field, fieldId, lang } = useApp();
  const [range, setRange] = useState("3y");
  const [rows, setRows] = useState(null);
  const [seasons, setSeasons] = useState([]);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    setRows(null);
    const days = RANGES[range];
    const params = { step: days && days <= 400 ? 3 : 7 };
    if (days) params.start = new Date(Date.now() - days * 864e5).toISOString().slice(0, 10);
    Promise.all([api.timeseries(fieldId, params), api.seasons(fieldId), api.events(fieldId)])
      .then(([ts, ss, ev]) => { setRows(ts); setSeasons(ss); setEvents(ev); setError(null); })
      .catch(setError);
  }, [fieldId, range]);

  const data = useMemo(() => (rows || []).map((r) => ({
    t: ms(r.date),
    ndvi_smoothed: r.ndvi_smoothed,
    obs: r.ndvi_source === "s2" ? r.ndvi : null,
    fill: r.ndvi_source === "sar_fill" ? r.ndvi : null,
    rain: r.is_step ? r.rain_step_mm : null,
  })), [rows]);
  const rain = data.filter((d) => d.rain != null);
  const domain = data.length ? [data[0].t, data[data.length - 1].t] : [0, 1];
  const inView = (s) => ms(s.harvest_date || Date.now()) >= domain[0];
  const maxYield = Math.max(1, ...seasons.map((s) => s.yield_high_t_ha || 0));
  const stress = events.filter((e) => e.origin === "detected");

  async function confirm(season, crop) {
    try {
      const updated = await api.confirmSeason(season.id, { crop });
      setSeasons(seasons.map((s) => (s.id === season.id ? { ...s, ...updated } : s)));
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Page title={`${t("timeline", lang)} · ${field?.name || ""}`} wide>
      <ErrorBox error={error} />
      <div className="flex gap-1" role="group" aria-label="Time range">
        {Object.keys(RANGES).map((k) => (
          <button key={k} onClick={() => setRange(k)}
                  className={`rounded border px-2.5 py-1 text-sm ${range === k ? "border-[var(--brand)] bg-[var(--brand)] text-white" : "border-black/15 bg-white"}`}>
            {k === "all" ? "All years" : `Last ${k}`}
          </button>
        ))}
      </div>

      <Card title="Crop greenness from space (NDVI)">
        {!rows ? <Loading /> : data.length === 0 ? (
          <p className="text-sm text-[var(--text-secondary)]">No satellite data yet. Kshetra is still building this field's history; check its status on the Map page.</p>
        ) : (
          <>
            <div className="mb-2 flex flex-wrap gap-4 text-xs text-[var(--text-secondary)]">
              <span><span style={{ color: "var(--series-1)" }}>━</span> Smoothed NDVI</span>
              <span><span style={{ color: "var(--series-1)" }}>●</span> Clear Sentinel-2</span>
              <span><span style={{ color: "var(--series-2)" }}>●</span> Cloudy day, estimated from radar</span>
              <span><span className="inline-block h-2.5 w-3 bg-[var(--band)] align-middle" /> Crop season</span>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data} margin={{ top: 18, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="t" type="number" scale="time" domain={domain} tickFormatter={fmtDate}
                       {...axisProps} />
                <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} stroke={C.axis}
                       tick={{ fill: C.muted, fontSize: 11 }} />
                {seasons.filter(inView).map((s) => (
                  <ReferenceArea key={s.id} x1={Math.max(ms(s.sowing_date), domain[0])} x2={ms(s.harvest_date || domain[1])}
                                 fill={C.band} fillOpacity={1} ifOverflow="hidden"
                                 label={{ value: s.crop || "?", position: "insideTop", fontSize: 11, fill: C.secondary }} />
                ))}
                {stress.filter((e) => ms(e.start_date) >= domain[0]).map((e) => (
                  <ReferenceLine key={e.id} x={ms(e.start_date)} stroke={eventStyle(e.event_type).color} strokeWidth={1.5}
                                 label={{ value: eventStyle(e.event_type).icon, position: "top", fill: eventStyle(e.event_type).color, fontSize: 12 }} />
                ))}
                <Line dataKey="ndvi_smoothed" stroke={C.series1} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
                <Scatter dataKey="obs" fill={C.series1} shape={(p) => p.payload.obs == null ? null : <circle cx={p.cx} cy={p.cy} r={2.5} fill={C.series1} />} isAnimationActive={false} />
                <Scatter dataKey="fill" fill={C.series2} shape={(p) => p.payload.fill == null ? null : <circle cx={p.cx} cy={p.cy} r={3} fill={C.series2} stroke={C.surface} strokeWidth={1} />} isAnimationActive={false} />
                <Tooltip content={<NdviTooltip />} cursor={{ stroke: C.axis }} />
              </ComposedChart>
            </ResponsiveContainer>
            <h3 className="mt-4 text-sm font-medium">Rainfall <span className="font-normal text-[var(--text-muted)]">(mm per {RANGES[range] && RANGES[range] <= 400 ? 3 : 7} days)</span></h3>
            <ResponsiveContainer width="100%" height={110}>
              <BarChart data={rain} margin={{ top: 4, right: 8, bottom: 0, left: -18 }} barCategoryGap={1}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis dataKey="t" type="number" scale="time" domain={domain} tickFormatter={fmtDate}
                       {...axisProps} />
                <YAxis {...axisProps} />
                <Bar dataKey="rain" fill={C.series1} shape={<GapBar />} isAnimationActive={false} />
                <Tooltip cursor={{ fill: C.band }} labelFormatter={fullDate} formatter={(v) => [`${v.toFixed(0)} mm`, "Rain"]} />
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </Card>

      <Card title="Seasons">
        {seasons.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">No seasons detected yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-[var(--text-secondary)]">
                <tr><th className="py-1 pr-3">Season</th><th className="pr-3">{t("crop", lang)}</th><th className="pr-3">{t("sowing", lang)}</th>
                  <th className="pr-3">{t("harvest", lang)}</th><th className="pr-3">{t("yieldRange", lang)}</th><th>Correct?</th></tr>
              </thead>
              <tbody>
                {[...seasons].reverse().map((s) => (
                  <tr key={s.id} className="border-t border-black/5">
                    <td className="py-1.5 pr-3 capitalize">{s.season} {s.year}</td>
                    <td className="pr-3"><CropBadge season={s} /></td>
                    <td className="tabular pr-3">{fullDate(s.sowing_date)}{["sar", "nisar"].includes(s.date_detection) && <span className="text-xs text-[var(--text-muted)]"> · seen by radar</span>}</td>
                    <td className="tabular pr-3">{s.in_progress ? "in field" : s.harvest_date ? fullDate(s.harvest_date) : "—"}</td>
                    <td className="pr-3"><RangeBar low={s.yield_low_t_ha} mid={s.yield_mid_t_ha} high={s.yield_high_t_ha} max={maxYield} />
                      {s.yield_is_forecast && <span className="text-xs text-[var(--text-muted)]"> forecast</span>}</td>
                    <td>
                      <select aria-label="Confirm crop" className="rounded border border-black/15 px-1 py-0.5 text-xs"
                              value={s.crop_confirmed_by_farmer ? s.crop : ""} onChange={(e) => e.target.value && confirm(s, e.target.value)}>
                        <option value="">{s.crop_confirmed_by_farmer ? "" : "confirm…"}</option>
                        {CROPS.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Stress events">
        {stress.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">No stress events detected.</p> : (
          <ul className="divide-y divide-black/5 text-sm">
            {[...stress].reverse().map((e) => (
              <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 py-1.5">
                <EventTag event={e} />
                <span className="tabular text-[var(--text-secondary)]">{fullDate(e.start_date)}{e.end_date && e.end_date !== e.start_date ? ` – ${fullDate(e.end_date)}` : ""}</span>
                <span className="text-xs text-[var(--text-muted)]">
                  {Object.entries(e.evidence).filter(([, v]) => v != null).map(([k, v]) => `${k.replaceAll("_", " ")}: ${v === true ? "yes" : v === false ? "no" : v}`).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </Page>
  );
}
