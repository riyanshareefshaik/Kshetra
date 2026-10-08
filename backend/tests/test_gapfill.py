import numpy as np
import pandas as pd

from app.ml.ndvi_gapfill import fill_and_smooth, fit_models, smooth


def synthetic_field(seed=0):
    """Two crop seasons a year; Sentinel-1 VH tracks NDVI; monsoon clouds hide July-Sept."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", "2023-12-31", freq="D")
    doy = idx.dayofyear.to_numpy()
    true = 0.2 + 0.55 * np.exp(-((doy - 240) / 35.0) ** 2) + 0.45 * np.exp(-((doy - 50) / 30.0) ** 2)
    df = pd.DataFrame(index=idx)
    df["true"] = true
    s2 = np.zeros(len(idx), bool)
    s2[::5] = True
    monsoon = (idx.month >= 7) & (idx.month <= 9)
    s2 &= ~(monsoon & (rng.random(len(idx)) < 0.9))
    df["ndvi"] = np.where(s2, true + rng.normal(0, 0.02, len(idx)), np.nan)
    s1 = np.zeros(len(idx), bool)
    s1[2::6] = True
    df["sar_vh"] = np.where(s1, -24 + 14 * true + rng.normal(0, 0.4, len(idx)), np.nan)
    df["sar_vv"] = np.where(s1, -14 + 6 * true + rng.normal(0, 0.4, len(idx)), np.nan)
    return df


def test_radar_fills_monsoon_gaps():
    df = synthetic_field()
    models = fit_models(df)
    assert "s1" in models and models["s1"].r2 > 0.8
    out = fill_and_smooth(df, models)
    filled = out[out["ndvi_source"] == "sar_fill"]
    assert len(filled) > 20
    assert filled.index.month.isin([7, 8, 9]).mean() > 0.7
    err = (filled["ndvi"] - filled["true"]).abs().mean()
    assert err < 0.06
    # Observed values are never overwritten.
    obs = df["ndvi"].notna()
    assert (out.loc[obs, "ndvi_source"] == "s2").all()
    sm = out["ndvi_smoothed"].dropna()
    assert (sm - out.loc[sm.index, "true"]).abs().mean() < 0.05


def test_no_model_when_radar_does_not_explain_ndvi():
    df = synthetic_field()
    rng = np.random.default_rng(1)
    df["sar_vh"] = np.where(df["sar_vh"].notna(), rng.normal(-18, 3, len(df)), np.nan)
    df["sar_vv"] = np.where(df["sar_vv"].notna(), rng.normal(-10, 3, len(df)), np.nan)
    assert fit_models(df) == {}


def test_smooth_leaves_long_gaps_empty():
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    s = pd.Series(np.nan, index=idx)
    s.iloc[[0, 10, 20, 30, 150, 160, 170]] = [0.2, 0.3, 0.4, 0.5, 0.6, 0.5, 0.4]
    out = smooth(s)
    assert out.iloc[15] == out.iloc[15]          # filled between close observations
    assert np.isnan(out.iloc[90])                # 120-day gap stays empty
