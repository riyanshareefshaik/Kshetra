"""Shared FastAPI dependencies."""
from collections.abc import Iterator

import psycopg
from fastapi import HTTPException

from app.db.session import get_conn

DEMO_PHONE = "demo-farmer"


def db() -> Iterator[psycopg.Connection]:
    with get_conn() as conn:
        yield conn


def field_or_404(conn, field_id: str) -> dict:
    try:
        row = conn.execute(
            """SELECT id::text, owner_id::text, name, village, district, state, area_ha, boundary_source,
                      irrigation_type, soil_texture, clay_pct, sand_pct, silt_pct, soc_g_per_kg, ph_h2o,
                      nitrogen_g_per_kg, ingest_status, ingest_error, created_at,
                      ST_AsGeoJSON(boundary)::json AS boundary, ST_Y(location) AS lat, ST_X(location) AS lon
               FROM fields WHERE id = %s""",
            (field_id,),
        ).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        conn.rollback()
        row = None
    if row is None:
        raise HTTPException(404, "field not found")
    row["area_ha"] = float(row["area_ha"]) if row["area_ha"] is not None else None
    return row


def season_or_404(conn, season_id: str) -> dict:
    try:
        row = conn.execute(
            """SELECT s.*, s.id::text AS id, s.field_id::text AS field_id FROM seasons s WHERE s.id = %s""",
            (season_id,),
        ).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        conn.rollback()
        row = None
    if row is None:
        raise HTTPException(404, "season not found")
    row.pop("feature_vector", None)
    return row


def demo_user_id(conn) -> str:
    """Kshetra has no login yet (hackathon); fields without an owner belong to the demo farmer."""
    return conn.execute(
        "INSERT INTO users (name, phone, preferred_language) VALUES ('Demo farmer', %s, 'te')"
        " ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone RETURNING id::text",
        (DEMO_PHONE,),
    ).fetchone()["id"]
