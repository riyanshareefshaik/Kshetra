"""Per-season features shared by the crop classifier, yield model, SHAP and field twins.

Growth stages are split around the NDVI peak (roughly flowering):
  vegetative   sowing -> peak-20 days
  reproductive peak-20 -> peak+20 days   (flowering / grain filling, most sensitive)
  maturity     peak+20 -> harvest
"""
from datetime import timedelta

import numpy as np
import pandas as pd

from app.ml.season_detection import DetectedSeason

DRY_DAY_MM = 2.5             # IMD: a day with < 2.5 mm is a dry day
HEAT_DAY_C = 38.0
STAGE_HALF_WIDTH = 20

# Order matters: it is the column order for the yield model.
FEATURES = [
    "sowing_doy", "season_days", "peak_ndvi", "ndvi_integral", "greenup_rate", "senescence_rate",
    "vh_peak_db", "vh_vv_peak_db", "flood_signal_db",
    "rain_total_mm", "rain_vegetative_mm", "rain_reproductive_mm", "rain_maturity_mm",
    "max_dry_spell_days", "heat_days_reproductive", "tmax_mean_c", "et0_total_mm",
    "clay_pct", "sand_pct", "ph_h2o", "soc_g_per_kg",
]

FEATURE_INFO = {
    # name: (plain-English label, unit)
    "sowing_doy": ("sowing date", "day of year"),
    "season_days": ("crop duration", "days"),
    "peak_ndvi": ("peak crop greenness (NDVI)", ""),
    "ndvi_integral": ("total crop greenness over the season", "NDVI-days"),
    "greenup_rate": ("speed of early crop growth", "NDVI/day"),
    "senescence_rate": ("speed of crop drying before harvest", "NDVI/day"),
    "vh_peak_db": ("radar canopy signal at peak", "dB"),
    "vh_vv_peak_db": ("radar canopy structure at peak", "dB"),
    "flood_signal_db": ("standing water at planting (radar)", "dB"),
    "rain_total_mm": ("rainfall during the season", "mm"),
    "rain_vegetative_mm": ("rainfall during early growth", "mm"),
    "rain_reproductive_mm": ("rainfall around flowering", "mm"),
    "rain_maturity_mm": ("rainfall before harvest", "mm"),
    "max_dry_spell_days": ("longest dry spell", "days"),
    "heat_days_reproductive": ("very hot days (>= 38 C) around flowering", "days"),
    "tmax_mean_c": ("average daytime temperature", "C"),
    "et0_total_mm": ("crop water demand (ET0)", "mm"),
    "clay_pct": ("soil clay content", "%"),
    "sand_pct": ("soil sand content", "%"),
    "ph_h2o": ("soil pH", ""),
    "soc_g_per_kg": ("soil organic carbon", "g/kg"),
}


def _sum(series: pd.Series) -> float | None:
    return float(series.sum()) if series.notna().any() else None


def _mean(series: pd.Series) -> float | None:
    return float(series.mean()) if series.notna().any() else None


def max_dry_spell(rain: pd.Series) -> int | None:
    if rain.notna().sum() == 0:
        return None
    dry = (rain.fillna(0) < DRY_DAY_MM).to_numpy()
    best = run = 0
    for d in dry:
        run = run + 1 if d else 0
        best = max(best, run)
    return best


