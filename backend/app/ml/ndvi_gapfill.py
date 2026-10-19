"""Fill monsoon cloud gaps in Sentinel-2 NDVI using radar, then smooth.

Radar sees through clouds. On dates where a field has both a clear Sentinel-2
NDVI (within +-3 days) and a radar observation, we fit radar -> NDVI. On cloudy
dates with radar but no clear NDVI, the model predicts NDVI. Predicted values
are flagged ndvi_source='sar_fill' and only used if the model's cross-validated
R^2 is good enough.

One model per radar source; on a given date the best available source wins:
NISAR L-band, then NISAR S-band, then Sentinel-1.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score

PAIR_WINDOW_DAYS = 3        # radar and optical within this many days count as a pair
GAP_DAYS = 5                # fill only if no clear optical within this many days
MIN_PAIRS = {"s1": 30, "nisar_l": 15, "nisar_s": 15}
MIN_R2 = 0.5
SMOOTH_WINDOW = 31          # days, Savitzky-Golay
MAX_INTERP_GAP = 60         # days without any NDVI -> leave smoothed NDVI empty

RADAR_SOURCES = {
    # name: (co-pol column, cross-pol column)
    "nisar_l": ("nisar_l_hh", "nisar_l_hv"),
    "nisar_s": ("nisar_s_hh", "nisar_s_hv"),
    "s1": ("sar_vv", "sar_vh"),
}


@dataclass
class FillModel:
    source: str
    model: RandomForestRegressor
    r2: float
    n_pairs: int


def _features(df: pd.DataFrame, co: str, cross: str) -> pd.DataFrame:
    # Radar only. Day-of-year features would let the model predict a typical
    # season from the calendar and hide what actually happened on the field
    # (late sowing, crop loss), which is exactly what we need to see.
    return pd.DataFrame(
        {
            "co": df[co].to_numpy(),
            "cross": df[cross].to_numpy(),
            "ratio": (df[cross] - df[co]).to_numpy(),   # dB difference = log ratio
        },
        index=df.index,
    )


def _nearest_ndvi(obs: pd.Series, dates: pd.DatetimeIndex, window: int) -> pd.Series:
    """For each date, the clear NDVI observation closest in time within +-window days."""
    if obs.empty:
        return pd.Series(np.nan, index=dates)
    left = pd.DataFrame({"date": dates}).sort_values("date")
    right = obs.rename("ndvi").rename_axis("obs_date").reset_index().sort_values("obs_date")
    merged = pd.merge_asof(
        left, right, left_on="date", right_on="obs_date",
        direction="nearest", tolerance=pd.Timedelta(days=window),
    )
    return pd.Series(merged["ndvi"].to_numpy(), index=pd.DatetimeIndex(merged["date"]))


def fit_models(df: pd.DataFrame) -> dict[str, FillModel]:
    """df: daily-indexed frame with 'ndvi' (clear S2 only) and radar columns."""
    obs = df["ndvi"].dropna()
    models: dict[str, FillModel] = {}
    for source, (co, cross) in RADAR_SOURCES.items():
        if co not in df or cross not in df:
            continue
        radar = df[[co, cross]].dropna()
        if radar.empty:
            continue
        target = _nearest_ndvi(obs, radar.index, PAIR_WINDOW_DAYS)
        mask = target.notna().to_numpy()
        if mask.sum() < MIN_PAIRS[source]:
            continue
        X = _features(radar, co, cross)[mask]
        y = target[mask].to_numpy()
        rf = RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=0, n_jobs=-1)
        r2 = float(np.mean(cross_val_score(rf, X, y, cv=5, scoring="r2")))
        if r2 < MIN_R2:
            continue
        rf.fit(X, y)
        models[source] = FillModel(source, rf, r2, int(mask.sum()))
    return models


def fill_and_smooth(df: pd.DataFrame, models: dict[str, FillModel] | None = None) -> pd.DataFrame:
    """Return df with ndvi (observed + radar-filled), ndvi_source and ndvi_smoothed.

    df must have a daily DatetimeIndex and an 'ndvi' column holding clear
    Sentinel-2 observations only.
    """
    df = df.sort_index().copy()
    if models is None:
        models = fit_models(df)

    df["ndvi_source"] = np.where(df["ndvi"].notna(), "s2", None)
    obs = df["ndvi"].dropna()
    near_obs = _nearest_ndvi(obs, df.index, GAP_DAYS).notna().to_numpy()

    # Best source last, so it overwrites weaker sources on the same date.
    for source in ("s1", "nisar_s", "nisar_l"):
        fm = models.get(source)
        if fm is None:
            continue
        co, cross = RADAR_SOURCES[source]
        candidates = df[co].notna() & df[cross].notna() & ~near_obs & df["ndvi_source"].ne("s2")
        if not candidates.any():
            continue
        X = _features(df.loc[candidates], co, cross)
        df.loc[candidates, "ndvi"] = np.clip(fm.model.predict(X), -1, 1).round(4)
        df.loc[candidates, "ndvi_source"] = "sar_fill"

    df["ndvi_smoothed"] = smooth(df["ndvi"])
    return df


def smooth(ndvi: pd.Series) -> pd.Series:
    """Daily Savitzky-Golay smoothing of sparse NDVI; empty across long data gaps."""
    s = ndvi.astype("float64")
    if s.notna().sum() < 4:
        return pd.Series(np.nan, index=s.index)
    interp = s.interpolate(method="time", limit_area="inside")
    valid = interp.notna().to_numpy()
    out = np.full(len(s), np.nan)
    if valid.sum() >= SMOOTH_WINDOW:
        out[valid] = savgol_filter(interp[valid].to_numpy(), SMOOTH_WINDOW, 2)
    else:
        out[valid] = interp[valid].to_numpy()

    # Blank days that are far from any real value.
    has = s.notna().to_numpy()
    idx = np.arange(len(s))
    last = np.where(has, idx, -10**9)
    last = np.maximum.accumulate(last)
    nxt = np.where(has, idx, 10**9)
    nxt = np.minimum.accumulate(nxt[::-1])[::-1]
    gap = (nxt - last)
    out[(gap > MAX_INTERP_GAP) & ~has] = np.nan
    return pd.Series(np.clip(out, -1, 1).round(4), index=s.index)
