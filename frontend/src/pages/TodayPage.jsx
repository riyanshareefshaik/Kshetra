import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  Bug, CircleCheck, Circle, CloudRain, Droplets, HeartPulse, NotebookPen, Pencil, Scissors, SprayCan, Sun, Thermometer,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { CropIcon, WeatherIcon } from "../components/art.jsx";
import { C, axisProps } from "../components/tokens.jsx";
import { Card, ErrorBox, LevelIcon, ListenButton, Loading, NeedField } from "../components/ui.jsx";
import { alertText, irrigationText, pestName, pestWhy } from "../components/words.js";
import { cropName, fmtDate, t } from "../i18n.js";
import { useApp } from "../state.jsx";

const CROPS = ["paddy", "maize", "cotton", "pulses", "chilli", "sugarcane"];

function readJSON(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
}
function writeJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* not saved */ }
}

function greeting(lang) {
  const h = new Date().getHours();
  return t(h < 12 ? "hello.morning" : h < 17 ? "hello.afternoon" : "hello.evening", lang);
}

/** Today's jobs, built from the advice. Each has a stable id so it can be ticked off. */
function buildTasks(data, lang) {
  if (!data) return [];
  const tasks = [];
  const today = data.days.find((d) => d.is_forecast);
  const ir = data.irrigation;
  if (ir?.status === "irrigate_now") tasks.push({ id: "irrigate", icon: Droplets, tone: "sky", text: t("task.irrigate", lang, { mm: ir.amount_mm }) });
  if (ir?.status === "irrigate_soon") tasks.push({ id: "irrigate-soon", icon: Droplets, tone: "sky", text: t("task.irrigate_soon", lang, { date: fmtDate(ir.next_date, lang, { weekday: "short", day: "numeric", month: "short" }) }) });
  if (ir?.status === "paddy") tasks.push({ id: "paddy-water", icon: Droplets, tone: "sky", text: t("task.paddy", lang) });
  if (data.alerts.some((a) => a.type === "heavy_rain")) tasks.push({ id: "drains", icon: CloudRain, tone: "sky", text: t("task.drains", lang) });
  const spray = data.alerts.find((a) => a.type === "spray_window");
  if (spray?.date && today && spray.date === today.date) tasks.push({ id: "spray", icon: SprayCan, tone: "leaf", text: t("task.spray", lang) });
  if (data.alerts.some((a) => a.type === "heat" && today && a.date === today.date)) tasks.push({ id: "heat", icon: Thermometer, tone: "red", text: t("task.heat", lang) });
  data.pests.filter((p) => p.level === "high").slice(0, 2).forEach((p) =>
    tasks.push({ id: `scout-${p.pest}`, icon: Bug, tone: "gold", text: t("task.scout", lang, { pest: pestName(p, lang) }) }));
  if (data.alerts.some((a) => a.type === "harvest_window" && a.date)) tasks.push({ id: "harvest", icon: Scissors, tone: "gold", text: t("task.harvest", lang) });
  if (tasks.length) tasks.push({ id: "diary", icon: NotebookPen, tone: "soil", text: t("task.diary", lang), link: "/diary" });
  return tasks;
}

/** Latest greenness vs the same weeks in earlier years. */
function cropHealth(rows) {
  const pts = (rows || []).filter((r) => r.ndvi_smoothed != null).map((r) => ({ d: new Date(r.date), v: r.ndvi_smoothed, obs: r.ndvi_source === "s2" }));
  if (pts.length < 30) return null;
  const last = pts[pts.length - 1];
  if (Date.now() - last.d.getTime() > 45 * 864e5) return null;
  const doy = (d) => Math.floor((d - new Date(d.getFullYear(), 0, 0)) / 864e5);
  const target = doy(last.d);
  const past = pts.filter((p) => p.d.getFullYear() < last.d.getFullYear()
    && Math.min(Math.abs(doy(p.d) - target), 365 - Math.abs(doy(p.d) - target)) <= 10);
  if (past.length < 3) return null;
  const usual = past.reduce((s, p) => s + p.v, 0) / past.length;
  const seen = [...pts].reverse().find((p) => p.obs)?.d || last.d;
  const diff = last.v - usual;
  return { now: last.v, usual, seen, verdict: diff > 0.05 ? "better" : diff < -0.05 ? "worse" : "normal" };
}

export default function TodayPage() {
  return <NeedField><Today /></NeedField>;
}