def season_features(df: pd.DataFrame, s: DetectedSeason, soil: dict) -> dict:
    """df: daily frame (ndvi_smoothed, sar_vv, sar_vh, rainfall_mm, temp_max_c, et0_mm)."""
    end = s.harvest_date or df.index[-1].date()
    sow, peak = pd.Timestamp(s.sowing_date), pd.Timestamp(s.peak_date)
    season = df.loc[sow:pd.Timestamp(end)]
    veg = df.loc[sow:peak - timedelta(days=STAGE_HALF_WIDTH)]
    rep = df.loc[peak - timedelta(days=STAGE_HALF_WIDTH):peak + timedelta(days=STAGE_HALF_WIDTH)]
    mat = df.loc[peak + timedelta(days=STAGE_HALF_WIDTH):pd.Timestamp(end)]
    around_peak = df.loc[peak - timedelta(days=10):peak + timedelta(days=10)]

    ndvi = season["ndvi_smoothed"]
    greenup_days = max((s.peak_date - s.greenup_date).days, 1)
    senesce_days = max(((s.harvest_date or end) - s.peak_date).days, 1)
    vh, vv = _mean(around_peak.get("sar_vh", pd.Series(dtype=float))), _mean(around_peak.get("sar_vv", pd.Series(dtype=float)))
    end_ndvi = df["ndvi_smoothed"].get(pd.Timestamp(end))

    feats = {
        "sowing_doy": s.sowing_date.timetuple().tm_yday,
        "season_days": (end - s.sowing_date).days,
        "peak_ndvi": s.peak_ndvi,
        "ndvi_integral": float((ndvi - s.trough_ndvi).clip(lower=0).sum()) if ndvi.notna().any() else None,
        "greenup_rate": (s.peak_ndvi - s.trough_ndvi) / greenup_days,
        "senescence_rate": (s.peak_ndvi - end_ndvi) / senesce_days if end_ndvi is not None and not np.isnan(end_ndvi) else None,
        "vh_peak_db": vh,
        "vh_vv_peak_db": vh - vv if vh is not None and vv is not None else None,
        "flood_signal_db": s.flood_signal_db or 0.0,
        "rain_total_mm": _sum(season["rainfall_mm"]),
        "rain_vegetative_mm": _sum(veg["rainfall_mm"]),
        "rain_reproductive_mm": _sum(rep["rainfall_mm"]),
        "rain_maturity_mm": _sum(mat["rainfall_mm"]),
        "max_dry_spell_days": max_dry_spell(season["rainfall_mm"].loc[:peak + timedelta(days=STAGE_HALF_WIDTH)]),
        "heat_days_reproductive": int((rep["temp_max_c"] >= HEAT_DAY_C).sum()) if rep["temp_max_c"].notna().any() else None,
        "tmax_mean_c": _mean(season["temp_max_c"]),
        "et0_total_mm": _sum(season["et0_mm"]),
        "clay_pct": soil.get("clay_pct"),
        "sand_pct": soil.get("sand_pct"),
        "ph_h2o": soil.get("ph_h2o"),
        "soc_g_per_kg": soil.get("soc_g_per_kg"),
    }
    return {k: (round(float(v), 4) if v is not None else None) for k, v in feats.items()}


# Fixed scales (typical spread of each feature) so twin vectors are comparable
# across fields without refitting a scaler whenever a field is added.
TWIN_SCALES = {
    "sowing_doy": 20, "season_days": 20, "peak_ndvi": 0.08, "ndvi_integral": 10,
    "rain_total_mm": 200, "max_dry_spell_days": 7, "tmax_mean_c": 2,
    "clay_pct": 8, "sand_pct": 10, "ph_h2o": 0.6, "soc_g_per_kg": 3,
}
TWIN_CENTERS = {
    "sowing_doy": 200, "season_days": 120, "peak_ndvi": 0.7, "ndvi_integral": 40,
    "rain_total_mm": 600, "max_dry_spell_days": 10, "tmax_mean_c": 32,
    "clay_pct": 35, "sand_pct": 35, "ph_h2o": 7.5, "soc_g_per_kg": 6,
}


def twin_vector(feats: dict) -> list[float]:
    """Scaled vector for k-NN; missing values sit at the centre (neutral)."""
    out = []
    for name, scale in TWIN_SCALES.items():
        v = feats.get(name)
        out.append(round(((v if v is not None else TWIN_CENTERS[name]) - TWIN_CENTERS[name]) / scale, 4))
    return out
