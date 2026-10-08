"""Turn a field's time series into seasons, crops, stress events and yield ranges.

    analyze_field(conn, field_id)

Reads Layer 2 (field_timeseries) and writes Layer 3 (seasons, events). Safe to
re-run: detected seasons and events are replaced; anything the farmer
confirmed (crop, variety) is kept.
"""
import logging

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from app.ml.crop_classifier import CROPS, classify, load_trained
from app.ml.explain_shap import baseline_reasons, shap_reasons
from app.ml.features import season_features, twin_vector
from app.ml.season_detection import DetectedSeason, detect_seasons
from app.ml.stress_detection import detect_stress
from app.ml.yield_model import YieldModel, baseline_yield

log = logging.getLogger(__name__)

TS_COLS = ["ndvi", "ndvi_smoothed", "ndvi_source", "sar_vv", "sar_vh", "nisar_l_hh", "nisar_l_hv",
           "rainfall_mm", "temp_max_c", "et0_mm"]


def load_timeseries(conn, field_id: str) -> pd.DataFrame:
    rows = conn.execute(
        f"SELECT date, {', '.join(TS_COLS)} FROM field_timeseries WHERE field_id = %s ORDER BY date",
        (field_id,),
    ).fetchall()
    if not rows:
        return pd.DataFrame(columns=TS_COLS)
    df = pd.DataFrame(rows).set_index("date")
    df.index = pd.to_datetime(df.index)
    df = df.reindex(pd.date_range(df.index.min(), df.index.max(), freq="D"))
    for c in TS_COLS:
        if c != "ndvi_source":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def district_area_share(conn, state: str | None, district: str | None, season: str) -> dict[str, float]:
    if not district:
        return {}
    rows = conn.execute(
        """WITH d AS (
               SELECT crop, year, area_ha, season FROM district_yields
               WHERE lower(district) = lower(%s) AND (%s::text IS NULL OR lower(state) = lower(%s))
                 AND season IN (%s, 'total') AND area_ha > 0),
             pick AS (SELECT * FROM d WHERE season = %s
                      UNION ALL SELECT * FROM d WHERE NOT EXISTS (SELECT 1 FROM d WHERE season = %s))
           SELECT crop, avg(area_ha) AS area FROM pick
           WHERE year >= (SELECT max(year) - 4 FROM pick) GROUP BY crop""",
        (district, state, state, season, season, season),
    ).fetchall()
    areas = {r["crop"]: float(r["area"]) for r in rows if r["crop"] in CROPS}
    total = sum(areas.values())
    return {c: a / total for c, a in areas.items()} if total else {}


def district_yield_history(conn, state, district, crop, season) -> list[float]:
    """Recent district yields for the crop: this season, else whole-year totals, else any season."""
    if not district:
        return []
    rows = conn.execute(
        """SELECT yield_t_ha, season FROM district_yields
           WHERE lower(district) = lower(%s) AND (%s::text IS NULL OR lower(state) = lower(%s))
             AND crop = %s AND yield_t_ha > 0
           ORDER BY year DESC""",
        (district, state, state, crop),
    ).fetchall()
    for wanted in (season, "total"):
        picked = [float(r["yield_t_ha"]) for r in rows if r["season"] == wanted]
        if picked:
            return picked[:10]
    return [float(r["yield_t_ha"]) for r in rows][:10]


