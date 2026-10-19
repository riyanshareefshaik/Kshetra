"""Irrigation advisor (feature 3): FAO-56 daily soil-water balance for the crop in the field.

  ETc = Kc(stage) x ET0                       crop water use
  Dr  = Dr_prev - effective rain - irrigation + ETc   root-zone depletion (0 = field capacity)
  TAW = available water (mm/m, from soil texture) x root depth;  RAW = p x TAW
  Irrigate when Dr reaches RAW; apply about Dr mm.

Kc, stage lengths, root depths and p are FAO-56 (Allen et al. 1998, Tables 11, 12, 22) typical
values. Irrigations recorded in the diary reset the balance. Paddy is grown flooded, so it gets
standing-water / alternate-wetting-and-drying advice instead of a soil-moisture threshold.
"""
from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class CropWater:
    kc: tuple[float, float, float]                  # initial, mid-season, end
    stages: tuple[float, float, float, float]      # share of season: initial, development, mid, late
    root_m: float
    p: float                                       # depletion allowed before stress


CROPS = {
    "paddy": CropWater((1.05, 1.20, 0.75), (0.17, 0.17, 0.44, 0.22), 0.5, 0.20),
    "maize": CropWater((0.30, 1.20, 0.60), (0.17, 0.28, 0.33, 0.22), 1.0, 0.55),
    "cotton": CropWater((0.35, 1.15, 0.60), (0.17, 0.27, 0.33, 0.23), 1.2, 0.65),
    "pulses": CropWater((0.40, 1.05, 0.35), (0.20, 0.30, 0.30, 0.20), 0.6, 0.45),
    "chilli": CropWater((0.60, 1.05, 0.90), (0.20, 0.30, 0.35, 0.15), 0.6, 0.30),
    "sugarcane": CropWater((0.40, 1.25, 0.75), (0.10, 0.20, 0.50, 0.20), 1.2, 0.65),
}
# Available water (field capacity - wilting point), mm per metre of soil (FAO-56 Table 19 mid-values)
AW_MM_PER_M = {"sand": 70, "loamy sand": 90, "sandy loam": 120, "loam": 160, "silt loam": 180, "silt": 180,
               "sandy clay loam": 140, "clay loam": 170, "silty clay loam": 180, "sandy clay": 160,
               "silty clay": 180, "clay": 170}
DEFAULT_AW = 150
INEFFECTIVE_RAIN_MM = 5      # light showers mostly evaporate before reaching roots


def kc_on(cw: CropWater, das: int, duration: int) -> float:
    ini, dev, mid, _ = (s * duration for s in cw.stages)
    k_ini, k_mid, k_end = cw.kc
    if das <= ini:
        return k_ini
    if das <= ini + dev:
        return k_ini + (k_mid - k_ini) * (das - ini) / dev
    if das <= ini + dev + mid:
        return k_mid
    late = duration - (ini + dev + mid)
    return max(k_end, k_mid + (k_end - k_mid) * (das - ini - dev - mid) / max(late, 1))


def stage_name(cw: CropWater, das: int, duration: int) -> str:
    ini, dev, mid, _ = (s * duration for s in cw.stages)
    if das <= ini:
        return "establishment"
    if das <= ini + dev:
        return "vegetative growth"
    if das <= ini + dev + mid:
        return "flowering / grain filling"
    return "maturity"


def advise(crop: str, sowing: date, duration: int, weather: pd.DataFrame, irrigations: list[date],
           soil_texture: str | None, area_ha: float | None, today: date) -> dict:
    """weather: daily index with rain_mm, et0_mm (observed past + forecast future, no gaps)."""
    cw = CROPS.get(crop)
    if cw is None:
        return {"error": f"no water model for {crop}"}
    das_today = (today - sowing).days
    if das_today < 0:
        return {"status": "not_sown", "message": f"{crop.title()} is not sown yet (planned {sowing.isoformat()})."}
    if das_today > duration + 10:
        return {"status": "harvested", "message": "The crop should be harvested; no irrigation needed."}

    aw = AW_MM_PER_M.get((soil_texture or "").lower(), DEFAULT_AW)
    taw = aw * cw.root_m
    raw = cw.p * taw
    irrigated = set(irrigations)
    dr, rows, next_irrigation = 0.0, [], None
    for day, w in weather.loc[pd.Timestamp(sowing):].iterrows():
        d = day.date()
        das = (d - sowing).days
        if das > duration:
            break
        etc = kc_on(cw, das, duration) * (w["et0_mm"] or 0)
        rain = w["rain_mm"] or 0
        eff = 0.0 if rain < INEFFECTIVE_RAIN_MM else 0.8 * rain
        dr = min(max(dr + etc - eff, 0.0), taw)
        if d in irrigated:
            dr = 0.0
        if d > today and next_irrigation is None and dr >= raw:
            next_irrigation = {"date": d.isoformat(), "amount_mm": round(dr)}
        rows.append({"date": d.isoformat(), "depletion_mm": round(dr, 1), "etc_mm": round(etc, 2),
                     "rain_mm": round(rain, 1), "forecast": d > today})

    now = next((r for r in reversed(rows) if not r["forecast"]), rows[-1] if rows else None)
    current = now["depletion_mm"] if now else 0.0
    stage = stage_name(cw, das_today, duration)
    out = {"crop": crop, "stage": stage, "days_after_sowing": das_today, "taw_mm": round(taw), "raw_mm": round(raw),
           "depletion_mm": current, "depletion_pct_of_raw": round(100 * current / raw) if raw else None,
           "series": rows[-37:], "soil_texture": soil_texture or "unknown (assumed medium soil)"}

    if crop == "paddy":
        flowering = stage == "flowering / grain filling"
        out.update(status="paddy", message=(
            "Keep 2–5 cm of standing water during flowering; do not let the field dry now." if flowering else
            "Use alternate wetting and drying: let the water drop until the soil just cracks (or 15 cm below "
            "the surface in a field tube), then flood again to 5 cm. This saves about a quarter of the water."))
        return out

    if current >= raw:
        amount = round(current)
        out.update(status="irrigate_now", amount_mm=amount,
                   message=f"Irrigate now: the root zone is dry ({current:.0f} mm used, limit {raw:.0f} mm). "
                           f"Apply about {amount} mm.")
    elif next_irrigation:
        days = (date.fromisoformat(next_irrigation["date"]) - today).days
        out.update(status="irrigate_soon", amount_mm=next_irrigation["amount_mm"], next_date=next_irrigation["date"],
                   message=f"Irrigate in about {days} day{'s' if days != 1 else ''} ({next_irrigation['date']}), "
                           f"about {next_irrigation['amount_mm']} mm.")
    else:
        out.update(status="ok", message="No irrigation needed in the next 7 days: the soil holds enough water "
                                        "with the expected rain.")
    if out.get("amount_mm") and area_ha:
        out["litres_for_field"] = round(out["amount_mm"] * float(area_ha) * 10_000)
    return out
