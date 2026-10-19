"""Weather alerts (feature 2) and pest/disease risk (feature 4) from the 7+7 day forecast.

Thresholds: IMD rainfall categories (heavy >= 64.5 mm/day, very heavy >= 115.6), common
spraying guidance (no rain for ~24 h, wind under 15 km/h), and weather conditions that agromet
advisories link with major pests and diseases of crops grown in Andhra Pradesh. These are
risk signals from weather only, never a diagnosis: the farmer should look at the crop first.
"""
from datetime import date

HEAVY_RAIN, VERY_HEAVY_RAIN = 64.5, 115.6
SPRAY_MAX_WIND, SPRAY_MAX_RAIN_PROB = 15, 30
HEAT, SEVERE_HEAT, COLD, STRONG_WIND = 40, 45, 10, 40


def _ok(v):
    return v is not None


def weather_alerts(days: list[dict], crop: dict | None = None) -> list[dict]:
    """crop: {'crop', 'days_after_sowing', 'days_to_harvest'} for the season in the field, if any."""
    future = [d for d in days if d["is_forecast"]]
    alerts = []

    for d in future:
        rain = d["rain_mm"] or 0
        if rain >= HEAVY_RAIN:
            alerts.append({"type": "heavy_rain", "level": "critical" if rain >= VERY_HEAVY_RAIN else "warning",
                           "date": d["date"], "value": rain,
                           "message": f"{'Very heavy' if rain >= VERY_HEAVY_RAIN else 'Heavy'} rain expected ({rain:.0f} mm). "
                                      "Open field drains; do not apply fertilizer or spray before it."})
        if _ok(d["tmax"]) and d["tmax"] >= HEAT:
            alerts.append({"type": "heat", "level": "critical" if d["tmax"] >= SEVERE_HEAT else "warning",
                           "date": d["date"], "value": d["tmax"],
                           "message": f"Very hot day ({d['tmax']:.0f} °C). Irrigate in the evening or early morning; "
                                      "avoid spraying in the afternoon."})
        if _ok(d["tmin"]) and d["tmin"] <= COLD:
            alerts.append({"type": "cold", "level": "warning", "date": d["date"], "value": d["tmin"],
                           "message": f"Cold night ({d['tmin']:.0f} °C). Light irrigation in the evening protects young crops."})
        if _ok(d["wind_kmh"]) and d["wind_kmh"] >= STRONG_WIND:
            alerts.append({"type": "wind", "level": "warning", "date": d["date"], "value": d["wind_kmh"],
                           "message": f"Strong wind ({d['wind_kmh']:.0f} km/h). Tall crops may lodge; avoid spraying."})

    spray = next((d for d in future if (d["rain_mm"] or 0) < 1 and (d["rain_prob"] or 0) <= SPRAY_MAX_RAIN_PROB
                  and (d["wind_kmh"] or 0) < SPRAY_MAX_WIND), None)
    alerts.append({"type": "spray_window", "level": "info", "date": spray["date"] if spray else None,
                   "message": (f"Good day to spray: {spray['date']} (dry, low wind)." if spray
                               else "No good spraying day in the next 7 days: rain or wind expected.")})

    week_rain = sum(d["rain_mm"] or 0 for d in future)
    if crop and week_rain < 5:
        alerts.append({"type": "dry_week", "level": "info", "date": future[0]["date"] if future else None,
                       "value": round(week_rain, 1),
                       "message": "Little or no rain in the next 7 days. Check the irrigation advice."})

    if crop and crop.get("days_to_harvest") is not None and crop["days_to_harvest"] <= 20:
        run = []
        best = None
        for d in future:
            run = run + [d] if (d["rain_mm"] or 0) < 2 else []
            if len(run) >= 3:
                best = run[:3]
                break
        alerts.append({"type": "harvest_window", "level": "info" if best else "warning",
                       "date": best[0]["date"] if best else None,
                       "message": (f"Good harvest window: {best[0]['date']} to {best[-1]['date']} (3 dry days)." if best
                                   else "Harvest is near but rain is expected on most days; keep harvested crop covered.")})
    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(alerts, key=lambda a: (order[a["level"]], a["date"] or ""))


