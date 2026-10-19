"""Shared FastAPI dependencies."""
from collections.abc import Iterator

import psycopg
from fastapi import HTTPException

from app.config import get_settings
from app.db.session import get_conn

LOCAL_PHONE = "demo-farmer"     # the single farmer in local (no-login) mode


def db() -> Iterator[psycopg.Connection]:
    with get_conn() as conn:
        yield conn


def _owner_ok(row_owner: str | None, user: dict | None) -> bool:
    """In local mode everything is visible; with login, only the owner's fields."""
    if user is None or user.get("mode") != "supabase" or get_settings().auth_mode != "supabase":
        return True
    return row_owner == user["id"]


def field_or_404(conn, field_id: str, user: dict | None = None) -> dict:
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
    if row is None or not _owner_ok(row["owner_id"], user):
        raise HTTPException(404, "field not found")
    row["area_ha"] = float(row["area_ha"]) if row["area_ha"] is not None else None
    return row


def season_or_404(conn, season_id: str, user: dict | None = None) -> dict:
    try:
        row = conn.execute(
            """SELECT s.*, s.id::text AS id, s.field_id::text AS field_id, f.owner_id::text AS owner_id
               FROM seasons s JOIN fields f ON f.id = s.field_id WHERE s.id = %s""",
            (season_id,),
        ).fetchone()
    except psycopg.errors.InvalidTextRepresentation:
        conn.rollback()
        row = None
    if row is None or not _owner_ok(row.pop("owner_id"), user):
        raise HTTPException(404, "season not found")
    row.pop("feature_vector", None)
    return row


def local_user_id(conn) -> str:
    """The single farmer used when login is off (AUTH_MODE=none)."""
    return conn.execute(
        "INSERT INTO users (name, phone, preferred_language) VALUES ('Farmer', %s, 'te')"
        " ON CONFLICT (phone) DO UPDATE SET phone = EXCLUDED.phone RETURNING id::text",
        (LOCAL_PHONE,),
    ).fetchone()["id"]