def analyze_field(conn: psycopg.Connection, field_id: str) -> dict:
    field = conn.execute(
        "SELECT id::text, district, state, clay_pct, sand_pct, ph_h2o, soc_g_per_kg FROM fields WHERE id = %s",
        (field_id,),
    ).fetchone()
    if field is None:
        raise ValueError(f"field {field_id} not found")
    df = load_timeseries(conn, field_id)
    detected = detect_seasons(df)
    confirmed = {
        (r["year"], r["season"]): r
        for r in conn.execute(
            "SELECT year, season, crop, variety FROM seasons WHERE field_id = %s AND crop_confirmed_by_farmer",
            (field_id,),
        ).fetchall()
    }
    trained_crop = load_trained()
    yield_model = YieldModel.load()

    # Pass 1: features, crop, stress events
    work = []
    for s in detected:
        feats = season_features(df, s, field)
        mine = confirmed.get((s.year, s.season))
        if mine:
            crop, conf, alts = mine["crop"], 1.0, []
        else:
            share = district_area_share(conn, field["state"], field["district"], s.season)
            crop, conf, alts = classify(feats, s.sowing_date.month, share, trained_crop)
        events = detect_stress(df, s, crop)
        work.append({"s": s, "feats": feats, "crop": crop, "conf": conf, "alts": alts, "events": events})

    # Pass 2: yields and likely reasons (needs the field's other seasons of the same crop)
    for w in work:
        s: DetectedSeason = w["s"]
        if yield_model is not None:
            yr = yield_model.predict(w["feats"], w["crop"], s.in_progress)
            reasons = shap_reasons(yield_model, w["feats"], w["crop"])
        else:
            others = [o["feats"]["ndvi_integral"] for o in work
                      if o["crop"] == w["crop"] and o is not w and o["feats"]["ndvi_integral"] is not None
                      and not o["s"].in_progress]
            history = district_yield_history(conn, field["state"], field["district"], w["crop"], s.season)
            yr = baseline_yield(history, w["feats"]["ndvi_integral"], others, s.in_progress)
            reasons = baseline_reasons(yr.details["greenness_vs_usual"] if yr else 0.0, w["events"])
        w["yield"], w["reasons"] = yr, reasons

    _write(conn, field_id, work)
    return {
        "field_id": field_id,
        "seasons": len(work),
        "uncertain_crops": sum(1 for w in work if w["conf"] < 0.6),
        "events": sum(len(w["events"]) for w in work),
        "yield_method": "model" if yield_model else ("baseline" if any(w["yield"] for w in work) else "none"),
    }


def _write(conn, field_id: str, work: list[dict]):
    keys = [(w["s"].year, w["s"].season) for w in work]
    with conn.transaction():
        conn.execute("DELETE FROM events WHERE field_id = %s AND origin = 'detected'", (field_id,))
        conn.execute(
            """DELETE FROM seasons WHERE field_id = %s AND NOT crop_confirmed_by_farmer
               AND NOT EXISTS (SELECT 1 FROM unnest(%s::smallint[], %s::text[]) AS k(year, season)
                               WHERE k.year = seasons.year AND k.season = seasons.season)""",
            (field_id, [k[0] for k in keys], [k[1] for k in keys]),
        )

        for w in work:
            s, yr = w["s"], w["yield"]
            row = {
                "field_id": field_id, "year": s.year, "season": s.season,
                "sowing_date": s.sowing_date, "peak_date": s.peak_date, "harvest_date": s.harvest_date,
                "peak_ndvi": s.peak_ndvi, "date_detection": s.date_detection,
                "date_confidence": s.obs_fraction, "in_progress": s.in_progress,
                "crop": w["crop"], "crop_confidence": w["conf"], "crop_alternatives": Jsonb(w["alts"]),
                "yield_low_t_ha": yr.low if yr else None, "yield_mid_t_ha": yr.mid if yr else None,
                "yield_high_t_ha": yr.high if yr else None, "yield_is_forecast": bool(yr and yr.is_forecast),
                "yield_method": yr.method if yr else None,
                "yield_model_version": (yr.details.get("model_version") or "baseline-v1") if yr else None,
                "shap_reasons": Jsonb(w["reasons"]), "features": Jsonb(w["feats"]),
                "feature_vector": str(twin_vector(w["feats"])),
            }
            cols = list(row)
            keep_farmer = {"crop", "crop_confidence", "crop_alternatives"}
            updates = ", ".join(
                f"{c} = CASE WHEN seasons.crop_confirmed_by_farmer THEN seasons.{c} ELSE EXCLUDED.{c} END"
                if c in keep_farmer else f"{c} = EXCLUDED.{c}"
                for c in cols[3:]
            )
            season_id = conn.execute(
                f"""INSERT INTO seasons ({', '.join(cols)}) VALUES ({', '.join(f'%({c})s' for c in cols)})
                    ON CONFLICT (field_id, year, season) DO UPDATE SET {updates}, updated_at = now()
                    RETURNING id""",
                row,
            ).fetchone()["id"]
            for e in w["events"]:
                conn.execute(
                    """INSERT INTO events (field_id, season_id, event_type, start_date, end_date, severity,
                                           origin, evidence)
                       VALUES (%s, %s, %s, %s, %s, %s, 'detected', %s)""",
                    (field_id, season_id, e["event_type"], e["start_date"], e["end_date"], e["severity"],
                     Jsonb(e["evidence"])),
                )
    conn.commit()   # transaction() only opens a savepoint when one is already running
