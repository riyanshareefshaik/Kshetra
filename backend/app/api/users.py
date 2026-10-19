"""Users, F13 data-sharing consent, and F14 seed company insights (aggregates only)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import current_user
from app.api.deps import db

router = APIRouter(prefix="/api", tags=["users"])


class UserIn(BaseModel):
    name: str | None = None
    preferred_language: Literal["te", "hi", "en"] | None = None


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


@router.get("/users/me")
def me(conn=Depends(db), user=Depends(current_user)):
    out = _user(conn, user["id"])
    return {**out, "email": user["email"], "auth_mode": user["mode"]}


@router.patch("/users/me")
def update_me(body: UserIn, conn=Depends(db), user=Depends(current_user)):
    data = body.model_dump(exclude_unset=True)
    if data:
        sets = ", ".join(f"{k} = %({k})s" for k in data)
        conn.execute(f"UPDATE users SET {sets} WHERE id::text = %(id)s", {**data, "id": user["id"]})
        conn.commit()
    return me(conn, user)


@router.put("/users/me/consent")
def set_consent(body: Consent, conn=Depends(db), user=Depends(current_user)):
    conn.execute("UPDATE users SET data_sharing_consent = %s, consent_updated_at = now() WHERE id::text = %s",
                 (body.data_sharing_consent, user["id"]))
    conn.commit()
    return _user(conn, user["id"])


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
