"""What-if simulator (F8) and next-season planner (F9).

A scenario (crop, variety, sowing date, nitrogen, irrigation) is replayed
against every past year of this field's own weather. Each replay builds the
season features the yield model expects, and the spread across years gives
the yield range, the risk, and the profit range.

Parts that are rule-based assumptions, not learned from data (shown to users
under "assumptions"):
  * crop greenness for the scenario = this field's average for that crop
    (or a typical value for the crop when the field never grew it);
  * nitrogen response: yield rises steeply up to the recommended dose and
    then flattens (Mitscherlich curve);
  * irrigation removes dry-spell and low-rain effects (full) or halves them
    (supplemental);
  * a high-water crop in a dry season without irrigation loses half its yield.
"""
import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.ml.analyze import district_yield_history, load_timeseries
from app.ml.crop_classifier import PROFILES
from app.ml.features import season_features
from app.ml.season_detection import DetectedSeason
from app.ml.yield_model import YieldModel, load_cached_model
from app.services.prices import price_per_quintal

ZERO_N_FRACTION = {"pulses": 0.9}       # legumes fix their own nitrogen
DEFAULT_ZERO_N_FRACTION = 0.6
UREA_RS_PER_KG_N = 266.5 / 45 / 0.46     # subsidised urea Rs 266.5 per 45 kg bag, 46% N
IRRIGATION_COST_RS_HA = {"rainfed": 0, "supplemental": 3000, "full": 8000}   # rough estimates
DRY_SEASONS = {"rabi", "zaid"}
TROUGH_NDVI = 0.2
LOW_YIELD_FRACTION = 0.85


@dataclass
class Scenario:
    crop: str
    season: str
    sowing_month_day: tuple[int, int]
    duration_days: int
    n_kg_ha: float
    recommended_n_kg_ha: float
    irrigation: str = "rainfed"          # rainfed | supplemental | full
    water_need: str = "medium"
    seed_cost_rs_ha: float = 0.0
    other_cost_rs_ha: float = 0.0
    variety: str | None = None
    price_rs_per_qtl: float | None = None


def n_multiplier(crop: str, n: float, n_rec: float) -> float:
    """Share of attainable yield at nitrogen dose n (1.0 at the recommended dose)."""
    base = ZERO_N_FRACTION.get(crop, DEFAULT_ZERO_N_FRACTION)
    if n_rec <= 0:
        return 1.0
    k = 3.0 / n_rec
    response = (1 - math.exp(-k * max(n, 0))) / (1 - math.exp(-3.0))
    return base + (1 - base) * min(response, 1.03)


def _crop_history(conn, field_id: str, crop: str) -> dict:
    row = conn.execute(
        """SELECT avg(peak_ndvi) AS peak, avg((features->>'ndvi_integral')::float) AS integral,
                  avg((features->>'vh_peak_db')::float) AS vh, avg((features->>'vh_vv_peak_db')::float) AS vhvv,
                  count(*) AS n
           FROM seasons WHERE field_id = %s AND crop = %s AND NOT in_progress""",
        (field_id, crop),
    ).fetchone()
    return row if row and row["n"] else {}


def _sowing_for_year(year: int, season: str, month: int, day: int) -> date:
    # Rabi sown in January belongs to the previous year's rabi.
    if season == "rabi" and month <= 2:
        return date(year + 1, month, day)
    return date(year, month, day)


class FieldContext:
    """Everything about a field the simulator needs, loaded once per request."""

    def __init__(self, conn, field_id: str):
        self.field = conn.execute(
            """SELECT id::text, name, district, state, area_ha, irrigation_type,
                      clay_pct, sand_pct, ph_h2o, soc_g_per_kg FROM fields WHERE id = %s""",
            (field_id,),
        ).fetchone()
        if self.field is None:
            raise ValueError(f"field {field_id} not found")
        self.df = load_timeseries(conn, field_id)
        self.conn = conn
        self.model = load_cached_model()


