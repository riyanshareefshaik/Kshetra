import numpy as np
import pandas as pd
import pytest

from app.ml.explain_shap import baseline_reasons, shap_reasons
from app.ml.features import FEATURES
from app.ml.yield_model import YieldModel, baseline_yield


def training_frame(n=240, seed=0):
    """Yield driven by flowering rain and peak greenness, plus noise."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({f: rng.normal(0, 1, n) for f in FEATURES})
    df["rain_reproductive_mm"] = rng.uniform(20, 250, n)
    df["peak_ndvi"] = rng.uniform(0.55, 0.88, n)
    df["crop"] = rng.choice(["paddy", "maize"], n)
    df["year"] = rng.choice(range(2017, 2025), n)
    base = np.where(df["crop"] == "paddy", 5.0, 6.0)
    df["target"] = (base + 0.008 * (df["rain_reproductive_mm"] - 135) + 6 * (df["peak_ndvi"] - 0.72)
                    + rng.normal(0, 0.25, n))
    return df


@pytest.fixture(scope="module")
def model():
    return YieldModel.train(training_frame(), version="test")


def test_ranges_are_ordered_and_cover_truth(model):
    assert model.metrics["range_coverage"] >= 0.6
    assert model.metrics["mae_t_ha"] < 0.6
    feats = {f: 0.0 for f in FEATURES} | {"rain_reproductive_mm": 60, "peak_ndvi": 0.6}
    r = model.predict(feats, "paddy")
    assert 0 <= r.low <= r.mid <= r.high
    assert r.method == "model" and not r.is_forecast


def test_forecast_is_wider(model):
    feats = {f: 0.0 for f in FEATURES} | {"rain_reproductive_mm": 135, "peak_ndvi": 0.72}
    done, live = model.predict(feats, "maize"), model.predict(feats, "maize", in_progress=True)
    assert live.is_forecast and (live.high - live.low) > (done.high - done.low)


def test_shap_reasons_name_the_real_drivers(model):
    feats = {f: 0.0 for f in FEATURES} | {"rain_reproductive_mm": 30, "peak_ndvi": 0.58}
    reasons = shap_reasons(model, feats, "paddy")
    names = [r["feature"] for r in reasons[:2]]
    assert set(names) == {"rain_reproductive_mm", "peak_ndvi"}
    assert all(r["direction"] == "down" for r in reasons[:2])
    assert all("likely" in r["text"] and "caus" not in r["text"] for r in reasons)


def test_too_few_rows():
    with pytest.raises(ValueError):
        YieldModel.train(training_frame(n=10), version="x")


def test_save_and_load(model, tmp_path):
    model.save(tmp_path / "m.joblib")
    loaded = YieldModel.load(tmp_path / "m.joblib")
    feats = {f: 0.0 for f in FEATURES}
    assert loaded.predict(feats, "paddy").mid == model.predict(feats, "paddy").mid
    assert YieldModel.load(tmp_path / "missing.joblib") is None


def test_baseline_from_district_history():
    r = baseline_yield([5.0, 5.4, 4.8, 5.2], integral=44.0, same_crop_integrals=[40.0, 40.0])
    assert r.method == "baseline"
    assert r.mid == pytest.approx(5.1 * 1.06, abs=0.01)     # +10% greenness -> +6%
    assert r.low < r.mid < r.high
    assert baseline_yield([], 40.0, [40.0, 40.0]) is None
    flat = baseline_yield([5.0], None, [])
    assert flat.mid == 5.0 and flat.high - flat.low > 1.0     # minimum 12% spread


def test_baseline_reasons():
    events = [{"event_type": "dry_spell", "severity": 0.7,
               "evidence": {"dry_days": 21, "during_flowering": True}}]
    reasons = baseline_reasons(-0.2, events)
    assert reasons[0]["direction"] == "down" and "less green" in reasons[0]["text"]
    assert reasons[1]["text"] == "A dry spell of 21 days during flowering likely lowered yield."
