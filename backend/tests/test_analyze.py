import json

import numpy as np

from app.ml.analyze import analyze_field
from app.ml.field_twins import find_twins
from tests.synth import field_frame

SQUARE = {"type": "Polygon", "coordinates": [[
    [80.7786, 16.4401], [80.7794, 16.4401], [80.7794, 16.4409], [80.7786, 16.4409], [80.7786, 16.4401]]]}


def add_field(conn, name, df, clay=40.0):
    fid = conn.execute(
        "INSERT INTO fields (name, boundary, district, state, clay_pct, sand_pct, ph_h2o, soc_g_per_kg, ingest_status)"
        " VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 'Krishna', 'Andhra Pradesh', %s, 30, 7.8, 6, 'done')"
        " RETURNING id::text", (name, json.dumps(SQUARE), clay)).fetchone()["id"]
    cols = ["ndvi", "ndvi_smoothed", "ndvi_source", "sar_vv", "sar_vh", "rainfall_mm", "temp_max_c", "et0_mm"]
    recs = []
    for day, r in df.iterrows():
        recs.append([fid, day.date()] + [None if (isinstance(r[c], float) and np.isnan(r[c])) else r[c] for c in cols])
    with conn.cursor() as cur:
        cur.executemany(
            f"INSERT INTO field_timeseries (field_id, date, {', '.join(cols)}) VALUES (%s, %s, {', '.join(['%s'] * len(cols))})",
            recs)
    conn.commit()
    return fid


def add_district_yields(conn):
    for year in range(2015, 2023):
        conn.execute("INSERT INTO district_yields (state, district, year, season, crop, area_ha, yield_t_ha, source)"
                     " VALUES ('Andhra Pradesh', 'Krishna', %s, 'kharif', 'paddy', 300000, %s, 'data_gov_in')",
                     (year, 5.0 + 0.1 * (year % 3)))
        conn.execute("INSERT INTO district_yields (state, district, year, season, crop, area_ha, yield_t_ha, source)"
                     " VALUES ('Andhra Pradesh', 'Krishna', %s, 'rabi', 'pulses', 150000, 0.9, 'data_gov_in')",
                     (year,))
    conn.commit()


def test_analyze_writes_seasons_events_and_yields(conn):
    add_district_yields(conn)
    df = field_frame()
    df.loc["2021-08-01":"2021-08-25", "rainfall_mm"] = 0.0     # dry spell in kharif 2021
    fid = add_field(conn, "a", df)

    summary = analyze_field(conn, fid)
    assert summary["seasons"] == 6 and summary["yield_method"] == "baseline"

    rows = conn.execute("SELECT * FROM seasons WHERE field_id = %s ORDER BY sowing_date", (fid,)).fetchall()
    kharif = [r for r in rows if r["season"] == "kharif"]
    assert all(r["crop"] == "paddy" and r["crop_status"] == "confident" for r in kharif)
    assert all(r["date_detection"] == "sar" for r in kharif)
    assert all(r["yield_low_t_ha"] < r["yield_mid_t_ha"] < r["yield_high_t_ha"] for r in kharif)
    assert all(r["features"]["season_days"] > 60 for r in rows)
    assert {r["crop"] for r in rows if r["season"] == "rabi"} == {"pulses"}

    dry = conn.execute("SELECT e.*, s.year FROM events e JOIN seasons s ON s.id = e.season_id"
                       " WHERE e.field_id = %s AND event_type = 'dry_spell'", (fid,)).fetchall()
    assert [d["year"] for d in dry] == [2021]
    k2021 = next(r for r in kharif if r["year"] == 2021)
    assert any("dry spell" in r["text"].lower() for r in k2021["shap_reasons"])

    # Re-running replaces, not duplicates; a farmer-confirmed crop is kept.
    conn.execute("UPDATE seasons SET crop = 'maize', crop_confirmed_by_farmer = true"
                 " WHERE field_id = %s AND year = 2022 AND season = 'kharif'", (fid,))
    conn.commit()
    analyze_field(conn, fid)
    again = conn.execute("SELECT year, season, crop FROM seasons WHERE field_id = %s", (fid,)).fetchall()
    assert len(again) == 6
    assert {(r["year"], r["crop"]) for r in again if r["season"] == "kharif"} >= {(2022, "maize")}
    n_dry = conn.execute("SELECT count(*) AS n FROM events WHERE field_id = %s AND event_type = 'dry_spell'",
                         (fid,)).fetchone()["n"]
    assert n_dry == 1


def test_field_twins(conn):
    add_district_yields(conn)
    me = add_field(conn, "me", field_frame(seed=1))
    near = add_field(conn, "near", field_frame(seed=2), clay=41.0)
    far = add_field(conn, "far", field_frame(seed=3, paddy_top=0.65), clay=15.0)
    for fid in (me, near, far):
        analyze_field(conn, fid)
    sid = conn.execute("SELECT id::text FROM seasons WHERE field_id = %s AND year = 2021 AND season = 'kharif'",
                       (me,)).fetchone()["id"]
    out = find_twins(conn, sid)
    assert out["crop"] == "paddy"
    fields = [t["field_id"] for t in out["twins"]]
    assert me not in fields
    assert fields[0] == near                       # most similar first
    assert all(isinstance(t["differences"], list) for t in out["twins"])


def test_train_then_analyze_uses_model_and_shap(conn, tmp_path, monkeypatch):
    from app.ml import analyze as analyze_mod
    from app.ml.yield_model import YieldModel
    from scripts.train_models import train_yield

    monkeypatch.setattr("scripts.train_models.YIELD_MODEL_PATH", tmp_path / "y.joblib")
    add_district_yields(conn)
    ids = [add_field(conn, f"f{i}", field_frame(seed=i, paddy_top=0.7 + 0.02 * i), clay=30 + 3 * i)
           for i in range(6)]
    for fid in ids:
        analyze_field(conn, fid)

    report = train_yield(conn)
    assert report["rows"] == 36 and set(report["crops"]) == {"paddy", "pulses"}
    assert "mae_t_ha" in report["metrics"]

    trained = YieldModel.load(tmp_path / "y.joblib")
    monkeypatch.setattr(analyze_mod, "YieldModel", type("Stub", (), {"load": staticmethod(lambda: trained)}))
    assert analyze_field(conn, ids[0])["yield_method"] == "model"
    row = conn.execute("SELECT yield_method, yield_low_t_ha, yield_high_t_ha, shap_reasons, yield_model_version"
                       " FROM seasons WHERE field_id = %s AND season = 'kharif' AND year = 2021", (ids[0],)).fetchone()
    assert row["yield_method"] == "model" and row["yield_model_version"].startswith("xgb-q-")
    assert row["yield_low_t_ha"] <= row["yield_high_t_ha"]
    assert all("likely" in r["text"] for r in row["shap_reasons"])
