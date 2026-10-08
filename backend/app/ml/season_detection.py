"""Detect crop seasons (sowing, peak, harvest) from a field's daily NDVI curve.

Each crop season shows up as a hump in smoothed NDVI. For every hump:
  * green-up  = NDVI first rises 20% of the way from the left trough to the peak
  * harvest   = NDVI falls 70% of the way from the peak to the right trough
  * sowing    = green-up minus ~15 days (seedlings are invisible from space at first)

Radar refines sowing for transplanted paddy: fields are flooded and puddled
just before transplanting, which shows as a sharp drop in cross-pol backscatter
(open water is dark to radar). If that drop appears in the 45 days before
green-up, its date is used as the sowing/transplanting date.

Season names follow the Indian calendar by sowing month:
  kharif Jun-Sep, rabi Oct-Jan, zaid Feb-May. `year` is the sowing year
  (rabi sown in Jan counts as the previous year's rabi).
"""
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

MIN_PEAK_NDVI = 0.35
MIN_PROMINENCE = 0.12
MIN_PEAK_DISTANCE_DAYS = 60
SEARCH_DAYS = 150
GREENUP_FRACTION = 0.20
HARVEST_FRACTION = 0.70
EMERGENCE_LAG_DAYS = 15
FLOOD_WINDOW_DAYS = 45
FLOOD_DROP_DB = 3.0          # below the window's median
FLOOD_MAX_DB = -20.0         # and darker than this (VH / HV)


@dataclass
class DetectedSeason:
    year: int
    season: str
    sowing_date: date
    greenup_date: date
    peak_date: date
    harvest_date: date | None          # None while the crop is still in the field
    peak_ndvi: float
    trough_ndvi: float
    date_detection: str                # 'ndvi' | 'sar' | 'nisar'
    flood_signal_db: float | None      # how far backscatter dropped at puddling, if seen
    obs_fraction: float                # share of season days near a real (not filled) NDVI
    in_progress: bool = False
    notes: list[str] = field(default_factory=list)


def season_name(sowing: date) -> tuple[str, int]:
    m = sowing.month
    if 6 <= m <= 9:
        return "kharif", sowing.year
    if m >= 10:
        return "rabi", sowing.year
    if m == 1:
        return "rabi", sowing.year - 1
    return "zaid", sowing.year


def _first_crossing(values: np.ndarray, start: int, stop: int, level: float, rising: bool) -> int | None:
    step = 1 if stop >= start else -1
    for i in range(start, stop, step):
        v = values[i]
        if np.isnan(v):
            continue
        if (rising and v >= level) or (not rising and v <= level):
            return i
    return None


def _flood_date(df: pd.DataFrame, greenup_idx: int) -> tuple[int | None, float | None, str]:
    """Darkest radar date before green-up if it looks like standing water."""
    lo = max(0, greenup_idx - FLOOD_WINDOW_DAYS)
    for col, source in (("nisar_l_hv", "nisar"), ("sar_vh", "sar")):
        if col not in df:
            continue
        window = df[col].iloc[lo:greenup_idx + 1]
        obs = window.dropna()
        if len(obs) < 3:
            continue
        # Compare against the wider context so a fully flooded window still stands out.
        context = df[col].iloc[max(0, lo - 60):greenup_idx + 30].dropna()
        drop = float(context.median() - obs.min())
        if obs.min() <= FLOOD_MAX_DB and drop >= FLOOD_DROP_DB:
            return df.index.get_loc(obs.idxmin()), round(drop, 2), source
    return None, None, "ndvi"


def detect_seasons(df: pd.DataFrame) -> list[DetectedSeason]:
    """df: daily DatetimeIndex with ndvi_smoothed; optional ndvi_source, sar_vh, nisar_l_hv."""
    if "ndvi_smoothed" not in df or df["ndvi_smoothed"].notna().sum() < 60:
        return []
    df = df.sort_index()
    s = df["ndvi_smoothed"].to_numpy(dtype="float64")
    low = np.nanmin(s)
    filled = np.where(np.isnan(s), low, s)
    # Pad both ends with the lowest value so a crop that is still green when the
    # data ends (or starts) still counts as a peak; it is then marked in progress.
    padded = np.concatenate(([low], filled, [low]))
    peaks, _ = find_peaks(padded, height=MIN_PEAK_NDVI, prominence=MIN_PROMINENCE,
                          distance=MIN_PEAK_DISTANCE_DAYS)
    peaks = peaks - 1
    observed = (df.get("ndvi_source") == "s2").to_numpy() if "ndvi_source" in df else np.zeros(len(df), bool)
    dates = df.index

    found: dict[tuple[int, str], DetectedSeason] = {}
    for k, p in enumerate(peaks):
        if np.isnan(s[p]):
            continue
        left_lim = max(0, p - SEARCH_DAYS, peaks[k - 1] if k > 0 else 0)
        right_lim = min(len(s) - 1, p + SEARCH_DAYS, peaks[k + 1] if k + 1 < len(peaks) else len(s) - 1)
        left = s[left_lim:p + 1]
        right = s[p:right_lim + 1]
        if np.all(np.isnan(left)) or np.all(np.isnan(right)):
            continue
        l_idx = left_lim + int(np.nanargmin(left))
        r_idx = p + int(np.nanargmin(right))
        trough_l, trough_r = s[l_idx], s[r_idx]

        g_idx = _first_crossing(s, l_idx, p + 1, trough_l + GREENUP_FRACTION * (s[p] - trough_l), rising=True)
        if g_idx is None:
            continue
        # Data ends before the crop has clearly declined -> still in the field.
        in_progress = r_idx >= len(s) - 15 and (s[p] - trough_r) < 0.5 * (s[p] - trough_l)
        h_idx = None
        if not in_progress:
            h_level = s[p] - HARVEST_FRACTION * (s[p] - trough_r)
            h_idx = _first_crossing(s, p, r_idx + 1, h_level, rising=False)
            if h_idx is None:
                continue

        f_idx, flood_drop, source = _flood_date(df, g_idx)
        if f_idx is not None:
            sowing = dates[f_idx].date()
        else:
            sowing = (dates[g_idx] - pd.Timedelta(days=EMERGENCE_LAG_DAYS)).date()
            source = "ndvi"

        end_idx = h_idx if h_idx is not None else len(s) - 1
        span = observed[g_idx:end_idx + 1]
        name, year = season_name(sowing)
        cand = DetectedSeason(
            year=year,
            season=name,
            sowing_date=sowing,
            greenup_date=dates[g_idx].date(),
            peak_date=dates[p].date(),
            harvest_date=dates[h_idx].date() if h_idx is not None else None,
            peak_ndvi=round(float(s[p]), 3),
            trough_ndvi=round(float(min(trough_l, trough_r)), 3),
            date_detection=source,
            flood_signal_db=flood_drop,
            obs_fraction=round(_near_obs_fraction(span), 2),
            in_progress=in_progress,
        )
        key = (year, name)
        # Two humps in one season slot (e.g. ratoon): keep the stronger one.
        if key not in found or cand.peak_ndvi > found[key].peak_ndvi:
            found[key] = cand
    return sorted(found.values(), key=lambda x: x.sowing_date)


def _near_obs_fraction(span: np.ndarray, window: int = 8) -> float:
    """Share of days with a real Sentinel-2 observation within +-window days."""
    if span.size == 0:
        return 0.0
    kernel = np.ones(2 * window + 1)
    near = np.convolve(span.astype(float), kernel, mode="same") > 0
    return float(near.mean())
