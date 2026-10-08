"""Train the yield model (and, when farmers have confirmed enough seasons, the crop model).

    python -m scripts.train_models            # after fields are built + load_reference
    python -m scripts.analyze_all             # then refresh every field with the new models

Yield labels: district yield for the season's crop, district and year
(district_yields). Each field-season gets its district's label, so the model
learns how timing, weather and crop vigour shift yields; ranges stay wide for
what it cannot see. Metrics are leave-one-year-out and saved with the model.
"""
import json
from datetime import UTC, datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import cross_val_score

from app.db.session import get_conn
from app.ml.crop_classifier import MODEL_PATH as CROP_MODEL_PATH
from app.ml.features import FEATURES
from app.ml.yield_model import MODEL_PATH as YIELD_MODEL_PATH
from app.ml.yield_model import YieldModel

MIN_CONFIRMED = 20


def yield_training_frame(conn) -> pd.DataFrame:
    rows = conn.execute(
        """SELECT s.features, s.crop, s.year, s.season,
                  coalesce(
                    (SELECT avg(d.yield_t_ha) FROM district_yields d
                      WHERE lower(d.district) = lower(f.district) AND lower(d.state) = lower(f.state)
                        AND d.crop = s.crop AND d.year = s.year AND d.season = s.season AND d.yield_t_ha > 0),
                    (SELECT avg(d.yield_t_ha) FROM district_yields d
                      WHERE lower(d.district) = lower(f.district) AND lower(d.state) = lower(f.state)
                        AND d.crop = s.crop AND d.year = s.year AND d.season = 'total' AND d.yield_t_ha > 0)
                  ) AS target
           FROM seasons s JOIN fields f ON f.id = s.field_id
           WHERE NOT s.in_progress AND s.crop IS NOT NULL
             AND (s.crop_confidence >= 0.6 OR s.crop_confirmed_by_farmer)"""
    ).fetchall()
    data = [{**{k: r["features"].get(k) for k in FEATURES}, "crop": r["crop"], "year": r["year"],
             "target": r["target"]} for r in rows if r["target"] is not None]
    return pd.DataFrame(data, columns=FEATURES + ["crop", "year", "target"])


def train_yield(conn) -> dict:
    df = yield_training_frame(conn)
    model = YieldModel.train(df, version=f"xgb-q-{datetime.now(UTC).date().isoformat()}")
    model.save(YIELD_MODEL_PATH)
    return {"rows": len(df), "crops": df["crop"].value_counts().to_dict(), "metrics": model.metrics}


def train_crop(conn) -> dict:
    rows = conn.execute(
        "SELECT features, crop FROM seasons WHERE crop_confirmed_by_farmer AND crop IS NOT NULL"
    ).fetchall()
    counts = pd.Series([r["crop"] for r in rows]).value_counts()
    if len(rows) < MIN_CONFIRMED or len(counts) < 2 or counts.min() < 2:
        return {"skipped": f"need {MIN_CONFIRMED}+ farmer-confirmed seasons, 2+ of each of 2+ crops; have {len(rows)}"}
    X = np.array([[r["features"].get(f, np.nan) if r["features"].get(f) is not None else np.nan
                   for f in FEATURES] for r in rows], dtype=float)
    y = np.array([r["crop"] for r in rows])
    clf = HistGradientBoostingClassifier(max_depth=3, random_state=0)
    acc = float(np.mean(cross_val_score(clf, X, y, cv=min(5, int(counts.min())))))
    clf.fit(X, y)
    CROP_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": clf, "features": FEATURES}, CROP_MODEL_PATH)
    return {"rows": len(rows), "cv_accuracy": round(acc, 3)}


def main():
    with get_conn() as conn:
        report = {}
        try:
            report["yield"] = train_yield(conn)
        except ValueError as exc:
            report["yield"] = {"skipped": str(exc)}
        report["crop"] = train_crop(conn)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
