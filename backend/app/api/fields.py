"""F1 field selection, ingestion status, and Layer 1/2 reads."""
import json
import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from shapely.geometry import shape

from app.api.auth import current_user
from app.api.deps import db, field_or_404
from app.db.session import get_conn
from app.ml.analyze import analyze_field
from app.services.boundary import auto_boundary, pin_square
from app.services.cache import cached
from app.services.ingest import ingest_field

router = APIRouter(prefix="/api", tags=["fields"])
log = logging.getLogger(__name__)

Irrigation = Literal["rainfed", "canal", "borewell", "tank", "drip", "sprinkler", "unknown"]


class FieldIn(BaseModel):
    name: str | None = None
    boundary: dict | None = Field(None, description="GeoJSON Polygon (WGS84). Omit and send lat/lon for a pin.")
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    boundary_source: Literal["drawn", "auto_ndvi", "auto_sam", "pin_buffer"] | None = None
    village: str | None = None
    district: str | None = None
    state: str | None = None
    irrigation_type: Irrigation | None = None
    start_ingest: bool = True


class FieldPatch(BaseModel):
    name: str | None = None
    boundary: dict | None = None
    village: str | None = None
    district: str | None = None
    state: str | None = None
    irrigation_type: Irrigation | None = None


class Pin(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


def _valid_polygon(geom: dict) -> dict:
    try:
        poly = shape(geom)
    except Exception as exc:
        raise HTTPException(422, f"invalid GeoJSON: {exc}") from exc
    if poly.geom_type != "Polygon" or not poly.is_valid or poly.is_empty:
        raise HTTPException(422, "boundary must be a valid, non-self-intersecting Polygon")
    if poly.area > 0.01:   # ~100 km2 at Indian latitudes
        raise HTTPException(422, "boundary is far too large for one field")
    return geom


def run_refresh(field_id: str, start: date | None = None):
    """Background job: ingest every source, then rebuild seasons. Uses its own connection."""
    with get_conn() as conn:
        rep = ingest_field(conn, field_id, start=start)
        if rep.rows:
            try:
                analyze_field(conn, field_id)
            except Exception as exc:  # noqa: BLE001 - keep the error on the field, not in the logs only
                conn.rollback()
                conn.execute("UPDATE fields SET ingest_error = coalesce(ingest_error || '; ', '') || %s WHERE id = %s",
                             (f"analysis: {exc}"[:300], field_id))
                conn.commit()
        log.info("refresh %s: %s rows, %s", field_id, rep.rows, rep.counts)


@router.post("/fields/auto-boundary")
def propose_boundary(pin: Pin, conn=Depends(db), user=Depends(current_user)):
    """Suggest a boundary for a pin (cached; falls back to a square around the pin)."""
    return cached(conn, "gee_boundary", {"lat": round(pin.lat, 5), "lon": round(pin.lon, 5)},
                  lambda: auto_boundary(pin.lat, pin.lon))


@router.post("/fields", status_code=201)
def create_field(body: FieldIn, tasks: BackgroundTasks, conn=Depends(db), user=Depends(current_user)):
    if body.boundary:
        geom, source = _valid_polygon(body.boundary), body.boundary_source or "drawn"
    elif body.lat is not None and body.lon is not None:
        geom, source = pin_square(body.lat, body.lon), "pin_buffer"
    else:
        raise HTTPException(422, "send a boundary polygon or a lat/lon pin")
    owner = user["id"]
    fid = conn.execute(
        """INSERT INTO fields (owner_id, name, boundary, boundary_source, village, district, state, irrigation_type)
           VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s, %s, %s) RETURNING id::text""",
        (owner, body.name, json.dumps(geom), source, body.village, body.district, body.state, body.irrigation_type),
    ).fetchone()["id"]
    conn.commit()
    if body.start_ingest:
        tasks.add_task(run_refresh, fid)
    return field_or_404(conn, fid, user)


@router.get("/fields")
def list_fields(conn=Depends(db), user=Depends(current_user)):
    # Local mode shows every field on this installation; with login, only your own.
    owner_id = user["id"] if user["mode"] == "supabase" else None
    rows = conn.execute(
        """SELECT f.id::text, f.name, f.district, f.state, f.area_ha, f.ingest_status,
                  ST_Y(f.location) AS lat, ST_X(f.location) AS lon, ST_AsGeoJSON(f.boundary)::json AS boundary,
                  (SELECT count(*) FROM seasons s WHERE s.field_id = f.id) AS seasons
           FROM fields f WHERE (%s::uuid IS NULL OR f.owner_id = %s::uuid) ORDER BY f.created_at""",
        (owner_id, owner_id),
    ).fetchall()
    for r in rows:
        r["area_ha"] = float(r["area_ha"]) if r["area_ha"] is not None else None
    return rows


@router.get("/fields/{field_id}")
def get_field(field_id: str, conn=Depends(db), user=Depends(current_user)):
    return field_or_404(conn, field_id, user)


@router.patch("/fields/{field_id}")
def update_field(field_id: str, body: FieldPatch, tasks: BackgroundTasks, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    data = body.model_dump(exclude_unset=True)
    boundary = data.pop("boundary", None)
    if data:
        sets = ", ".join(f"{k} = %({k})s" for k in data)
        conn.execute(f"UPDATE fields SET {sets}, updated_at = now() WHERE id = %(id)s", {**data, "id": field_id})
    if boundary:
        conn.execute("UPDATE fields SET boundary = ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), boundary_source = 'drawn'"
                     " WHERE id = %s", (json.dumps(_valid_polygon(boundary)), field_id))
        tasks.add_task(run_refresh, field_id)      # new boundary -> new satellite averages
    conn.commit()
    return field_or_404(conn, field_id, user)


@router.delete("/fields/{field_id}", status_code=204)
def delete_field(field_id: str, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    conn.execute("DELETE FROM fields WHERE id = %s", (field_id,))
    conn.commit()


@router.post("/fields/{field_id}/refresh", status_code=202)
def refresh_field(field_id: str, tasks: BackgroundTasks, start: date | None = None, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    conn.execute("UPDATE fields SET ingest_status = 'pending' WHERE id = %s", (field_id,))
    conn.commit()
    tasks.add_task(run_refresh, field_id, start)
    return {"field_id": field_id, "status": "pending"}


@router.get("/fields/{field_id}/timeseries")
def timeseries(field_id: str, start: date | None = None, end: date | None = None,
               step: int = Query(5, ge=1, le=31, description="return every Nth day, plus every satellite date"),
               conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    rows = conn.execute(
        """WITH t AS (
             SELECT date, ndvi, ndvi_smoothed, ndvi_source, cloud_pct, sar_vv, sar_vh, nisar_l_hh, nisar_l_hv,
                    nisar_s_hh, nisar_s_hv, rainfall_mm, temp_max_c, temp_min_c, soil_moisture,
                    sum(rainfall_mm) OVER (ORDER BY date ROWS BETWEEN %(back)s PRECEDING AND CURRENT ROW) AS rain_step_mm
             FROM field_timeseries
             WHERE field_id = %(fid)s AND (%(start)s::date IS NULL OR date >= %(start)s - %(step)s)
               AND (%(end)s::date IS NULL OR date <= %(end)s))
           SELECT *, (date - DATE '2000-01-01') %% %(step)s = 0 AS is_step FROM t
           WHERE (%(start)s::date IS NULL OR date >= %(start)s)
             AND ((date - DATE '2000-01-01') %% %(step)s = 0 OR ndvi IS NOT NULL OR sar_vv IS NOT NULL
                  OR nisar_l_hh IS NOT NULL OR nisar_s_hh IS NOT NULL)
           ORDER BY date""",
        {"fid": field_id, "start": start, "end": end, "step": step, "back": step - 1},
    ).fetchall()
    return rows