def simulate(ctx: FieldContext, sc: Scenario) -> dict:
    df = ctx.df
    if df.empty or df["rainfall_mm"].notna().sum() < 365:
        return {"error": "not enough weather history for this field yet"}
    hist = _crop_history(ctx.conn, ctx.field["id"], sc.crop)
    profile = PROFILES.get(sc.crop)
    peak_ndvi = float(hist.get("peak") or (sum(profile.peak_ndvi) / 2 if profile else 0.7))
    amplitude = peak_ndvi - TROUGH_NDVI

    years, rows = [], []
    first, last = df.index.min().date(), df.index.max().date()
    for year in range(first.year, last.year + 1):
        sow = _sowing_for_year(year, sc.season, *sc.sowing_month_day)
        harvest = sow + timedelta(days=sc.duration_days)
        if sow < first or harvest > last:
            continue
        peak = sow + timedelta(days=round(0.55 * sc.duration_days))
        s = DetectedSeason(year=year, season=sc.season, sowing_date=sow, greenup_date=sow + timedelta(days=15),
                           peak_date=peak, harvest_date=harvest, peak_ndvi=round(peak_ndvi, 3),
                           trough_ndvi=TROUGH_NDVI, date_detection="ndvi",
                           flood_signal_db=6.0 if profile and profile.flooded else 0.0, obs_fraction=1.0)
        f = season_features(df, s, ctx.field)
        # The real NDVI of that year belongs to whatever crop was grown then; use this crop's norm.
        f["ndvi_integral"] = float(hist.get("integral") or amplitude * sc.duration_days * 0.55)
        f["senescence_rate"] = round(0.7 * amplitude / max((harvest - peak).days, 1), 4)
        f["vh_peak_db"], f["vh_vv_peak_db"] = hist.get("vh"), hist.get("vhvv")
        _apply_irrigation(f, sc.irrigation, ctx.model)
        years.append(year)
        rows.append(f)
    if not rows:
        return {"error": "no complete past season of weather for this sowing date and duration"}

    lows, mids, highs, method = _predict(ctx, sc, rows)
    mult = n_multiplier(sc.crop, sc.n_kg_ha, sc.recommended_n_kg_ha)
    water_penalty = 0.5 if (sc.water_need == "high" and sc.season in DRY_SEASONS and sc.irrigation == "rainfed") else 1.0
    factor = mult * water_penalty
    lows, mids, highs = lows * factor, mids * factor, highs * factor

    yield_range = {"low": round(float(np.percentile(lows, 10)), 2), "mid": round(float(np.median(mids)), 2),
                   "high": round(float(np.percentile(highs, 90)), 2)}
    risk = _risk(rows, mids, sc, water_penalty)
    if sc.price_rs_per_qtl:
        price = {"rs_per_qtl": sc.price_rs_per_qtl, "source": "entered by user"}
    else:
        price = price_per_quintal(ctx.conn, sc.crop, ctx.field["state"], ctx.field["district"])
    profit = _profit(yield_range, price, sc, ctx.field["area_ha"])
    return {
        "scenario": {"crop": sc.crop, "variety": sc.variety, "season": sc.season,
                     "sowing": f"{sc.sowing_month_day[0]:02d}-{sc.sowing_month_day[1]:02d}",
                     "duration_days": sc.duration_days, "n_kg_ha": sc.n_kg_ha, "irrigation": sc.irrigation},
        "yield_t_ha": yield_range,
        "risk": risk,
        "profit": profit,
        "years_simulated": years,
        "per_year": [{"year": y, "yield_mid_t_ha": round(float(m), 2)} for y, m in zip(years, mids)],
        "method": method,
        "assumptions": [
            (f"Crop greenness from {'this field' if hist else 'a typical ' + sc.crop + ' crop'} "
             f"(peak NDVI {peak_ndvi:.2f})."),
            (f"Nitrogen {sc.n_kg_ha:.0f} kg/ha vs recommended {sc.recommended_n_kg_ha:.0f}: "
             f"x{mult:.2f} of attainable yield (response curve, not measured on this field)."),
            f"Irrigation '{sc.irrigation}' adjusts dry-spell and rainfall effects (rule-based).",
        ] + (["High-water crop in a dry season without irrigation: yield halved."] if water_penalty < 1 else []),
    }


