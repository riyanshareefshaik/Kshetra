"""F2-F7: seasons, events, likely reasons and field twins."""
from fastapi import APIRouter, Depends
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.api.deps import db, field_or_404, season_or_404
from app.ml.crop_classifier import CROPS
from app.ml.field_twins import find_twins

router = APIRouter(prefix="/api", tags=["seasons"])


class SeasonPatch(BaseModel):
    crop: str | None = None
    variety: str | None = None


@router.get("/fields/{field_id}/seasons")
def list_seasons(field_id: str, conn=Depends(db)):
    field_or_404(conn, field_id)
    return conn.execute(
        """SELECT id::text, year, season, crop, crop_confidence, crop_status, crop_alternatives,
                  crop_confirmed_by_farmer, variety, sowing_date, peak_date, harvest_date, peak_ndvi,
                  date_detection, date_confidence, in_progress, yield_low_t_ha, yield_mid_t_ha, yield_high_t_ha,
                  yield_is_forecast, yield_method,
                  (SELECT count(*) FROM events e WHERE e.season_id = s.id) AS events
           FROM seasons s WHERE field_id = %s ORDER BY sowing_date""",
        (field_id,),
    ).fetchall()


@router.get("/fields/{field_id}/events")
def list_events(field_id: str, conn=Depends(db)):
    field_or_404(conn, field_id)
    return conn.execute(
        """SELECT id::text, season_id::text, event_type, start_date, end_date, severity, origin, evidence
           FROM events WHERE field_id = %s ORDER BY start_date""",
        (field_id,),
    ).fetchall()


@router.get("/seasons/{season_id}")
def get_season(season_id: str, conn=Depends(db)):
    return season_or_404(conn, season_id)


@router.patch("/seasons/{season_id}")
def confirm_season(season_id: str, body: SeasonPatch, conn=Depends(db)):
    """The farmer confirms or corrects the crop/variety. Confirmed crops are never overwritten."""
    season_or_404(conn, season_id)
    if body.crop is not None:
        if body.crop not in CROPS:
            from fastapi import HTTPException
            raise HTTPException(422, f"crop must be one of {CROPS}")
        conn.execute("""UPDATE seasons SET crop = %s, crop_confidence = 1.0, crop_confirmed_by_farmer = true,
                        crop_alternatives = %s, updated_at = now() WHERE id = %s""",
                     (body.crop, Jsonb([]), season_id))
    if body.variety is not None:
        conn.execute("UPDATE seasons SET variety = %s, updated_at = now() WHERE id = %s", (body.variety, season_id))
    conn.commit()
    return season_or_404(conn, season_id)


@router.get("/seasons/{season_id}/why")
def why(season_id: str, conn=Depends(db)):
    s = season_or_404(conn, season_id)
    events = conn.execute(
        "SELECT event_type, start_date, end_date, severity, evidence FROM events WHERE season_id = %s ORDER BY start_date",
        (season_id,),
    ).fetchall()
    return {
        "season_id": season_id, "year": s["year"], "season": s["season"], "crop": s["crop"],
        "crop_status": s["crop_status"],
        "yield_t_ha": {"low": s["yield_low_t_ha"], "mid": s["yield_mid_t_ha"], "high": s["yield_high_t_ha"]},
        "is_forecast": s["yield_is_forecast"], "method": s["yield_method"],
        "likely_reasons": s["shap_reasons"], "events": events,
        "note": "Likely reasons are associations found in the data, not proven causes.",
    }


@router.get("/seasons/{season_id}/twins")
def twins(season_id: str, conn=Depends(db)):
    season_or_404(conn, season_id)
    out = find_twins(conn, season_id)
    for t in out["twins"]:
        t.pop("field_id", None)      # other farmers stay anonymous
    return out
