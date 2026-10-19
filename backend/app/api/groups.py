"""Farmer groups / FPO dashboard (feature 9).

A group admin creates a group and shares its join code. Members choose whether their fields are
visible to the group (on by default when joining, can be turned off at any time). The dashboard
only shows fields of members who share; others are just counted.
"""
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import current_user
from app.api.deps import db

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    district: str | None = None
    state: str | None = None


class JoinIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=12)


class ShareIn(BaseModel):
    share_with_group: bool


def _code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def _membership(conn, group_id: str, user_id: str) -> dict:
    row = conn.execute("SELECT role, share_with_group FROM group_members WHERE group_id::text = %s AND user_id::text = %s",
                       (group_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "group not found")
    return row


@router.get("")
def my_groups(conn=Depends(db), user=Depends(current_user)):
    return conn.execute(
        """SELECT g.id::text, g.name, g.district, g.state, m.role, m.share_with_group,
                  CASE WHEN m.role = 'admin' THEN g.join_code END AS join_code,
                  (SELECT count(*) FROM group_members x WHERE x.group_id = g.id) AS members
           FROM farmer_groups g JOIN group_members m ON m.group_id = g.id
           WHERE m.user_id::text = %s ORDER BY g.created_at""",
        (user["id"],),
    ).fetchall()


@router.post("", status_code=201)
def create_group(body: GroupIn, conn=Depends(db), user=Depends(current_user)):
    gid = conn.execute(
        "INSERT INTO farmer_groups (name, district, state, join_code, created_by) VALUES (%s, %s, %s, %s, %s) RETURNING id::text",
        (body.name, body.district, body.state, _code(), user["id"]),
    ).fetchone()["id"]
    conn.execute("INSERT INTO group_members (group_id, user_id, role) VALUES (%s, %s, 'admin')", (gid, user["id"]))
    conn.commit()
    return next(g for g in my_groups(conn, user) if g["id"] == gid)


@router.post("/join")
def join(body: JoinIn, conn=Depends(db), user=Depends(current_user)):
    g = conn.execute("SELECT id::text FROM farmer_groups WHERE join_code = %s", (body.code.strip().upper(),)).fetchone()
    if g is None:
        raise HTTPException(404, "No group with that code.")
    conn.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                 (g["id"], user["id"]))
    conn.commit()
    return next(x for x in my_groups(conn, user) if x["id"] == g["id"])


@router.put("/{group_id}/share")
def set_share(group_id: str, body: ShareIn, conn=Depends(db), user=Depends(current_user)):
    _membership(conn, group_id, user["id"])
    conn.execute("UPDATE group_members SET share_with_group = %s WHERE group_id::text = %s AND user_id::text = %s",
                 (body.share_with_group, group_id, user["id"]))
    conn.commit()
    return {"group_id": group_id, "share_with_group": body.share_with_group}


@router.delete("/{group_id}/members/me", status_code=204)
def leave(group_id: str, conn=Depends(db), user=Depends(current_user)):
    _membership(conn, group_id, user["id"])
    conn.execute("DELETE FROM group_members WHERE group_id::text = %s AND user_id::text = %s", (group_id, user["id"]))
    conn.commit()


@router.get("/{group_id}/dashboard")
def dashboard(group_id: str, conn=Depends(db), user=Depends(current_user)):
    _membership(conn, group_id, user["id"])
    g = conn.execute("SELECT id::text, name, district, state FROM farmer_groups WHERE id::text = %s", (group_id,)).fetchone()
    counts = conn.execute(
        "SELECT count(*) AS members, count(*) FILTER (WHERE share_with_group) AS sharing FROM group_members WHERE group_id::text = %s",
        (group_id,),
    ).fetchone()
    fields = conn.execute(
        """SELECT f.id::text, f.name, coalesce(u.name, 'Member') AS farmer, f.area_ha, f.district,
                  (SELECT s.crop FROM seasons s WHERE s.field_id = f.id AND s.in_progress ORDER BY s.sowing_date DESC LIMIT 1) AS crop_now,
                  (SELECT count(*) FROM events e WHERE e.field_id = f.id AND e.origin = 'detected'
                      AND e.event_type IN ('dry_spell', 'waterlogging', 'flood', 'heat_stress', 'sudden_damage')
                      AND e.start_date >= current_date - 30) AS stress_30d
           FROM group_members m JOIN users u ON u.id = m.user_id JOIN fields f ON f.owner_id = m.user_id
           WHERE m.group_id::text = %s AND m.share_with_group ORDER BY f.name""",
        (group_id,),
    ).fetchall()
    crops = {}
    for f in fields:
        f["area_ha"] = float(f["area_ha"] or 0)
        if f["crop_now"]:
            crops[f["crop_now"]] = round(crops.get(f["crop_now"], 0) + f["area_ha"], 2)
    yields = conn.execute(
        """SELECT s.crop, s.season, s.year, count(*) AS n, round(avg(s.yield_mid_t_ha)::numeric, 2) AS avg_yield_t_ha
           FROM group_members m JOIN fields f ON f.owner_id = m.user_id JOIN seasons s ON s.field_id = f.id
           WHERE m.group_id::text = %s AND m.share_with_group AND NOT s.in_progress AND s.yield_mid_t_ha IS NOT NULL
           GROUP BY 1, 2, 3 ORDER BY s.year DESC, s.season LIMIT 12""",
        (group_id,),
    ).fetchall()
    return {"group": g, "members": counts["members"], "members_sharing": counts["sharing"], "fields": fields,
            "area_ha": round(sum(f["area_ha"] for f in fields), 2), "crop_area_now_ha": crops,
            "fields_with_stress_30d": sum(1 for f in fields if f["stress_30d"]), "yields": yields}