def _apply_irrigation(f: dict, irrigation: str, model: YieldModel | None):
    if irrigation == "rainfed":
        return
    share = 1.0 if irrigation == "full" else 0.5
    typical = (model.feature_means if model else {}) or {}
    for k in ("rain_vegetative_mm", "rain_reproductive_mm", "rain_total_mm"):
        target = typical.get(k)
        if f.get(k) is not None and target is not None and f[k] < target:
            f[k] = f[k] + share * (target - f[k])
    if f.get("max_dry_spell_days") is not None:
        f["max_dry_spell_days"] = round(f["max_dry_spell_days"] * (1 - share) + 5 * share)


def _predict(ctx: FieldContext, sc: Scenario, rows: list[dict]):
    if ctx.model is not None:
        X = ctx.model.matrix(rows, [sc.crop] * len(rows))
        preds = np.sort(np.vstack([ctx.model.models[q].predict(X) for q in (0.1, 0.5, 0.9)]), axis=0)
        return preds[0], preds[1], preds[2], "model"
    history = district_yield_history(ctx.conn, ctx.field["state"], ctx.field["district"], sc.crop, sc.season)
    if not history:
        raise LookupError(f"Not enough yield records for {sc.crop} in this district yet, so Kshetra cannot "
                          "estimate it. Ask your administrator to load district crop statistics.")
    base = float(np.median(history))
    spread = max(float(np.std(history)) / base if len(history) > 1 else 0.0, 0.12)
    mids = np.array([base * _stress_factor(r, sc) for r in rows])
    return mids * (1 - 1.28 * spread), mids, mids * (1 + 1.28 * spread), "baseline"


def _stress_factor(f: dict, sc: Scenario) -> float:
    """Baseline only: rule-based yield loss from dry spells and heat (no trained model yet)."""
    loss = 0.0
    dry = f.get("max_dry_spell_days") or 0
    if sc.season == "kharif" and dry > 14:
        loss += min(0.015 * (dry - 14), 0.4)
    loss += min(0.03 * (f.get("heat_days_reproductive") or 0), 0.2)
    return 1 - loss


def _risk(rows: list[dict], mids: np.ndarray, sc: Scenario, water_penalty: float) -> dict:
    med = float(np.median(mids))
    low_years = float(np.mean(mids < LOW_YIELD_FRACTION * med)) if med > 0 else 1.0
    dry = float(np.mean([(r.get("max_dry_spell_days") or 0) >= 21 for r in rows]))
    heavy = float(np.mean([(r.get("rain_maturity_mm") or 0) >= 250 for r in rows]))
    score = 0.5 * low_years + 0.3 * dry + 0.2 * heavy + (0.5 if water_penalty < 1 else 0)
    level = "high" if score >= 0.4 else "medium" if score >= 0.2 else "low"
    return {"level": level, "score": round(min(score, 1.0), 2),
            "share_of_years_low_yield": round(low_years, 2),
            "share_of_years_long_dry_spell": round(dry, 2),
            "share_of_years_heavy_rain_near_harvest": round(heavy, 2)}


