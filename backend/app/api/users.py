"""Users, F13 data-sharing consent, and F14 seed company insights (aggregates only)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import db, demo_user_id

router = APIRouter(prefix="/api", tags=["users"])


class UserIn(BaseModel):
    name: str | None = None
    phone: str | None = None
    preferred_language: Literal["te", "hi", "en"] = "te"


class Consent(BaseModel):
    data_sharing_consent: bool


def _user(conn, user_id: str) -> dict:
    row = conn.execute(
        "SELECT id::text, name, preferred_language, data_sharing_consent, consent_updated_at FROM users WHERE id::text = %s",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "user not found")
    return row


@router.get("/users/demo")
def demo_user(conn=Depends(db)):
    uid = demo_user_id(conn)
    conn.commit()
    return _user(conn, uid)


@router.post("/users", status_code=201)
def create_user(body: UserIn, conn=Depends(db)):
    uid = conn.execute("INSERT INTO users (name, phone, preferred_language) VALUES (%s, %s, %s) RETURNING id::text",
                       (body.name, body.phone, body.preferred_language)).fetchone()["id"]
    conn.commit()
    return _user(conn, uid)


@router.get("/users/{user_id}")
def get_user(user_id: str, conn=Depends(db)):
    return _user(conn, user_id)


@router.put("/users/{user_id}/consent")
def set_consent(user_id: str, body: Consent, conn=Depends(db)):
    _user(conn, user_id)
    conn.execute("UPDATE users SET data_sharing_consent = %s, consent_updated_at = now() WHERE id::text = %s",
                 (body.data_sharing_consent, user_id))
    conn.commit()
    return _user(conn, user_id)


@router.get("/insights")
def insights(state: str | None = None, district: str | None = None, crop: str | None = None, conn=Depends(db)):
    """Seed company view: consenting farmers only, district level, groups of 5+ fields, no ids or locations."""
    rows = conn.execute(
        """SELECT * FROM v_seed_insights
           WHERE (%(s)s::text IS NULL OR lower(state) = lower(%(s)s))
             AND (%(d)s::text IS NULL OR lower(district) = lower(%(d)s))
             AND (%(c)s::text IS NULL OR crop = %(c)s)
           ORDER BY year DESC, crop, variety""",
        {"s": state, "d": district, "c": crop},
    ).fetchall()
    totals = conn.execute(
        """SELECT count(*) FILTER (WHERE data_sharing_consent) AS sharing, count(*) AS users FROM users"""
    ).fetchone()
    return {"groups": rows, "farmers_sharing": totals["sharing"], "min_group_size": 5,
            "privacy": "Only farmers who turned sharing on are included. No names, ids or field locations."}
