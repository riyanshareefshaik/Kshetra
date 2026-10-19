"""Which crop was grown in a season, with a confidence score (F3).

There is no free, field-level crop map for India, so the classifier combines:
  1. Phenology rules: duration, sowing month, peak greenness and the radar
     flooding signal of each crop, from published crop calendars for coastal
     Andhra Pradesh (approximate ranges).
  2. A district prior: the crop's share of sown area in that district and
     season (ICRISAT / data.gov.in), when loaded.
  3. A trained model, once farmers have confirmed enough seasons
     (scripts/train_models.py), blended 50/50 with the rules.

Confidence < 0.60 is shown as "uncertain" (schema: seasons.crop_status).
Black gram and green gram look identical from space, so they are reported
together as "pulses"; the farmer's diary can say which.
"""
import math
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "crop_classifier.joblib"


@dataclass(frozen=True)
class CropProfile:
    days: tuple[float, float]          # typical sowing-to-harvest range
    sow_months: tuple[int, ...]
    peak_ndvi: tuple[float, float]
    flooded: bool                      # transplanted into standing water


PROFILES = {
    "paddy": CropProfile((100, 150), (6, 7, 8, 9, 12, 1), (0.60, 0.88), True),
    "maize": CropProfile((90, 125), (6, 7, 10, 11, 12, 1), (0.65, 0.90), False),
    "cotton": CropProfile((150, 210), (5, 6, 7), (0.50, 0.80), False),
    "pulses": CropProfile((60, 95), (10, 11, 12, 1, 2), (0.40, 0.68), False),
    "chilli": CropProfile((150, 220), (7, 8, 9, 10), (0.45, 0.75), False),
    "sugarcane": CropProfile((270, 400), (1, 2, 3, 12), (0.65, 0.90), False),
}
CROPS = list(PROFILES)


def _range_score(x: float | None, lo: float, hi: float, soft: float) -> float:
    """1 inside [lo, hi], Gaussian fall-off outside with width `soft`."""
    if x is None:
        return 1.0
    if lo <= x <= hi:
        return 1.0
    d = lo - x if x < lo else x - hi
    return math.exp(-0.5 * (d / soft) ** 2)


def _month_score(month: int, months: tuple[int, ...]) -> float:
    dist = min(min(abs(month - m), 12 - abs(month - m)) for m in months)
    return {0: 1.0, 1: 0.5}.get(dist, 0.08)


def rule_probabilities(feats: dict, sowing_month: int) -> dict[str, float]:
    flood = (feats.get("flood_signal_db") or 0.0) >= 3.0
    scores = {}
    for crop, p in PROFILES.items():
        score = (
            _range_score(feats.get("season_days"), *p.days, soft=15)
            * _month_score(sowing_month, p.sow_months)
            * _range_score(feats.get("peak_ndvi"), *p.peak_ndvi, soft=0.07)
        )
        # Flooding is strong evidence for paddy; its absence is weaker evidence
        # (radar can miss it), so the penalty is asymmetric.
        if p.flooded:
            score *= 3.0 if flood else 0.6
        elif flood:
            score *= 0.25
        scores[crop] = score
    return _normalize(scores)


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        return {c: 1 / len(scores) for c in scores}
    return {c: v / total for c, v in scores.items()}


def apply_prior(probs: dict[str, float], area_share: dict[str, float] | None) -> dict[str, float]:
    """Mix in the district's crop area shares; half-weighted so a rare crop can still win."""
    if not area_share:
        return probs
    uniform = 1 / len(probs)
    return _normalize({c: p * (0.5 * uniform + 0.5 * area_share.get(c, 0.0)) for c, p in probs.items()})


class TrainedCropModel:
    """Optional sklearn model trained on farmer-confirmed seasons."""

    def __init__(self, path: Path = MODEL_PATH):
        bundle = joblib.load(path)
        self.model, self.features = bundle["model"], bundle["features"]

    def predict(self, feats: dict) -> dict[str, float]:
        x = np.array([[feats.get(f) if feats.get(f) is not None else np.nan for f in self.features]])
        probs = self.model.predict_proba(x)[0]
        return {c: float(p) for c, p in zip(self.model.classes_, probs)}


def load_trained() -> "TrainedCropModel | None":
    return TrainedCropModel() if MODEL_PATH.exists() else None


def classify(
    feats: dict,
    sowing_month: int,
    area_share: dict[str, float] | None = None,
    trained: TrainedCropModel | None = None,
) -> tuple[str, float, list[dict]]:
    """Returns (crop, confidence 0-1, alternatives [{crop, p}] best first)."""
    probs = rule_probabilities(feats, sowing_month)
    if trained is not None:
        learned = trained.predict(feats)
        probs = _normalize({c: 0.5 * probs[c] + 0.5 * learned.get(c, 0.0) for c in probs})
    probs = apply_prior(probs, area_share)
    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    crop, conf = ranked[0]
    alternatives = [{"crop": c, "p": round(p, 3)} for c, p in ranked[1:4]]
    return crop, round(conf, 3), alternatives
