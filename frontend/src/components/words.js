// Put server advice (codes + numbers) into words in the farmer's language.
import { MONTHS, cropName, fmtDate, has, t } from "../i18n.js";

const short = (d, lang) => fmtDate(d, lang, { weekday: "short", day: "numeric", month: "short" });
const n0 = (v) => (v == null ? "—" : Math.round(v));

export function alertText(a, lang) {
  switch (a.type) {
    case "heavy_rain":
      return t(a.level === "critical" ? "alert.heavy_rain.critical" : "alert.heavy_rain", lang, { date: short(a.date, lang), value: n0(a.value) });
    case "spray_window":
      return a.date ? t("alert.spray_window", lang, { date: short(a.date, lang) }) : t("alert.spray_window.none", lang);
    case "harvest_window":
      return a.date ? t("alert.harvest_window", lang, { date: short(a.date, lang) }) : t("alert.harvest_window.none", lang);
    case "dry_week":
      return t("alert.dry_week", lang, { value: a.value });
    default:
      return has(`alert.${a.type}`) ? t(`alert.${a.type}`, lang, { date: a.date ? short(a.date, lang) : "", value: n0(a.value) }) : a.message;
  }
}

export function pestName(p, lang) {
  return has(`pest.${p.pest}`) ? t(`pest.${p.pest}`, lang) : p.pest;
}

export function pestWhy(p, lang) {
  return has(`pest.${p.pest}.why`) ? t(`pest.${p.pest}.why`, lang) : p.why;
}

export function irrigationText(ir, lang) {
  if (!ir) return "";
  switch (ir.status) {
    case "irrigate_now": return t("irrigation.irrigate_now", lang, { mm: ir.amount_mm });
    case "irrigate_soon": {
      const days = Math.max(1, Math.round((new Date(ir.next_date) - new Date(new Date().toDateString())) / 864e5));
      return t("irrigation.irrigate_soon", lang, { n: days, date: short(ir.next_date, lang), mm: ir.amount_mm });
    }
    case "ok": return t("irrigation.ok", lang);
    case "paddy": return t(ir.stage === "flowering / grain filling" ? "irrigation.paddy.flowering" : "irrigation.paddy.awd", lang);
    case "no_crop": case "not_sown": case "harvested": return t(`irrigation.${ir.status}`, lang);
    default: return ir.message || "";
  }
}

export function stageText(ir, lang) {
  if (!ir?.crop || ir.days_after_sowing == null) return "";
  return t("today.stage", lang, { crop: cropName(ir.crop, lang), n: ir.days_after_sowing, stage: t(`stage.${ir.stage}`, lang) });
}

function fmtNum(v) {
  if (v == null) return "—";
  return Math.abs(v) >= 10 ? Math.round(v).toString() : Number(v).toFixed(2);
}

export function reasonText(r, lang) {
  if (r.shap_t_ha != null && has(`f.${r.feature}`)) {
    return t("why.reason.model", lang, {
      label: t(`f.${r.feature}`, lang), value: fmtNum(r.value), typical: fmtNum(r.typical),
      dir: t(r.direction === "up" ? "why.raised" : "why.lowered", lang), x: Math.abs(r.shap_t_ha).toFixed(1),
    });
  }
  if (r.feature === "ndvi_integral" && r.value != null) {
    return t(r.direction === "up" ? "why.reason.greener" : "why.reason.lessGreen", lang, { p: Math.round(Math.abs(r.value) * 100) });
  }
  if (has(`ev.${r.feature}`)) return t("why.reason.event", lang, { event: t(`ev.${r.feature}`, lang) });
  return r.text;
}

export function marketAdvice(a, lang) {
  switch (a.code) {
    case "trend": return t(`mk.trend.${a.word}`, lang, { c: `${a.change_pct > 0 ? "+" : ""}${a.change_pct}` });
    case "seasonal": return t("mk.seasonal", lang, { best: MONTHS[lang][a.best_month - 1], now: MONTHS[lang][a.this_month - 1], g: a.gain_pct });
    case "best_market": return t("mk.best", lang, { m: a.market, km: a.km, p: a.price.toLocaleString("en-IN"), d: short(a.date, lang) });
    case "no_data": return t("mk.no_data", lang);
    default: return a.text;
  }
}

export function fertNote(n, lang) {
  return has(`fz.note.${n.code}`) ? t(`fz.note.${n.code}`, lang, { v: n.value }) : n.text;
}

export function twinDiff(d, lang) {
  switch (d.code) {
    case "sowed_later": case "sowed_earlier": return t(`tw.${d.code}`, lang, { n: d.days });
    case "variety": return t("tw.variety", lang, { v: d.variety });
    case "irrigation": return t("tw.irrigation", lang, { v: t(`irr.${d.irrigation}`, lang) });
    case "diary": return t("tw.diary", lang, { a: t(`act.${d.activity}`, lang), theirs: d.theirs, mine: d.mine });
    case "no_stress": return t("tw.no_stress", lang);
    default: return d.text || String(d);
  }
}
