"""Fertilizer calculator (feature 5) and soil tests, including Soil Health Card photos."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth import current_user
from app.api.deps import db, field_or_404
from app.ml.fertilizer import calculate
from app.services import ocr

router = APIRouter(prefix="/api", tags=["fertilizer"])
MAX_UPLOAD = 15 * 1024 * 1024


class SoilTestIn(BaseModel):
    test_date: date | None = None
    n_kg_ha: float | None = Field(None, ge=0, le=2000)
    p_kg_ha: float | None = Field(None, ge=0, le=500)
    k_kg_ha: float | None = Field(None, ge=0, le=3000)
    ph: float | None = Field(None, ge=0, le=14)
    oc_pct: float | None = Field(None, ge=0, le=20)
    ec_ds_m: float | None = Field(None, ge=0, le=50)
    zn_ppm: float | None = Field(None, ge=0, le=100)
    source: Literal["soil_health_card", "lab", "manual"] = "manual"


def _insert(conn, field_id: str, body: SoilTestIn, raw_text: str | None = None) -> dict:
    data = body.model_dump()
    data["test_date"] = data["test_date"] or date.today()  # noqa: DTZ011
    row = conn.execute(
        """INSERT INTO soil_tests (field_id, test_date, n_kg_ha, p_kg_ha, k_kg_ha, ph, oc_pct, ec_ds_m, zn_ppm,
                                   source, raw_text)
           VALUES (%(field_id)s, %(test_date)s, %(n_kg_ha)s, %(p_kg_ha)s, %(k_kg_ha)s, %(ph)s, %(oc_pct)s,
                   %(ec_ds_m)s, %(zn_ppm)s, %(source)s, %(raw_text)s) RETURNING *, id::text AS id""",
        {**data, "field_id": field_id, "raw_text": raw_text},
    ).fetchone()
    conn.commit()
    row["field_id"] = str(row["field_id"])
    return row


@router.get("/fields/{field_id}/soil-tests")
def list_tests(field_id: str, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    rows = conn.execute("SELECT *, id::text AS id, field_id::text AS field_id FROM soil_tests WHERE field_id = %s"
                        " ORDER BY test_date DESC", (field_id,)).fetchall()
    for r in rows:
        r.pop("raw_text", None)
    return rows


@router.post("/fields/{field_id}/soil-tests", status_code=201)
def add_test(field_id: str, body: SoilTestIn, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    return _insert(conn, field_id, body)


@router.post("/fields/{field_id}/soil-tests/card", status_code=201)
async def read_card(field_id: str, image: UploadFile = File(...), save: bool = Form(True),
                    conn=Depends(db), user=Depends(current_user)):
    """Read a Soil Health Card photo; returns the values found so the farmer can check them."""
    field_or_404(conn, field_id, user)
    data = await image.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "image too large")
    try:
        text = ocr.read_image(data)
    except Exception as exc:
        raise HTTPException(422, f"could not read the image: {exc}") from exc
    values = ocr.parse_soil_card(text)
    if not values:
        raise HTTPException(422, "No soil values found. Take a sharper photo of the results table, or type them in.")
    result = {"values": values}
    if save:
        result["saved"] = _insert(conn, field_id, SoilTestIn(**values, source="soil_health_card"), raw_text=text)
    return result


@router.get("/fields/{field_id}/fertilizer")
def fertilizer(field_id: str, crop: str, season: Literal["kharif", "rabi", "zaid"],
               variety: str | None = None, conn=Depends(db), user=Depends(current_user)):
    f = field_or_404(conn, field_id, user)
    v = conn.execute(
        """SELECT recommended_n_kg_ha, recommended_p2o5_kg_ha, recommended_k2o_kg_ha, variety FROM crop_varieties
           WHERE crop = %s AND season = %s AND (%s::text IS NULL OR variety = %s) ORDER BY variety LIMIT 1""",
        (crop, season, variety, variety),
    ).fetchone()
    if v is None or v["recommended_n_kg_ha"] is None:
        raise HTTPException(404, f"No fertilizer recommendation for {crop} in {season} yet.")
    soil = conn.execute("SELECT * FROM soil_tests WHERE field_id = %s ORDER BY test_date DESC LIMIT 1",
                        (field_id,)).fetchone()
    rdf = (v["recommended_n_kg_ha"] or 0, v["recommended_p2o5_kg_ha"] or 0, v["recommended_k2o_kg_ha"] or 0)
    out = calculate(crop, rdf, soil, f["area_ha"] or 1.0)
    out["variety"] = v["variety"]
    out["soil_test_date"] = soil["test_date"] if soil else None
    return out
