"""Create clearly-labelled SYNTHETIC demo fields for offline development and UI testing.

    python -m scripts.seed_synthetic          # 6 fields, 2018-2025, plus synthetic district stats

Everything created here is flagged is_synthetic=true (UI badge, PDF banner),
uses the district name "Synthetic", and must never be shown as real results.
It never trains the yield model (train_models also ignores synthetic fields),
so yields here come from the baseline method.
Delete it with:  python -m scripts.seed_synthetic --delete
"""
import argparse
import json
from datetime import date

import numpy as np
from psycopg.types.json import Jsonb

from app.db.seeds import load_crop_varieties
from app.db.session import get_conn
from app.dev.synthetic import field_frame
from app.ml.analyze import analyze_field
from app.services.boundary import pin_square

DISTRICT, STATE = "Synthetic", "Andhra Pradesh"
YEARS = tuple(range(2018, 2026))
CENTRES = [(16.44, 80.78), (16.36, 80.83), (16.32, 80.95), (16.45, 80.96), (16.23, 80.90), (16.26, 81.13)]
TS_COLS = ["ndvi", "ndvi_smoothed", "ndvi_source", "sar_vv", "sar_vh", "rainfall_mm", "temp_max_c", "et0_mm"]


def _frame(i: int):
    rng = np.random.default_rng(100 + i)
    df = field_frame(years=YEARS, end=date(2026, 3, 31), paddy_top=0.72 + 0.03 * (i % 4), seed=i)
    for year in YEARS:
        if rng.random() < 0.35:   # some years get a monsoon break
            start = rng.integers(0, 20)
            df.loc[f"{year}-08-{1 + start:02d}":f"{year}-08-{min(31, 21 + start):02d}", "rainfall_mm"] = 0.0
    df["temp_min_c"] = df["temp_max_c"] - 9
    return df


def delete(conn):
    conn.execute("DELETE FROM fields WHERE is_synthetic")
    conn.execute("DELETE FROM district_yields WHERE source = 'synthetic'")
    conn.execute("DELETE FROM users WHERE phone LIKE 'synthetic-%'")
    conn.commit()


def seed(conn, n_fields: int = 6):
    delete(conn)
    load_crop_varieties(conn)
    for year in YEARS:
        conn.execute("""INSERT INTO district_yields (state, district, year, season, crop, area_ha, yield_t_ha, source)
                        VALUES (%s, %s, %s, 'kharif', 'paddy', 300000, %s, 'synthetic'),
                               (%s, %s, %s, 'rabi', 'pulses', 120000, %s, 'synthetic')""",
                     (STATE, DISTRICT, year, round(5.0 + 0.3 * np.sin(year), 2), STATE, DISTRICT, year,
                      round(0.85 + 0.1 * np.cos(year), 2)))
    ids = []
    for i in range(n_fields):
        owner = conn.execute("INSERT INTO users (name, phone, preferred_language, data_sharing_consent) "
                             "VALUES (%s, %s, 'te', true) RETURNING id::text",
                             (f"Synthetic farmer {i + 1}", f"synthetic-{i}")).fetchone()["id"]
        lat, lon = CENTRES[i % len(CENTRES)]
        fid = conn.execute(
            """INSERT INTO fields (owner_id, name, boundary, boundary_source, district, state, irrigation_type,
                                   soil_texture, clay_pct, sand_pct, silt_pct, ph_h2o, soc_g_per_kg,
                                   is_synthetic, ingest_status)
               VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 'pin_buffer', %s, %s, %s,
                       'clay', %s, 25, 30, 7.9, 6.5, true, 'done') RETURNING id::text""",
            (owner, f"[SYNTHETIC] Demo field {i + 1}", json.dumps(pin_square(lat, lon)), DISTRICT, STATE,
             "canal" if i % 2 == 0 else "borewell", 40 + 2 * i),
        ).fetchone()["id"]
        df = _frame(i)
        recs = []
        for day, r in df.iterrows():
            rec = [fid, day.date()]
            for c in TS_COLS + ["temp_min_c"]:
                v = r[c]
                rec.append(None if v is None or (isinstance(v, float) and np.isnan(v)) else v)
            sources = ["weather"] + (["s2"] if rec[2] is not None else []) + (["s1"] if rec[5] is not None else [])
            recs.append(rec + [sources])
        with conn.cursor() as cur:
            cur.executemany(
                f"""INSERT INTO field_timeseries (field_id, date, {', '.join(TS_COLS)}, temp_min_c, sources)
                    VALUES (%s, %s, {', '.join(['%s'] * (len(TS_COLS) + 1))}, %s)""", recs)
        conn.execute("""INSERT INTO diary_entries (field_id, entry_date, raw_text, text_en, language, activity_type, structured)
                        VALUES (%s, '2025-07-20', '2 బస్తాల యూరియా వేశాను', 'Applied 2 bags of urea', 'te', 'fertilizer', %s)""",
                     (fid, Jsonb({"activity_type": "fertilizer", "product": "urea", "quantity": 2, "unit": "bag",
                                  "quantity_kg": 90})))
        conn.commit()
        ids.append(fid)
    for fid in ids:
        analyze_field(conn, fid)
    return ids


def main():
    ap = argparse.ArgumentParser(description="Synthetic demo data (clearly labelled, never real)")
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--fields", type=int, default=6)
    args = ap.parse_args()
    with get_conn() as conn:
        if args.delete:
            delete(conn)
            print("synthetic data removed")
            return
        ids = seed(conn, args.fields)
        print(f"created {len(ids)} synthetic fields")


if __name__ == "__main__":
    main()