def _profit(y: dict, price: dict, sc: Scenario, area_ha) -> dict:
    cost = (sc.seed_cost_rs_ha + sc.other_cost_rs_ha + sc.n_kg_ha * UREA_RS_PER_KG_N
            + IRRIGATION_COST_RS_HA.get(sc.irrigation, 0))
    out = {"cost_rs_ha": round(cost), "price": price,
           "cost_note": "Seed and other costs are rough estimates from crop_varieties; edit them for your farm."}
    if price["rs_per_qtl"] is None:
        out.update({"low_rs_ha": None, "mid_rs_ha": None, "high_rs_ha": None})
        return out
    for k in ("low", "mid", "high"):
        out[f"{k}_rs_ha"] = round(y[k] * 10 * price["rs_per_qtl"] - cost)
    if area_ha:
        out["mid_rs_field"] = round(out["mid_rs_ha"] * float(area_ha))
    return out


# ------------------------------------------------------------------ planner (F9)

IRRIGATION_FROM_FIELD = {"canal": "full", "drip": "full", "sprinkler": "full", "borewell": "supplemental",
                         "tank": "supplemental", "rainfed": "rainfed", "unknown": "rainfed", None: "rainfed"}


def next_season(today: date) -> tuple[str, int]:
    m = today.month
    if 3 <= m <= 7:
        return "kharif", today.year
    if 8 <= m <= 11:
        return "rabi", today.year
    return "zaid", today.year + (1 if m == 12 else 0)


def scenario_from_variety(v: dict, irrigation: str) -> Scenario:
    start = tuple(int(x) for x in v["sowing_window_start"].split("-"))
    end = tuple(int(x) for x in v["sowing_window_end"].split("-"))
    mid = _mid_window(start, end)
    return Scenario(crop=v["crop"], variety=v["variety"], season=v["season"], sowing_month_day=mid,
                    duration_days=int(v["duration_days"]), n_kg_ha=float(v["recommended_n_kg_ha"] or 0),
                    recommended_n_kg_ha=float(v["recommended_n_kg_ha"] or 0), irrigation=irrigation,
                    water_need=v["water_need"] or "medium", seed_cost_rs_ha=float(v["seed_cost_rs_per_ha"] or 0),
                    other_cost_rs_ha=float(v["other_cost_rs_per_ha"] or 0))


def _mid_window(start: tuple[int, int], end: tuple[int, int]) -> tuple[int, int]:
    a = pd.Timestamp(2001, *start)
    b = pd.Timestamp(2001 if end >= start else 2002, *end)
    m = a + (b - a) / 2
    return m.month, m.day


def plan(ctx: FieldContext, season: str, top: int = 3) -> list[dict]:
    varieties = ctx.conn.execute(
        "SELECT * FROM crop_varieties WHERE season = %s AND (%s::text IS NULL OR %s = ANY(states) OR states = '{}')",
        (season, ctx.field["state"], ctx.field["state"]),
    ).fetchall()
    irrigation = IRRIGATION_FROM_FIELD.get(ctx.field["irrigation_type"], "rainfed")
    options = []
    for v in varieties:
        try:
            res = simulate(ctx, scenario_from_variety(v, irrigation))
        except LookupError as exc:
            options.append({"crop": v["crop"], "variety": v["variety"], "skipped": str(exc)})
            continue
        if "error" in res:
            continue
        p = res["profit"]
        if p.get("mid_rs_ha") is None:
            score = None
        else:
            # Risk-adjusted: penalise the downside (half the gap between median and bad years).
            score = p["mid_rs_ha"] - 0.5 * (p["mid_rs_ha"] - p["low_rs_ha"])
        options.append({
            "crop": v["crop"], "variety": v["variety"], "season": season,
            "sowing_window": f"{v['sowing_window_start']} to {v['sowing_window_end']}",
            "duration_days": v["duration_days"], "yield_t_ha": res["yield_t_ha"], "risk": res["risk"],
            "profit": p, "score": score, "assumptions": res["assumptions"], "method": res["method"],
        })
    ranked = sorted([o for o in options if o.get("score") is not None], key=lambda o: o["score"], reverse=True)
    unpriced = [o for o in options if o.get("score") is None and "skipped" not in o]
    return ranked[:top] + ([] if len(ranked) >= top else unpriced[: top - len(ranked)])
