"""Synthetic field histories for tests and offline UI development.

Kharif paddy (radar sees puddling) followed by rabi pulses each year. Data made
here is never real: fields built from it are flagged is_synthetic and every
screen and report says so.
"""
from datetime import date

import numpy as np
import pandas as pd


def hump(days: np.ndarray, start: float, peak: float, end: float, base: float, top: float) -> np.ndarray:
    """Smooth rise from start to peak, fall from peak to end (in day numbers)."""
    out = np.full(days.shape, 0.0)
    rise = (days >= start) & (days <= peak)
    fall = (days > peak) & (days <= end)
    out[rise] = (top - base) * (np.sin(np.pi / 2 * (days[rise] - start) / (peak - start)) ** 2)
    out[fall] = (top - base) * (np.cos(np.pi / 2 * (days[fall] - peak) / (end - peak)) ** 2)
    return out


def field_frame(years=(2020, 2021, 2022), end: date | None = None, paddy_top=0.8, pulses_top=0.55,
                seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{years[0]}-01-01", end or f"{years[-1] + 1}-03-31", freq="D")
    t = (idx - idx[0]).days.to_numpy().astype(float)
    base = 0.18
    ndvi = np.full(len(idx), base)
    vh = np.full(len(idx), -17.0) + rng.normal(0, 0.3, len(idx))
    for y in years:
        d0 = (pd.Timestamp(f"{y}-01-01") - idx[0]).days
        # Kharif paddy: puddled ~Jul 5, green-up ~Jul 25, peak ~Sep 20, harvest ~Nov 15
        ndvi += hump(t, d0 + 200, d0 + 263, d0 + 330, base, paddy_top)
        vh[(t >= d0 + 183) & (t <= d0 + 192)] = -24.0
        # Rabi pulses: green-up ~Dec 10, peak ~Jan 15, harvest ~Feb 20
        ndvi += hump(t, d0 + 342, d0 + 380, d0 + 415, base, pulses_top)
    df = pd.DataFrame(index=idx)
    df["ndvi_smoothed"] = ndvi.round(4)
    obs = np.zeros(len(idx), bool)
    obs[::5] = True
    df["ndvi"] = np.where(obs, df["ndvi_smoothed"], np.nan)
    df["ndvi_source"] = np.where(obs, "s2", None)
    s1 = np.zeros(len(idx), bool)
    s1[1::6] = True
    df["sar_vh"] = np.where(s1, vh, np.nan)
    df["sar_vv"] = np.where(s1, vh + 8, np.nan)
    month = idx.month.to_numpy()
    df["rainfall_mm"] = np.where((month >= 6) & (month <= 10), 8.0, 0.5)
    df["temp_max_c"] = 33.0
    df["et0_mm"] = 4.5
    return df
