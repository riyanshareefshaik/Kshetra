"""7-day weather forecast plus the last 7 days, per field (Open-Meteo forecast API: free, no key).

One call returns daily values and hourly humidity/temperature for 7 past + 7 coming days,
which feeds weather alerts, pest-risk rules and the irrigation advisor. Cached for 3 hours.
"""
from datetime import date, timedelta

import httpx

from app.services.cache import cached

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY = ["precipitation_sum", "precipitation_probability_max", "temperature_2m_max", "temperature_2m_min",
         "wind_speed_10m_max", "et0_fao_evapotranspiration"]
HOURLY = ["relative_humidity_2m", "temperature_2m"]
HUMID_RH = 90


def fetch_forecast(lat: float, lon: float) -> dict:
    with httpx.Client() as client:
        r = client.get(FORECAST_URL, timeout=30, params={
            "latitude": round(lat, 4), "longitude": round(lon, 4), "daily": ",".join(DAILY),
            "hourly": ",".join(HOURLY), "past_days": 7, "forecast_days": 7, "timezone": "Asia/Kolkata",
            "wind_speed_unit": "kmh",
        })
        r.raise_for_status()
        return r.json()


def parse_forecast(payload: dict, today: date) -> list[dict]:
    d = payload["daily"]
    hourly = payload.get("hourly") or {}
    by_day: dict[str, dict] = {}
    for ts, rh, temp in zip(hourly.get("time", []), hourly.get("relative_humidity_2m", []),
                            hourly.get("temperature_2m", [])):
        day = by_day.setdefault(ts[:10], {"rh": [], "humid_hours": 0, "night_temps": []})
        if rh is not None:
            day["rh"].append(rh)
            day["humid_hours"] += rh >= HUMID_RH
        hour = int(ts[11:13])
        if temp is not None and (hour >= 20 or hour <= 6):
            day["night_temps"].append(temp)
    days = []
    for i, ds in enumerate(d["time"]):
        h = by_day.get(ds, {"rh": [], "humid_hours": 0, "night_temps": []})
        day = date.fromisoformat(ds)
        days.append({
            "date": ds,
            "is_forecast": day >= today,
            "rain_mm": d["precipitation_sum"][i],
            "rain_prob": d.get("precipitation_probability_max", [None] * len(d["time"]))[i],
            "tmax": d["temperature_2m_max"][i],
            "tmin": d["temperature_2m_min"][i],
            "wind_kmh": d["wind_speed_10m_max"][i],
            "et0_mm": d["et0_fao_evapotranspiration"][i],
            "rh_mean": round(sum(h["rh"]) / len(h["rh"]), 1) if h["rh"] else None,
            "humid_hours": h["humid_hours"],
            "night_temp": round(sum(h["night_temps"]) / len(h["night_temps"]), 1) if h["night_temps"] else None,
        })
    return days


def field_forecast(conn, lat: float, lon: float, today: date | None = None, fetch=None) -> list[dict]:
    today = today or date.today()  # noqa: DTZ011 - local calendar day
    params = {"lat": round(lat, 3), "lon": round(lon, 3), "day": today.isoformat(), "v": 1}
    payload = cached(conn, "open_meteo_forecast", params, lambda: (fetch or fetch_forecast)(lat, lon), ttl=timedelta(hours=3))
    return parse_forecast(payload, today)
