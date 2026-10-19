"""Daily weather per field: Open-Meteo archive (primary) and NASA POWER (fallback).

Both are free and keyless. Open-Meteo is for non-commercial use; NASA POWER is public.
Returns a list of {date, rainfall_mm, temp_max_c, temp_min_c, temp_mean_c, et0_mm, soil_moisture}.
"""
from collections import defaultdict
from datetime import date

import httpx

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_MISSING = -999.0

DAILY_VARS = [
    "precipitation_sum",
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "et0_fao_evapotranspiration",
]


def fetch_open_meteo(client: httpx.Client, lat: float, lon: float, start: date, end: date) -> dict:
    resp = client.get(
        OPEN_METEO_URL,
        params={
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(DAILY_VARS),
            # Soil moisture is only published hourly; averaged to daily below.
            "hourly": "soil_moisture_0_to_7cm",
            "timezone": "Asia/Kolkata",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def parse_open_meteo(payload: dict) -> list[dict]:
    daily = payload["daily"]
    soil: dict[str, list[float]] = defaultdict(list)
    hourly = payload.get("hourly") or {}
    for ts, value in zip(hourly.get("time", []), hourly.get("soil_moisture_0_to_7cm", [])):
        if value is not None:
            soil[ts[:10]].append(value)

    rows = []
    for i, day in enumerate(daily["time"]):
        values = soil.get(day)
        rows.append(
            {
                "date": date.fromisoformat(day),
                "rainfall_mm": daily["precipitation_sum"][i],
                "temp_max_c": daily["temperature_2m_max"][i],
                "temp_min_c": daily["temperature_2m_min"][i],
                "temp_mean_c": daily["temperature_2m_mean"][i],
                "et0_mm": daily["et0_fao_evapotranspiration"][i],
                "soil_moisture": round(sum(values) / len(values), 4) if values else None,
            }
        )
    return rows


def fetch_nasa_power(client: httpx.Client, lat: float, lon: float, start: date, end: date) -> dict:
    resp = client.get(
        NASA_POWER_URL,
        params={
            "parameters": "PRECTOTCORR,T2M_MAX,T2M_MIN,T2M",
            "community": "AG",
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()


def parse_nasa_power(payload: dict) -> list[dict]:
    p = payload["properties"]["parameter"]

    def val(name: str, key: str):
        v = p.get(name, {}).get(key)
        return None if v is None or v == POWER_MISSING else v

    rows = []
    for key in sorted(p["PRECTOTCORR"]):
        rows.append(
            {
                "date": date(int(key[:4]), int(key[4:6]), int(key[6:])),
                "rainfall_mm": val("PRECTOTCORR", key),
                "temp_max_c": val("T2M_MAX", key),
                "temp_min_c": val("T2M_MIN", key),
                "temp_mean_c": val("T2M", key),
                "et0_mm": None,
                "soil_moisture": None,
            }
        )
    return rows