function Today() {
  const { fieldId, field, lang } = useApp();
  const [override, setOverride] = useState(() => readJSON(`kshetra.crop.${fieldId}`, null));
  const [form, setForm] = useState(() => override || { crop: "paddy", sowing_date: "" });
  const [editing, setEditing] = useState(false);
  const [data, setData] = useState(null);
  const [series, setSeries] = useState(null);
  const [error, setError] = useState(null);
  const todayKey = new Date().toISOString().slice(0, 10);
  const doneKey = `kshetra.done.${fieldId}.${todayKey}`;
  const [done, setDone] = useState(() => readJSON(doneKey, []));

  useEffect(() => {
    setData(null);
    api.today(fieldId, override?.crop, override?.sowing_date).then((d) => { setData(d); setError(null); }).catch(setError);
  }, [fieldId, override]);
  useEffect(() => {
    const start = new Date(Date.now() - 6 * 365 * 864e5).toISOString().slice(0, 10);
    api.timeseries(fieldId, { step: 7, start }).then(setSeries).catch(() => setSeries([]));
  }, [fieldId]);

  const tasks = useMemo(() => buildTasks(data, lang), [data, lang]);
  const health = useMemo(() => cropHealth(series), [series]);

  function toggle(id) {
    const next = done.includes(id) ? done.filter((x) => x !== id) : [...done, id];
    setDone(next);
    writeJSON(doneKey, next);
  }

  function saveCrop(e) {
    e.preventDefault();
    if (!form.sowing_date) return;
    writeJSON(`kshetra.crop.${fieldId}`, form);
    setOverride({ ...form });
    setEditing(false);
  }

  if (error) return <div className="mx-auto max-w-5xl p-4"><ErrorBox error={error} /></div>;
  if (!data) return <div className="mx-auto max-w-5xl p-4"><Loading lines={4} /></div>;

  const future = data.days.filter((d) => d.is_forecast);
  const now = future[0];
  const crop = data.crop;
  const ir = data.irrigation;
  const duration = crop && crop.days_to_harvest != null ? crop.days_after_sowing + crop.days_to_harvest : null;
  const progress = duration ? Math.min(1, Math.max(0, crop.days_after_sowing / duration)) : null;
  const warnings = data.alerts.filter((a) => a.level !== "info");
  const readAloud = [greeting(lang), ...tasks.map((x) => x.text), ...warnings.map((a) => alertText(a, lang))].join(". ");
  const doneCount = tasks.filter((x) => done.includes(x.id)).length;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 px-4 py-5 sm:px-6">
      {/* Hero: greeting, weather now, crop and season progress */}
      <section className="k-hero k-rise overflow-hidden p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm text-white/80">{fmtDate(new Date(), lang, { weekday: "long", day: "numeric", month: "long" })}</p>
            <h1 className="mt-0.5 text-3xl font-bold leading-tight">{greeting(lang)}</h1>
            <p className="mt-1 truncate text-white/85">{field?.name}{field?.district ? ` · ${field.district}` : ""}</p>
          </div>
          {now && (
            <div className="flex items-center gap-3 rounded-2xl bg-white/12 px-4 py-3 backdrop-blur-sm" style={{ background: "rgba(255,255,255,0.12)" }}>
              <span className="grid h-14 w-14 place-items-center rounded-2xl bg-white"><WeatherIcon day={now} size={34} /></span>
              <div>
                <div className="font-display text-3xl font-bold leading-none">{Math.round(now.tmax)}°<span className="text-lg font-medium text-white/70"> / {Math.round(now.tmin)}°</span></div>
                <div className="mt-1 text-sm text-white/85">{now.rain_mm >= 1 ? `${Math.round(now.rain_mm)} mm` : t("home.rainChance", lang, { p: Math.round(now.rain_prob ?? 0) })}</div>
              </div>
            </div>
          )}
        </div>

        {crop ? (
          <div className="mt-5 rounded-2xl bg-white/95 p-4 text-[var(--text-primary)]">
            <div className="flex flex-wrap items-center gap-3">
              <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[var(--leaf-50)]"><CropIcon crop={crop.crop} size={34} /></span>
              <div className="min-w-0 flex-1">
                <div className="font-display text-lg font-bold leading-tight">{cropName(crop.crop, lang)}</div>
                <div className="text-sm text-[var(--text-secondary)]">
                  {duration ? t("home.dayOf", lang, { n: crop.days_after_sowing, total: duration }) : ""}
                  {ir?.stage ? ` · ${t(`stage.${ir.stage}`, lang)}` : ""}
                </div>
              </div>
              <button onClick={() => setEditing((v) => !v)} aria-label={t("today.whatGrowing", lang)} className="inline-flex items-center gap-1 rounded-full border border-black/10 p-2 text-xs sm:px-3 sm:py-1"><Pencil size={13} /><span className="hidden sm:inline">{t("today.whatGrowing", lang)}</span></button>
            </div>
            {progress != null && (
              <div className="mt-3">
                <div className="relative h-3 overflow-hidden rounded-full bg-[var(--leaf-50)]">
                  <div className="h-full rounded-full bg-gradient-to-r from-[var(--leaf)] to-[var(--gold)] transition-[width] duration-700" style={{ width: `${progress * 100}%` }} />
                </div>
                <div className="mt-1 flex justify-between text-[11px] text-[var(--text-muted)]">
                  <span>{t("sowing", lang)}</span>
                  <span>{crop.days_to_harvest > 0 ? t("home.toHarvest", lang, { n: crop.days_to_harvest }) : t("harvest", lang)}</span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <button onClick={() => setEditing(true)} className="mt-5 flex w-full items-center gap-3 rounded-2xl border-2 border-dashed border-white/40 p-4 text-left text-white">
            <CropIcon crop="other" size={30} /> <span className="font-medium">{t("home.setCrop", lang)}</span>
          </button>
        )}
        {editing && (
          <form onSubmit={saveCrop} className="k-rise mt-3 flex flex-wrap items-end gap-2 rounded-2xl bg-white p-3 text-sm text-[var(--text-primary)]">
            <div className="flex flex-wrap gap-1.5">
              {CROPS.map((c) => (
                <button type="button" key={c} onClick={() => setForm({ ...form, crop: c })}
                        className={`flex items-center gap-1 rounded-xl border px-2 py-1 ${form.crop === c ? "border-[var(--leaf)] bg-[var(--leaf-50)]" : "border-black/10"}`}>
                  <CropIcon crop={c} size={20} />{cropName(c, lang).split(" (")[0]}
                </button>
              ))}
            </div>
            <label className="text-xs">{t("today.sownOn", lang)}
              <input type="date" required className="mt-1 block rounded-xl border border-black/15 px-2 py-1.5 text-sm" value={form.sowing_date}
                     onChange={(e) => setForm({ ...form, sowing_date: e.target.value })} />
            </label>
            <button className="rounded-xl bg-[var(--brand)] px-4 py-2 text-white">{t("today.set", lang)}</button>
          </form>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-5">
        {/* To do today */}
        <Card title={t("home.todo", lang)} icon={CircleCheck} className="lg:col-span-3"
              actions={<div className="flex items-center gap-2">{tasks.length > 0 && <span className="rounded-full bg-[var(--leaf-50)] px-2.5 py-0.5 text-xs font-semibold text-[var(--brand)]">{doneCount}/{tasks.length}</span>}<ListenButton text={readAloud} /></div>}>
          {tasks.length === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">{t("home.nothing", lang)}</p>
          ) : (
            <ul className="space-y-2">
              {tasks.map((task) => {
                const isDone = done.includes(task.id);
                return (
                  <li key={task.id}>
                    <button onClick={() => toggle(task.id)}
                            className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors ${isDone ? "border-[var(--leaf-100)] bg-[var(--leaf-50)]" : "border-black/10 bg-white hover:border-[var(--leaf)]"}`}>
                      {isDone ? <CircleCheck key="d" size={22} className="k-pop shrink-0 text-[var(--leaf)]" /> : <Circle size={22} className="shrink-0 text-[var(--text-muted)]" />}
                      <task.icon size={18} className="shrink-0 text-[var(--text-secondary)]" />
                      <span className={`text-sm ${isDone ? "text-[var(--text-muted)] line-through" : ""}`}>{task.text}</span>
                      {task.link && <Link to={task.link} onClick={(e) => e.stopPropagation()} className="ml-auto text-xs text-[var(--sky)] underline">{t("nav.diary", lang)}</Link>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {tasks.length > 0 && doneCount === tasks.length && <p className="k-rise mt-3 text-sm font-medium text-[var(--brand)]">🌾 {t("home.allDone", lang)}</p>}
        </Card>

        {/* Crop health from space */}
        <Card title={t("home.health", lang)} icon={HeartPulse} tone={health?.verdict === "worse" ? "red" : "leaf"} className="lg:col-span-2">
          {!series ? <Loading lines={2} /> : !health ? (
            <p className="text-sm text-[var(--text-secondary)]">{t("home.health.none", lang)}</p>
          ) : (
            <div>
              <p className="font-display text-lg font-semibold leading-snug">{t(`home.health.${health.verdict}`, lang)}</p>
              <div className="relative mt-4 h-3 rounded-full bg-gradient-to-r from-[#d9c9a8] via-[#b7dbb0] to-[var(--leaf)]">
                <span className="absolute -top-1 h-5 w-0.5 bg-[var(--text-primary)]/60" style={{ left: `${health.usual * 100}%` }} />
                <span className="absolute -top-1.5 h-6 w-6 -translate-x-1/2 rounded-full border-[3px] border-white bg-[var(--brand)] shadow" style={{ left: `${health.now * 100}%` }} />
              </div>
              <div className="relative mt-1 h-4 text-[11px] text-[var(--text-muted)]">
                <span className="absolute -translate-x-1/2" style={{ left: `${health.usual * 100}%` }}>{t("home.usual", lang)}</span>
              </div>
              <p className="mt-2 text-xs text-[var(--text-muted)]">{t("home.health.seen", lang, { date: fmtDate(health.seen, lang) })}</p>
            </div>
          )}
        </Card>
      </div>

      {/* Week ahead */}
      <Card title={t("home.week", lang)} icon={Sun} tone="gold">
        <div className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1">
          {future.map((d, i) => (
            <div key={d.date} className={`min-w-[5.2rem] flex-1 snap-start rounded-2xl border p-2.5 text-center ${i === 0 ? "border-[var(--leaf)] bg-[var(--leaf-50)]" : "border-black/5 bg-[var(--page)]"}`}>
              <div className="text-xs font-medium text-[var(--text-secondary)]">{i === 0 ? t("home.todayWeather", lang) : fmtDate(d.date, lang, { weekday: "short" })}</div>
              <div className="my-1.5 flex justify-center"><WeatherIcon day={d} size={28} /></div>
              <div className="tabular text-sm font-semibold">{Math.round(d.tmax)}° <span className="font-normal text-[var(--text-muted)]">{Math.round(d.tmin)}°</span></div>
              <div className={`tabular mt-0.5 text-xs ${(d.rain_mm || 0) >= 64.5 ? "font-bold text-[var(--status-critical)]" : "text-[var(--sky)]"}`}>{Math.round(d.rain_mm ?? 0)} mm</div>
            </div>
          ))}
        </div>
        {data.alerts.length > 0 && (
          <ul className="mt-3 space-y-1.5 text-sm">
            {data.alerts.map((a, i) => <li key={i} className="flex gap-2"><LevelIcon level={a.level} /><span>{alertText(a, lang)}</span></li>)}
          </ul>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t("today.irrigation", lang)} icon={Droplets} tone="sky">
          <p className="text-sm">{irrigationText(ir, lang)}{ir?.litres_for_field ? ` (${t("irrigation.litres", lang, { l: ir.litres_for_field.toLocaleString("en-IN") })})` : ""}</p>
          {ir?.series?.length > 0 && ir.status !== "paddy" && (
            <>
              <div className="mt-3 text-xs text-[var(--text-secondary)]">{t("today.waterUsed", lang)}</div>
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
        </Card>

        <Card title={t("today.pests", lang)} icon={Bug} tone="gold">
          {data.pests.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">{t("today.noPests", lang)}</p> : (
            <ul className="space-y-2">
              {data.pests.map((p) => (
                <li key={p.pest} className="rounded-xl border border-black/5 bg-[var(--page)] p-2.5 text-sm">
                  <div className="flex items-center gap-2">
                    <LevelIcon level={p.level} /><b>{pestName(p, lang)}</b>
                    <span className={`ml-auto rounded-full px-2 py-0.5 text-xs font-semibold ${p.level === "high" ? "bg-red-50 text-[var(--status-critical)]" : p.level === "medium" ? "bg-[var(--gold-50)] text-[#9a6a06]" : "bg-[var(--leaf-50)] text-[var(--brand)]"}`}>{t(p.level, lang)}</span>
                  </div>
                  <p className="mt-1 pl-5 text-[var(--text-secondary)]">{pestWhy(p, lang)}</p>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-[var(--text-muted)]">{t("today.pestNote", lang)}</p>
        </Card>
      </div>
    </div>
  );
}
