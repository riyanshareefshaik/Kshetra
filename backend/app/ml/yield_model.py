"""Yield ranges in t/ha (F5): never a single number.

Two methods, chosen automatically:

1. `YieldModel` (trained, preferred): three XGBoost quantile regressors give
   the 10th, 50th and 90th percentile. Trained by scripts/train_models.py on
   season features with district yields (ICRISAT / data.gov.in) as the label.
   No free field-level yields exist for India, so the label is the district
   average for that crop and year: the model learns how weather, timing and
   crop vigour move yields, and the range stays honest about the rest.

2. `baseline_yield` (fallback, until enough data to train): the district's
   recent yields for that crop, shifted by how this season's total greenness
   compares with the same field's other seasons of that crop.

In-progress seasons get a wider range and are flagged as forecasts.
"""
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median, pstdev

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.ml.crop_classifier import CROPS
from app.ml.features import FEATURES

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "yield_model.joblib"
QUANTILES = (0.1, 0.5, 0.9)
MIN_TRAIN_ROWS = 30
GREENNESS_ELASTICITY = 0.6     # baseline: +10% season greenness -> +6% yield (assumption)
MIN_REL_SPREAD = 0.12
FORECAST_WIDEN = 1.5


@dataclass
class YieldRange:
    low: float
    mid: float
    high: float
    method: str                    # 'model' | 'baseline'
    is_forecast: bool = False
    details: dict = field(default_factory=dict)

    def as_db(self) -> dict:
        return {"yield_low_t_ha": self.low, "yield_mid_t_ha": self.mid, "yield_high_t_ha": self.high,
                "yield_is_forecast": self.is_forecast}


def _ordered(low: float, mid: float, high: float) -> tuple[float, float, float]:
    a, b, c = sorted(max(0.0, v) for v in (low, mid, high))
    return round(a, 2), round(b, 2), round(c, 2)


def _widen(r: YieldRange) -> YieldRange:
    half_lo, half_hi = (r.mid - r.low) * FORECAST_WIDEN, (r.high - r.mid) * FORECAST_WIDEN
    low, mid, high = _ordered(r.mid - half_lo, r.mid, r.mid + half_hi)
    return YieldRange(low, mid, high, r.method, True, r.details)


class YieldModel:
    def __init__(self, models: dict, feature_means: dict, metrics: dict, version: str):
        self.models = models
        self.feature_means = feature_means
        self.metrics = metrics
        self.version = version
        self.columns = FEATURES + [f"crop_{c}" for c in CROPS]

    @staticmethod
    def matrix(rows: list[dict], crops: list[str]) -> pd.DataFrame:
        data = []
        for feats, crop in zip(rows, crops):
            r = {f: (np.nan if feats.get(f) is None else feats[f]) for f in FEATURES}
            r.update({f"crop_{c}": float(crop == c) for c in CROPS})
            data.append(r)
        return pd.DataFrame(data, columns=FEATURES + [f"crop_{c}" for c in CROPS])

    def predict(self, feats: dict, crop: str, in_progress: bool = False) -> YieldRange:
        X = self.matrix([feats], [crop])
        low, mid, high = _ordered(*(float(self.models[q].predict(X)[0]) for q in QUANTILES))
        r = YieldRange(low, mid, high, "model", details={"model_version": self.version})
        return _widen(r) if in_progress else r

    @classmethod
    def train(cls, df: pd.DataFrame, version: str) -> "YieldModel":
        """df columns: FEATURES..., crop, year, target (t/ha)."""
        if len(df) < MIN_TRAIN_ROWS:
            raise ValueError(f"need at least {MIN_TRAIN_ROWS} labelled seasons, have {len(df)}")
        X = cls.matrix(df[FEATURES].to_dict("records"), df["crop"].tolist())
        y = df["target"].to_numpy()
        metrics = cls._evaluate(X, y, df["year"].to_numpy())
        models = {q: cls._fit(X, y, q) for q in QUANTILES}
        means = {f: float(df[f].mean()) for f in FEATURES if df[f].notna().any()}
        return cls(models, means, metrics, version)

    @staticmethod
    def _fit(X, y, q) -> XGBRegressor:
        m = XGBRegressor(objective="reg:quantileerror", quantile_alpha=q, n_estimators=300,
                         max_depth=3, learning_rate=0.05, subsample=0.8, min_child_weight=3,
                         random_state=0)
        return m.fit(X, y)

    @classmethod
    def _evaluate(cls, X, y, years) -> dict:
        """Leave-one-year-out: is the median close, and do 80% of truths fall in the range?"""
        abs_err, inside, n = [], 0, 0
        for yr in np.unique(years):
            test = years == yr
            if test.all() or test.sum() == 0:
                continue
            preds = {q: cls._fit(X[~test], y[~test], q).predict(X[test]) for q in QUANTILES}
            lo, mid, hi = (np.minimum.reduce([preds[q] for q in QUANTILES]), preds[0.5],
                           np.maximum.reduce([preds[q] for q in QUANTILES]))
            abs_err.extend(np.abs(mid - y[test]))
            inside += int(((y[test] >= lo) & (y[test] <= hi)).sum())
            n += int(test.sum())
        if not n:
            return {"note": "only one year of data; no out-of-year check"}
        return {"mae_t_ha": round(float(np.mean(abs_err)), 3),
                "range_coverage": round(inside / n, 3), "n_eval": n, "target_coverage": 0.8}

    def save(self, path: Path = MODEL_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"models": self.models, "feature_means": self.feature_means,
                     "metrics": self.metrics, "version": self.version}, path)

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "YieldModel | None":
        if not path.exists():
            return None
        b = joblib.load(path)
        return cls(b["models"], b["feature_means"], b["metrics"], b["version"])


_cache: dict = {}


def load_cached_model(path: Path = MODEL_PATH) -> "YieldModel | None":
    """YieldModel.load, reused until the file changes (keeps the what-if simulator under a second)."""
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if _cache.get("key") != (str(path), mtime):
        _cache.update(key=(str(path), mtime), model=YieldModel.load(path))
    return _cache["model"]


def baseline_yield(
    district_yields: list[float],
    integral: float | None,
    same_crop_integrals: list[float],
    in_progress: bool = False,
) -> YieldRange | None:
    """District yield history shifted by this season's greenness vs the field's own norm."""
    if not district_yields:
        return None
    base = median(district_yields)
    spread = max(pstdev(district_yields) / base if len(district_yields) > 1 and base else 0, MIN_REL_SPREAD)
    rel = 0.0
    if integral is not None and len(same_crop_integrals) >= 2:
        norm = float(np.mean(same_crop_integrals))
        if norm > 0:
            rel = float(np.clip((integral - norm) / norm, -0.5, 0.5))
    mid = base * (1 + GREENNESS_ELASTICITY * rel)
    half = 1.28 * spread * mid                     # ~10th-90th percentile for a normal spread
    low, mid, high = _ordered(mid - half, mid, mid + half)
    r = YieldRange(low, mid, high, "baseline", details={
        "district_median_t_ha": round(base, 2), "greenness_vs_usual": round(rel, 3),
        "district_years": len(district_yields)})
    return _widen(r) if in_progress else r
