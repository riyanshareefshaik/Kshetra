"""Stress events within a season (F4): dry spells, waterlogging, sudden damage, heat.

Each event carries the numbers behind it (`evidence`) so the app and the LLM
can show why it was flagged. Thresholds follow common agronomy / IMD usage and
are deliberately conservative.
"""
from datetime import timedelta

import numpy as np
import pandas as pd

from app.ml.features import DRY_DAY_MM, HEAT_DAY_C, STAGE_HALF_WIDTH
from app.ml.season_detection import DetectedSeason

DRY_SPELL_MIN_DAYS = 14
DRY_SPELL_MIN_NORMAL_MM = 40    # only flag if this window normally gets at least this much rain
HEAVY_RAIN_3DAY_MM = 150        # 3-day total that floods low-lying fields
WATER_VV_DB = -17.0             # Sentinel-1 VV this dark over a crop means standing water
ESTABLISHMENT_DAYS = 30         # paddy is supposed to be flooded early on
DAMAGE_DROP = 0.15              # NDVI fall (observed) in <= 12 days before maturity
DAMAGE_WINDOW_DAYS = 12
HEAT_MIN_RUN = 3


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(start, end) index pairs of consecutive True values, end inclusive."""
    runs, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _event(kind, start, end, severity, evidence):
    return {
        "event_type": kind,
        "start_date": pd.Timestamp(start).date(),
        "end_date": pd.Timestamp(end).date(),
        "severity": round(float(min(max(severity, 0.0), 1.0)), 2),
        "evidence": evidence,
    }


def detect_stress(df: pd.DataFrame, s: DetectedSeason, crop: str | None) -> list[dict]:
    end = pd.Timestamp(s.harvest_date or df.index[-1])
    sow, peak = pd.Timestamp(s.sowing_date), pd.Timestamp(s.peak_date)
    season = df.loc[sow:end]
    events: list[dict] = []
    if season.empty:
        return events

    # --- dry spells: sowing -> end of flowering (later dry weather helps harvest)
    growing = season.loc[:peak + timedelta(days=STAGE_HALF_WIDTH)]
    rain = growing["rainfall_mm"]
    if rain.notna().any():
        # Rabi in coastal Andhra is normally dry (crops use stored soil moisture or
        # irrigation), so a dry spell only counts where rain is normally expected:
        # compare with this field's own average rain for the same calendar days.
        normal_by_doy = df["rainfall_mm"].groupby(df.index.dayofyear).mean()
        for a, b in _runs((rain.fillna(0) < DRY_DAY_MM).to_numpy()):
            days = b - a + 1
            if days < DRY_SPELL_MIN_DAYS:
                continue
            window = growing.iloc[a:b + 1]
            normal = float(normal_by_doy.reindex(window.index.dayofyear).fillna(0).sum())
            if normal < DRY_SPELL_MIN_NORMAL_MM:
                continue
            et0 = float(window["et0_mm"].sum()) if window["et0_mm"].notna().any() else None
            in_flowering = window.index[-1] >= peak - timedelta(days=STAGE_HALF_WIDTH)
            severity = min(days / 35, 1.0) * (1.2 if in_flowering else 1.0)
            events.append(_event("dry_spell", window.index[0], window.index[-1], severity, {
                "dry_days": days,
                "rain_mm": round(float(window["rainfall_mm"].sum()), 1),
                "normal_rain_mm": round(normal, 1),
                "et0_mm": round(et0, 1) if et0 is not None else None,
                "during_flowering": bool(in_flowering),
            }))

    # --- waterlogging / flood: heavy 3-day rain, or radar sees standing water
    skip_until = sow + timedelta(days=ESTABLISHMENT_DAYS if crop == "paddy" else 0)
    later = season.loc[skip_until:]
    if not later.empty:
        rain3 = later["rainfall_mm"].rolling(3, min_periods=1).sum()
        heavy = (rain3 >= HEAVY_RAIN_3DAY_MM).to_numpy()
        water = (later["sar_vv"] <= WATER_VV_DB).to_numpy() if "sar_vv" in later else np.zeros(len(later), bool)
        for a, b in _runs(heavy | water):
            window = later.iloc[a:b + 1]
            vv_min = window["sar_vv"].min() if "sar_vv" in window and window["sar_vv"].notna().any() else None
            radar_seen = vv_min is not None and vv_min <= WATER_VV_DB
            r3 = float(rain3.iloc[a:b + 1].max())
            kind = "flood" if radar_seen and r3 >= HEAVY_RAIN_3DAY_MM else "waterlogging"
            severity = 0.4 + 0.3 * radar_seen + 0.3 * min(r3 / 300, 1.0)
            events.append(_event(kind, window.index[0], window.index[-1], severity, {
                "max_rain_3day_mm": round(r3, 1),
                "sar_vv_min_db": round(float(vv_min), 2) if vv_min is not None else None,
                "radar_standing_water": bool(radar_seen),
            }))

    # --- sudden damage: real (not radar-filled) NDVI drops fast before maturity
    if "ndvi_source" in season:
        obs = season.loc[:peak + timedelta(days=STAGE_HALF_WIDTH)]
        obs = obs.loc[obs["ndvi_source"] == "s2", "ndvi"].dropna()
        for i in range(1, len(obs)):
            prev_t, t = obs.index[i - 1], obs.index[i]
            drop = obs.iloc[i - 1] - obs.iloc[i]
            if (t - prev_t).days <= DAMAGE_WINDOW_DAYS and drop >= DAMAGE_DROP:
                events.append(_event("sudden_damage", prev_t, t, drop / 0.4, {
                    "ndvi_before": round(float(obs.iloc[i - 1]), 3),
                    "ndvi_after": round(float(obs.iloc[i]), 3),
                    "days": int((t - prev_t).days),
                    "rain_mm_window": round(float(season.loc[prev_t:t, "rainfall_mm"].sum()), 1),
                }))

    # --- heat around flowering
    rep = season.loc[peak - timedelta(days=STAGE_HALF_WIDTH):peak + timedelta(days=STAGE_HALF_WIDTH)]
    if rep["temp_max_c"].notna().any():
        for a, b in _runs((rep["temp_max_c"] >= HEAT_DAY_C).to_numpy()):
            days = b - a + 1
            if days >= HEAT_MIN_RUN:
                window = rep.iloc[a:b + 1]
                events.append(_event("heat_stress", window.index[0], window.index[-1], days / 7, {
                    "hot_days": days, "tmax_max_c": round(float(window["temp_max_c"].max()), 1)}))
    return events
