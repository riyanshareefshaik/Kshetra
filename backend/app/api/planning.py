"""F8 what-if simulator and F9 next-season planner."""
import time
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import current_user
from app.api.deps import db, field_or_404
from app.ml.simulator import FieldContext, Scenario, next_season, plan, simulate

router = APIRouter(prefix="/api", tags=["planning"])
Season = Literal["kharif", "rabi", "zaid"]


class WhatIf(BaseModel):
    crop: str
    season: Season
    variety: str | None = None
    sowing_date: str = Field(..., pattern=r"^\d{2}-\d{2}$", description="MM-DD")
    n_kg_ha: float = Field(..., ge=0, le=400)
    irrigation: Literal["rainfed", "supplemental", "full"] = "rainfed"
    price_rs_per_qtl: float | None = Field(None, gt=0)
    seed_cost_rs_ha: float | None = Field(None, ge=0)
    other_cost_rs_ha: float | None = Field(None, ge=0)


@router.get("/crop-varieties")
def crop_varieties(season: Season | None = None, conn=Depends(db)):
    return conn.execute(
        "SELECT * FROM crop_varieties WHERE %s::text IS NULL OR season = %s ORDER BY crop, variety",
        (season, season),
    ).fetchall()


@router.post("/fields/{field_id}/what-if")
def what_if(field_id: str, body: WhatIf, conn=Depends(db), user=Depends(current_user)):
    t0 = time.perf_counter()
    field_or_404(conn, field_id, user)
    v = conn.execute(
        """SELECT * FROM crop_varieties WHERE crop = %s AND season = %s AND (%s::text IS NULL OR variety = %s)
           ORDER BY variety LIMIT 1""",
        (body.crop, body.season, body.variety, body.variety),
    ).fetchone()
    if v is None:
        raise HTTPException(404, f"no variety data for {body.crop} in {body.season}")
    month, day = (int(x) for x in body.sowing_date.split("-"))
    try:
        date(2001, month, day)
    except ValueError as exc:
        raise HTTPException(422, "sowing_date is not a real date") from exc
    rec = float(v["recommended_n_kg_ha"] or 0)
    sc = Scenario(crop=body.crop, variety=v["variety"], season=body.season, sowing_month_day=(month, day),
                  duration_days=int(v["duration_days"]), n_kg_ha=body.n_kg_ha, recommended_n_kg_ha=rec,
                  irrigation=body.irrigation, water_need=v["water_need"] or "medium",
                  seed_cost_rs_ha=body.seed_cost_rs_ha if body.seed_cost_rs_ha is not None else float(v["seed_cost_rs_per_ha"] or 0),
                  other_cost_rs_ha=body.other_cost_rs_ha if body.other_cost_rs_ha is not None else float(v["other_cost_rs_per_ha"] or 0),
                  price_rs_per_qtl=body.price_rs_per_qtl)
    try:
        res = simulate(FieldContext(conn, field_id), sc)
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    if "error" in res:
        raise HTTPException(409, res["error"])
    res["recommended_n_kg_ha"] = rec
    res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
    return res


@router.get("/fields/{field_id}/plan")
def next_season_plan(field_id: str, season: Season | None = None, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    target, year = (season, None) if season else next_season(date.today())  # noqa: DTZ011
    options = plan(FieldContext(conn, field_id), target)
    return {"season": target, "year": year, "options": options,
            "note": "Ranked by profit with a penalty for bad years. Costs are estimates; prices from Agmarknet or MSP."}
