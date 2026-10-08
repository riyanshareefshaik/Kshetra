from datetime import date, timedelta

import jwt
import pandas as pd
import pytest

from app.ml import advisory, irrigation
from app.services.forecast import parse_forecast

TODAY = date(2026, 10, 8)


def payload(rain=None, tmax=None, tmin=None, wind=None, rh=None):
    days = [TODAY + timedelta(days=i) for i in range(-7, 7)]
    n = len(days)
    hours = [f"{d.isoformat()}T{h:02d}:00" for d in days for h in range(24)]
    return {
        "daily": {
            "time": [d.isoformat() for d in days],
            "precipitation_sum": rain or [0.0] * n,
            "precipitation_probability_max": [10] * n,
            "temperature_2m_max": tmax or [32.0] * n,
            "temperature_2m_min": tmin or [24.0] * n,
            "wind_speed_10m_max": wind or [8.0] * n,
            "et0_fao_evapotranspiration": [5.0] * n,
        },
        "hourly": {"time": hours, "relative_humidity_2m": rh or [70] * len(hours),
                   "temperature_2m": [23.0 if int(t[11:13]) < 7 or int(t[11:13]) >= 20 else 31.0 for t in hours]},
    }


def test_parse_forecast_marks_past_and_future():
    days = parse_forecast(payload(), TODAY)
    assert len(days) == 14
    assert [d["is_forecast"] for d in days].count(True) == 7
    assert days[0]["night_temp"] == 23.0 and days[0]["humid_hours"] == 0


def test_heavy_rain_heat_and_spray_window():
    rain = [0.0] * 7 + [0.0, 80.0, 130.0, 0, 0, 0, 0]
    tmax = [32.0] * 7 + [41.0] + [32.0] * 6
    days = parse_forecast(payload(rain=rain, tmax=tmax), TODAY)
    alerts = advisory.weather_alerts(days)
    kinds = [(a["type"], a["level"]) for a in alerts]
    assert ("heavy_rain", "critical") in kinds and ("heavy_rain", "warning") in kinds
    assert ("heat", "warning") in kinds
    spray = next(a for a in alerts if a["type"] == "spray_window")
    assert spray["date"] == TODAY.isoformat()
    assert alerts[0]["level"] == "critical"


def test_harvest_window_and_dry_week():
    days = parse_forecast(payload(), TODAY)
    alerts = advisory.weather_alerts(days, {"crop": "paddy", "days_after_sowing": 130, "days_to_harvest": 10})
    types = {a["type"] for a in alerts}
    assert {"harvest_window", "dry_week"} <= types


def test_paddy_blast_risk_from_humid_mild_nights():
    rh = [95] * (14 * 24)
    days = parse_forecast(payload(rh=rh), TODAY)
    risks = {r["pest"]: r for r in advisory.pest_risks(days, "paddy")}
    assert risks["Blast"]["level"] == "high" and risks["Blast"]["favourable_days"] == 14
    assert advisory.pest_risks(days, "banana") == []


def weather(start, days, rain=0.0, et0=5.0):
    idx = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame({"rain_mm": rain, "et0_mm": et0}, index=idx)


def test_irrigation_now_when_root_zone_dry():
    sow = TODAY - timedelta(days=60)
    w = weather(sow, 68)
    out = irrigation.advise("maize", sow, 115, w, [], "loam", 0.5, TODAY)
    assert out["status"] == "irrigate_now" and out["amount_mm"] >= out["raw_mm"]
    assert out["litres_for_field"] == out["amount_mm"] * 5000
    assert out["stage"] == "flowering / grain filling"


def test_irrigation_diary_entry_resets_and_rain_counts():
    sow = TODAY - timedelta(days=60)
    w = weather(sow, 68)
    loam = irrigation.advise("maize", sow, 115, w, [TODAY - timedelta(days=1)], "loam", 0.5, TODAY)
    assert loam["status"] == "ok"                      # loam holds a week of water after irrigating
    sand = irrigation.advise("maize", sow, 115, w, [TODAY - timedelta(days=1)], "sand", 0.5, TODAY)
    assert sand["status"] == "irrigate_soon" and sand["next_date"] > TODAY.isoformat()
    wet = weather(sow, 68, rain=10.0, et0=4.0)
    assert irrigation.advise("maize", sow, 115, wet, [], "loam", None, TODAY)["status"] == "ok"


def test_irrigation_paddy_and_edge_cases():
    sow = TODAY - timedelta(days=80)
    out = irrigation.advise("paddy", sow, 148, weather(sow, 88), [], "clay", 1.0, TODAY)
    assert out["status"] == "paddy" and "flowering" in out["message"]
    assert irrigation.advise("maize", TODAY + timedelta(days=5), 115, weather(TODAY, 8), [], None, None, TODAY)[
        "status"] == "not_sown"
    assert irrigation.kc_on(irrigation.CROPS["maize"], 0, 100) == 0.30


def test_supabase_token_verification(monkeypatch):
    from app.api import auth
    from app.config import get_settings
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-test-secret-test-secret!")
    get_settings.cache_clear()
    good = jwt.encode({"sub": "abc", "aud": "authenticated", "email": "a@b.in"},
                      "test-secret-test-secret-test-secret!", algorithm="HS256")
    assert auth.verify_token(good)["sub"] == "abc"
    bad = jwt.encode({"sub": "abc", "aud": "authenticated"}, "wrong-secret-wrong-secret-wrong!!", algorithm="HS256")
    with pytest.raises(Exception, match="sign in"):
        auth.verify_token(bad)
    get_settings.cache_clear()
