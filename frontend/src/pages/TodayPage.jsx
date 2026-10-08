import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { C, axisProps } from "../components/tokens.jsx";
import { Card, ErrorBox, LevelIcon, ListenButton, Loading, NeedField, Page } from "../components/ui.jsx";
import { alertText, irrigationText, pestName, pestWhy, stageText } from "../components/words.js";
import { cropName, fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

const CROPS = ["paddy", "maize", "cotton", "pulses", "chilli", "sugarcane"];

function savedCrop(fieldId) {
  try {
    return JSON.parse(localStorage.getItem(`kshetra.crop.${fieldId}`) || "null");
  } catch {
    return null;
  }
}

export default function TodayPage() {
  return <NeedField><Today /></NeedField>;
}

function Today() {
  const { fieldId, field, lang } = useApp();
  const [override, setOverride] = useState(() => savedCrop(fieldId));
  const [form, setForm] = useState(() => override || { crop: "paddy", sowing_date: "" });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    api.today(fieldId, override?.crop, override?.sowing_date).then((d) => { setData(d); setError(null); }).catch(setError);
  }, [fieldId, override]);

  function setCrop(e) {
    e.preventDefault();
    if (!form.sowing_date) return;
    try { localStorage.setItem(`kshetra.crop.${fieldId}`, JSON.stringify(form)); } catch { /* not saved */ }
    setOverride({ ...form });
  }

  const future = data?.days.filter((d) => d.is_forecast) || [];
  const alerts = data?.alerts || [];
  const ir = data?.irrigation;
  const readAloud = data ? [
    ...alerts.map((a) => alertText(a, lang)), irrigationText(ir, lang),
    ...data.pests.filter((p) => p.level !== "low").map((p) => `${pestName(p, lang)}: ${t(p.level, lang)}`),
  ].filter(Boolean).join(". ") : "";

  return (
    <Page title={`${t("today.title", lang)} · ${field?.name || ""}`} wide>
      <ErrorBox error={error} />
      {!data ? (!error && <Loading />) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            {data.crop && <span className="text-sm text-[var(--text-secondary)]">{stageText({ ...ir, crop: data.crop.crop, days_after_sowing: data.crop.days_after_sowing }, lang)}</span>}
            <ListenButton text={readAloud} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={t("today.alerts", lang)}>
              <ul className="space-y-2 text-sm">
                {alerts.filter((a) => a.level !== "info").length === 0 && <li className="text-[var(--text-secondary)]">{t("alert.none", lang)}</li>}
                {alerts.map((a, i) => (
                  <li key={i} className="flex gap-2"><LevelIcon level={a.level} /><span>{alertText(a, lang)}</span></li>
                ))}
              </ul>
            </Card>

            <Card title={t("today.irrigation", lang)}>
              {ir?.status === "no_crop" || !data.crop ? (
                <p className="text-sm text-[var(--text-secondary)]">{t("irrigation.no_crop", lang)}</p>
              ) : (
                <p className="mb-2 text-sm"><LevelIcon level={ir?.status === "irrigate_now" ? "critical" : ir?.status === "irrigate_soon" ? "warning" : "info"} />{" "}
                  {irrigationText(ir, lang)}{ir?.litres_for_field ? ` (${t("irrigation.litres", lang, { l: ir.litres_for_field.toLocaleString("en-IN") })})` : ""}</p>
              )}
              {ir?.series?.length > 0 && ir.status !== "paddy" && (
                <>
                  <div className="text-xs text-[var(--text-secondary)]">{t("today.waterUsed", lang)}</div>
                  <ResponsiveContainer width="100%" height={150}>
                    <LineChart data={ir.series} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
                      <CartesianGrid stroke={C.grid} vertical={false} />
                      <XAxis dataKey="date" tickFormatter={(d) => fmtDate(d, lang, { day: "numeric", month: "short" })} {...axisProps} minTickGap={24} />
                      <YAxis reversed {...axisProps} />
                      <ReferenceLine y={ir.raw_mm} stroke={C.critical} strokeWidth={1.5}
                                     label={{ value: t("today.limit", lang), position: "insideBottomRight", fill: C.critical, fontSize: 11 }} />
                      <Line dataKey="depletion_mm" stroke={C.series1} strokeWidth={2} dot={false} isAnimationActive={false} />
                      <Tooltip formatter={(v) => [`${v} mm`, t("today.waterUsed", lang)]} labelFormatter={(d) => fmtDate(d, lang)} />
                    </LineChart>
                  </ResponsiveContainer>
                </>
              )}
              <form onSubmit={setCrop} className="mt-3 flex flex-wrap items-end gap-2 border-t border-black/5 pt-3 text-sm">
                <label>{t("today.whatGrowing", lang)}
                  <select className="mt-1 block rounded border border-black/15 px-2 py-1" value={form.crop}
                          onChange={(e) => setForm({ ...form, crop: e.target.value })}>
                    {CROPS.map((c) => <option key={c} value={c}>{cropName(c, lang)}</option>)}
                  </select>
                </label>
                <label>{t("today.sownOn", lang)}
                  <input type="date" required className="mt-1 block rounded border border-black/15 px-2 py-1" value={form.sowing_date}
                         onChange={(e) => setForm({ ...form, sowing_date: e.target.value })} />
                </label>
                <button className="rounded bg-[var(--brand)] px-3 py-1.5 text-white">{t("today.set", lang)}</button>
              </form>
            </Card>
          </div>

          <Card title={t("today.week", lang)}>
            <div className="overflow-x-auto">
              <table className="w-full text-center text-sm">
                <thead className="text-xs text-[var(--text-secondary)]">
                  <tr><th />{future.map((d) => <th key={d.date} className="px-2 py-1 font-medium">{fmtDate(d.date, lang, { weekday: "short", day: "numeric" })}</th>)}</tr>
                </thead>
                <tbody className="tabular">
                  <tr><td className="pr-2 text-left text-xs text-[var(--text-secondary)]">{t("today.rain", lang)} (mm)</td>
                    {future.map((d) => <td key={d.date} className={(d.rain_mm || 0) >= 64.5 ? "font-semibold text-[var(--status-critical)]" : ""}>{Math.round(d.rain_mm ?? 0)}</td>)}</tr>
                  <tr><td className="pr-2 text-left text-xs text-[var(--text-secondary)]">{t("today.max", lang)} °C</td>
                    {future.map((d) => <td key={d.date}>{d.tmax != null ? Math.round(d.tmax) : "—"}</td>)}</tr>
                  <tr><td className="pr-2 text-left text-xs text-[var(--text-secondary)]">{t("today.min", lang)} °C</td>
                    {future.map((d) => <td key={d.date}>{d.tmin != null ? Math.round(d.tmin) : "—"}</td>)}</tr>
                </tbody>
              </table>
            </div>
          </Card>

          <Card title={t("today.pests", lang)}>
            {data.pests.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">{t("today.noPests", lang)}</p> : (
              <ul className="space-y-2 text-sm">
                {data.pests.map((p) => (
                  <li key={p.pest} className="flex flex-wrap gap-x-2">
                    <LevelIcon level={p.level} />
                    <b>{pestName(p, lang)}</b>
                    <span>{t(p.level, lang)}</span>
                    <span className="text-[var(--text-muted)]">· {t("today.favourable", lang, { n: p.favourable_days, total: p.of_days })}</span>
                    <span className="w-full pl-5 text-[var(--text-secondary)]">{pestWhy(p, lang)}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-[var(--text-muted)]">{t("today.pestNote", lang)}</p>
          </Card>
        </>
      )}
    </Page>
  );
}