# ------------------------------------------------------------------ pest / disease risk

def _count(days, cond):
    return sum(1 for d in days if cond(d))


def _tmean(d):
    return (d["tmax"] + d["tmin"]) / 2 if _ok(d["tmax"]) and _ok(d["tmin"]) else None


RULES = {
    "paddy": [
        ("Blast", "Leaf/neck blast spreads in long humid nights at 20–26 °C.",
         lambda d: _ok(d["night_temp"]) and 20 <= d["night_temp"] <= 26 and d["humid_hours"] >= 8),
        ("Brown planthopper", "Warm (25–30 °C), humid, cloudy weather favours planthopper build-up at the base of plants.",
         lambda d: _ok(_tmean(d)) and 25 <= _tmean(d) <= 30 and (d["rh_mean"] or 0) >= 80),
        ("Sheath blight", "Hot (28–32 °C) and very humid weather with a dense canopy favours sheath blight.",
         lambda d: _ok(d["tmax"]) and 28 <= d["tmax"] <= 34 and d["humid_hours"] >= 12),
    ],
    "cotton": [
        ("Whitefly", "Hot, dry weather (above 35 °C, low humidity) favours whitefly.",
         lambda d: _ok(d["tmax"]) and d["tmax"] >= 35 and (d["rh_mean"] or 100) < 60),
        ("Boll rot", "Continuous rain at boll stage causes boll rot.", lambda d: (d["rain_mm"] or 0) >= 10),
    ],
    "chilli": [
        ("Thrips and mites", "Dry, warm weather without rain favours thrips and mites.",
         lambda d: (d["rain_mm"] or 0) < 1 and _ok(d["tmax"]) and d["tmax"] >= 30),
        ("Fruit rot / anthracnose", "Rainy days at 24–30 °C spread fruit rot.",
         lambda d: (d["rain_mm"] or 0) >= 2.5 and _ok(_tmean(d)) and 24 <= _tmean(d) <= 30),
    ],
    "maize": [
        ("Fall armyworm", "Warm (25–30 °C), dry spells favour fall armyworm in young maize.",
         lambda d: _ok(_tmean(d)) and 25 <= _tmean(d) <= 30 and (d["rain_mm"] or 0) < 2.5),
        ("Turcicum leaf blight", "Mild (18–27 °C) and humid weather favours leaf blight.",
         lambda d: _ok(_tmean(d)) and 18 <= _tmean(d) <= 27 and d["humid_hours"] >= 8),
    ],
    "pulses": [
        ("Yellow mosaic (whitefly-borne)", "Warm, dry weather increases whitefly that spreads yellow mosaic.",
         lambda d: _ok(d["tmax"]) and d["tmax"] >= 32 and (d["rain_mm"] or 0) < 1),
        ("Powdery mildew", "Cool nights (15–22 °C) with dew and dry days favour powdery mildew.",
         lambda d: _ok(d["night_temp"]) and 15 <= d["night_temp"] <= 22 and d["humid_hours"] >= 6
         and (d["rain_mm"] or 0) < 1),
    ],
    "sugarcane": [
        ("Early shoot borer", "Hot, dry weather in young cane favours early shoot borer.",
         lambda d: _ok(d["tmax"]) and d["tmax"] >= 35 and (d["rain_mm"] or 0) < 1),
    ],
}


def pest_risks(days: list[dict], crop: str | None) -> list[dict]:
    if crop not in RULES:
        return []
    out = []
    for name, why, cond in RULES[crop]:
        n = _count(days, cond)
        level = "high" if n >= 5 else "medium" if n >= 3 else "low"
        out.append({"pest": name, "level": level, "favourable_days": n, "of_days": len(days), "why": why})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda r: order[r["level"]])


def crop_context(season: dict | None, duration_days: int | None, today: date) -> dict | None:
    if not season:
        return None
    das = (today - season["sowing_date"]).days
    dth = (duration_days - das) if duration_days else None
    return {"crop": season["crop"], "days_after_sowing": das, "days_to_harvest": dth}
