from datetime import date

import pytest

from app.services.earth_engine import parse_s1, parse_s2


def test_s2_merges_tiles_and_drops_cloudy_dates():
    raw = [
        {"date": "2024-01-05", "ndvi": 0.60, "clear": 1.0},
        {"date": "2024-01-05", "ndvi": 0.70, "clear": 0.5},   # overlapping tile, same day
        {"date": "2024-01-10", "ndvi": 0.20, "clear": 0.3},   # mostly cloudy -> no NDVI
        {"date": "2024-01-15", "ndvi": None, "clear": 0.0},
    ]
    rows = parse_s2(raw)
    assert [r["date"] for r in rows] == [date(2024, 1, 5), date(2024, 1, 10), date(2024, 1, 15)]
    assert rows[0]["ndvi"] == pytest.approx((0.6 * 1 + 0.7 * 0.5) / 1.5, abs=1e-4)
    assert rows[0]["cloud_pct"] == 0.0
    assert rows[1]["ndvi"] is None and rows[1]["cloud_pct"] == 70.0
    assert rows[2]["ndvi"] is None and rows[2]["cloud_pct"] == 100.0


def test_s1_keeps_dominant_orbit_and_converts_to_db():
    raw = [
        {"date": "2024-07-01", "vv_lin": 0.1, "vh_lin": 0.01, "pass": "DESCENDING"},
        {"date": "2024-07-13", "vv_lin": 0.1, "vh_lin": 0.02, "pass": "DESCENDING"},
        {"date": "2024-07-05", "vv_lin": 0.5, "vh_lin": 0.05, "pass": "ASCENDING"},
        {"date": "2024-07-20", "vv_lin": None, "vh_lin": None, "pass": "DESCENDING"},
    ]
    rows = parse_s1(raw)
    assert [r["date"] for r in rows] == [date(2024, 7, 1), date(2024, 7, 13)]
    assert rows[0]["sar_vv"] == -10.0
    assert rows[0]["sar_vh"] == -20.0


def test_s1_empty():
    assert parse_s1([]) == []
