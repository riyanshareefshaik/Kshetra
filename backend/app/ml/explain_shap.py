"""Likely reasons behind a season's yield (F6).

With a trained model: SHAP values of the median (P50) model say how much each
feature pushed this season's yield above or below the model's average. The
biggest pushes become reasons, always worded as "likely", never as causes:
the model finds associations in the data, not proof.

With the baseline: reasons come from greenness versus the field's usual and
from detected stress events, without t/ha numbers.
"""
from functools import lru_cache

import shap

from app.ml.features import FEATURE_INFO, FEATURES
from app.ml.yield_model import YieldModel

MIN_EFFECT_T_HA = 0.05
TOP_N = 4

EVENT_TEXT = {
    "dry_spell": "a dry spell of {dry_days} days{flowering}",
    "waterlogging": "waterlogging after heavy rain ({max_rain_3day_mm} mm in 3 days)",
    "flood": "flooding seen by radar after {max_rain_3day_mm} mm of rain in 3 days",
    "sudden_damage": "a sudden drop in crop greenness ({ndvi_before} to {ndvi_after} in {days} days)",
    "heat_stress": "{hot_days} very hot days (up to {tmax_max_c} C) around flowering",
}


@lru_cache(maxsize=4)
def _explainer(model):
    return shap.TreeExplainer(model)


def _fmt(v: float | None) -> str:
    if v is None:
        return "unknown"
    return f"{v:.0f}" if abs(v) >= 10 else f"{v:.2f}"


def shap_reasons(model: YieldModel, feats: dict, crop: str) -> list[dict]:
    p50 = model.models[0.5]
    X = model.matrix([feats], [crop])
    values = _explainer(p50).shap_values(X)[0]
    reasons = []
    for name, effect in zip(model.columns, values):
        if name not in FEATURES or abs(effect) < MIN_EFFECT_T_HA or feats.get(name) is None:
            continue
        label, unit = FEATURE_INFO[name]
        value, typical = feats.get(name), model.feature_means.get(name)
        direction = "raised" if effect > 0 else "lowered"
        compare = f" vs a typical {_fmt(typical)}" if typical is not None else ""
        reasons.append({
            "feature": name,
            "value": value,
            "typical": round(typical, 3) if typical is not None else None,
            "shap_t_ha": round(float(effect), 3),
            "direction": "up" if effect > 0 else "down",
            "text": f"{label.capitalize()} was {_fmt(value)} {unit}{compare}; "
                    f"this likely {direction} yield by about {abs(effect):.1f} t/ha.".replace("  ", " "),
        })
    reasons.sort(key=lambda r: abs(r["shap_t_ha"]), reverse=True)
    return reasons[:TOP_N]


def baseline_reasons(greenness_vs_usual: float, events: list[dict]) -> list[dict]:
    reasons = []
    if abs(greenness_vs_usual) >= 0.05:
        more = greenness_vs_usual > 0
        reasons.append({
            "feature": "ndvi_integral",
            "value": round(greenness_vs_usual, 3),
            "direction": "up" if more else "down",
            "text": f"The crop stayed {'greener' if more else 'less green'} than usual for this field "
                    f"({abs(greenness_vs_usual) * 100:.0f}% {'more' if more else 'less'} total greenness); "
                    f"this likely {'raised' if more else 'lowered'} yield.",
        })
    for e in sorted(events, key=lambda e: e.get("severity") or 0, reverse=True):
        template = EVENT_TEXT.get(e["event_type"])
        if not template:
            continue
        ev = dict(e.get("evidence") or {})
        ev["flowering"] = " during flowering" if ev.get("during_flowering") else ""
        try:
            what = template.format(**ev)
        except (KeyError, ValueError):
            what = e["event_type"].replace("_", " ")
        reasons.append({
            "feature": e["event_type"],
            "value": e.get("severity"),
            "direction": "down",
            "text": f"{what[0].upper()}{what[1:]} likely lowered yield.",
        })
    return reasons[:TOP_N]

