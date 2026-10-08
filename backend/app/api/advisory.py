"""Today: weather alerts (2), irrigation advice (3) and pest/disease risk (4) for a field."""
from datetime import date, timedelta

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_user
from app.api.deps import db, field_or_404
from app.ml import advisory, irrigation
from app.services import forecast

router = APIRouter(prefix="/api", tags=["advisory"])


def current_season(conn, field_id: str, crop: str | None = None, sowing: date | None = None) -> dict | None:
    """The crop in the field: explicit crop+sowing date, else the season detected as in progress."""
    if crop and sowing:
        return {"crop": crop, "sowing_date": sowing, "variety": None, "season": None}
    return conn.execute(
        """SELECT crop, sowing_date, variety, season FROM seasons
           WHERE field_id = %s AND in_progress AND crop IS NOT NULL ORDER BY sowing_date DESC LIMIT 1""",
        (field_id,),
    ).fetchone()


def duration_for(conn, season: dict | None) -> int | None:
    if not season:
        return None
    row = conn.execute(
        """SELECT round(avg(duration_days)) AS d FROM crop_varieties
           WHERE crop = %s AND (%s::text IS NULL OR season = %s)""",
        (season["crop"], season.get("season"), season.get("season")),
    ).fetchone()
    return int(row["d"]) if row and row["d"] else None


def _forecast_or_503(conn, f: dict, today: date) -> list[dict]:
    try:
        return forecast.field_forecast(conn, f["lat"], f["lon"], today)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Weather forecast is unavailable right now. Try again later.") from exc


@router.get("/fields/{field_id}/today")
def today_advice(field_id: str, crop: str | None = None, sowing_date: date | None = None,
                 conn=Depends(db), user=Depends(current_user)):
    f = field_or_404(conn, field_id, user)
    today = date.today()  # noqa: DTZ011 - local calendar day
    days = _forecast_or_503(conn, f, today)
    season = current_season(conn, field_id, crop, sowing_date)
    duration = duration_for(conn, season)
    ctx = advisory.crop_context(season, duration, today)
    return {
        "field_id": field_id,
        "crop": ctx,
        "days": days,
        "alerts": advisory.weather_alerts(days, ctx),
        "pests": advisory.pest_risks(days, season["crop"] if season else None),
        "irrigation": _irrigation(conn, f, season, duration, days, today),
        "note": "Pest risk is from weather only. Check your crop before spraying and ask your agriculture officer.",
    }


def _irrigation(conn, f, season, duration, days, today):
    if not season or not duration:
        return {"status": "no_crop", "message": "Tell Kshetra what is growing (crop and sowing date) to get irrigation advice."}
    start = season["sowing_date"]
    observed = conn.execute(
        "SELECT date, rainfall_mm AS rain_mm, et0_mm FROM field_timeseries WHERE field_id = %s AND date >= %s",
        (f["id"], start),
    ).fetchall()
    df = pd.DataFrame(observed or [], columns=["date", "rain_mm", "et0_mm"])
    fc = pd.DataFrame([{"date": date.fromisoformat(d["date"]), "rain_mm": d["rain_mm"], "et0_mm": d["et0_mm"]}
                       for d in days])
    df = pd.concat([df.dropna(subset=["et0_mm"]), fc]).drop_duplicates("date", keep="last")
    df["date"] = pd.to_datetime(df["date"])
    idx = pd.date_range(min(pd.Timestamp(start), df["date"].min()) if len(df) else pd.Timestamp(start),
                        pd.Timestamp(today + timedelta(days=7)), freq="D")
    weather = df.set_index("date").reindex(idx)
    weather["et0_mm"] = weather["et0_mm"].fillna(weather["et0_mm"].mean() if weather["et0_mm"].notna().any() else 4.0)
    weather["rain_mm"] = weather["rain_mm"].fillna(0)
    irrigations = [r["entry_date"] for r in conn.execute(
        "SELECT entry_date FROM diary_entries WHERE field_id = %s AND activity_type = 'irrigation' AND entry_date >= %s",
        (f["id"], start)).fetchall()]
    soil = conn.execute("SELECT soil_texture FROM fields WHERE id = %s", (f["id"],)).fetchone()["soil_texture"]
    return irrigation.advise(season["crop"], start, duration, weather, irrigations, soil, f["area_ha"], today)
