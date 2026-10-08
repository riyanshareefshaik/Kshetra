import json
from datetime import date, timedelta

import numpy as np

from app.services.ingest import Fetchers, ingest_field

FIELD = {"type": "Polygon", "coordinates": [[
    [80.7786, 16.4401], [80.7794, 16.4401], [80.7794, 16.4409], [80.7786, 16.4409], [80.7786, 16.4401]]]}


class Calls:
    def __init__(self):
        self.n = {}

    def hit(self, name):
        self.n[name] = self.n.get(name, 0) + 1


def fake_fetchers(calls: Calls) -> Fetchers:
    def open_meteo(http, lat, lon, start, end):
        calls.hit("open_meteo")
        days = [start + timedelta(d) for d in range((end - start).days + 1)]
        return {"daily": {
            "time": [d.isoformat() for d in days],
            "precipitation_sum": [5.0] * len(days),
            "temperature_2m_max": [33.0] * len(days),
            "temperature_2m_min": [24.0] * len(days),
            "temperature_2m_mean": [28.0] * len(days),
            "et0_fao_evapotranspiration": [4.0] * len(days),
        }}

    def s2(geom, start, end):
        calls.hit("s2")
        out = []
        d = start
        while d <= end:
            doy = d.timetuple().tm_yday
            ndvi = 0.2 + 0.6 * np.exp(-((doy - 240) / 35.0) ** 2)
            cloudy = 7 <= d.month <= 9 and d.day % 10 != 0
            out.append({"date": d.isoformat(), "ndvi": None if cloudy else float(ndvi),
                        "clear": 0.1 if cloudy else 1.0})
            d += timedelta(days=5)
        return out

    def s1(geom, start, end):
        calls.hit("s1")
        out = []
        d = start + timedelta(days=2)
        while d <= end:
            doy = d.timetuple().tm_yday
            ndvi = 0.2 + 0.6 * np.exp(-((doy - 240) / 35.0) ** 2)
            out.append({"date": d.isoformat(), "vv_lin": 10 ** ((-14 + 6 * ndvi) / 10),
                        "vh_lin": 10 ** ((-24 + 14 * ndvi) / 10), "pass": "DESCENDING"})
            d += timedelta(days=6)
        return out

    def soilgrids(http, lat, lon):
        calls.hit("soilgrids")
        return {"properties": {"layers": [
            {"name": n, "depths": [{"label": lbl, "values": {"mean": v}} for lbl in ("0-5cm", "5-15cm", "15-30cm")]}
            for n, v in (("clay", 450), ("sand", 250), ("silt", 300), ("phh2o", 78))]}}

    def fail(*a, **k):
        raise AssertionError("should not be called")

    return Fetchers(soilgrids=soilgrids, open_meteo=open_meteo, nasa_power=fail, s2=s2, s1=s1,
                    nisar_search=fail, nisar_resolve=fail, nisar_read_url=fail, nisar_read_file=fail)


def add_field(conn):
    return conn.execute(
        "INSERT INTO fields (name, boundary) VALUES ('t', ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) RETURNING id::text",
        (json.dumps(FIELD),)).fetchone()["id"]


def test_ingest_builds_timeseries_and_caches(conn, monkeypatch):
    monkeypatch.setattr("app.services.ingest.get_settings", lambda: type("S", (), {"earthdata_token": ""})())
    fid = add_field(conn)
    conn.commit()
    calls = Calls()
    rep = ingest_field(conn, fid, start=date(2020, 1, 1), end=date(2022, 12, 31), fetchers=fake_fetchers(calls))

    assert rep.rows == 3 * 365 + 1
    assert rep.counts["ndvi_obs"] > 150 and rep.counts["sentinel1"] > 150
    assert rep.counts["ndvi_filled"] > 10
    assert any("EARTHDATA_TOKEN" in e for e in rep.errors)       # NISAR skipped without a key

    f = conn.execute("SELECT ingest_status, soil_texture, clay_pct, area_ha FROM fields WHERE id = %s", (fid,)).fetchone()
    assert f["ingest_status"] == "done"
    assert f["soil_texture"] == "clay" and f["clay_pct"] == 45.0
    assert float(f["area_ha"]) > 0.5

    row = conn.execute(
        "SELECT ndvi_source, sources FROM field_timeseries WHERE field_id = %s AND ndvi_source = 'sar_fill' LIMIT 1",
        (fid,)).fetchone()
    assert row["sources"][-1] == "sar_fill" and "s1" in row["sources"]
    smoothed = conn.execute(
        "SELECT count(*) AS n FROM field_timeseries WHERE field_id = %s AND ndvi_smoothed IS NOT NULL", (fid,)
    ).fetchone()["n"]
    assert smoothed > 1000

    # Second run is served entirely from api_cache.
    before = dict(calls.n)
    rep2 = ingest_field(conn, fid, start=date(2020, 1, 1), end=date(2022, 12, 31), fetchers=fake_fetchers(calls))
    assert calls.n == before
    assert rep2.rows == rep.rows


def test_ingest_survives_failing_sources(conn, monkeypatch):
    monkeypatch.setattr("app.services.ingest.get_settings", lambda: type("S", (), {"earthdata_token": ""})())
    fid = add_field(conn)
    conn.commit()
    calls = Calls()
    f = fake_fetchers(calls)

    def boom(*a, **k):
        raise RuntimeError("GEE_PROJECT is not set")

    f.s2 = f.s1 = boom
    rep = ingest_field(conn, fid, start=date(2022, 1, 1), end=date(2022, 12, 31), fetchers=f)
    status = conn.execute("SELECT ingest_status, ingest_error FROM fields WHERE id = %s", (fid,)).fetchone()
    assert rep.rows == 365                      # weather still stored
    assert status["ingest_status"] == "failed"  # but no NDVI -> not usable yet
    assert "GEE_PROJECT" in status["ingest_error"]
