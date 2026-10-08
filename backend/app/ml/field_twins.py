"""Field twins (F7): the 5 most similar field-seasons, and what they did differently.

Similarity is k-NN on `seasons.feature_vector` (pgvector, Euclidean) over soil,
timing, greenness and weather, restricted to the same crop and season type and
excluding the field itself. Differences compare things a farmer controls:
sowing date, variety, and the inputs recorded in the diary.
"""
import psycopg

K = 5


def find_twins(conn: psycopg.Connection, season_id: str, k: int = K) -> dict:
    me = conn.execute(
        """SELECT s.id::text, s.field_id::text, s.crop, s.season, s.year, s.sowing_date, s.variety,
                  s.yield_mid_t_ha, s.feature_vector IS NOT NULL AS has_vec, f.irrigation_type
           FROM seasons s JOIN fields f ON f.id = s.field_id WHERE s.id = %s""",
        (season_id,),
    ).fetchone()
    if me is None or not me["has_vec"]:
        return {"season_id": season_id, "twins": [], "note": "season not analysed yet"}

    twins = conn.execute(
        """SELECT t.id::text AS season_id, t.field_id::text, t.year, t.crop, t.variety, t.sowing_date,
                  t.yield_low_t_ha, t.yield_mid_t_ha, t.yield_high_t_ha, f.district, f.irrigation_type,
                  round((t.feature_vector <-> m.feature_vector)::numeric, 3) AS distance,
                  (SELECT count(*) FROM events e WHERE e.season_id = t.id AND e.origin = 'detected'
                      AND e.event_type IN ('dry_spell', 'waterlogging', 'flood', 'heat_stress', 'sudden_damage'))
                      AS stress_events
           FROM seasons t
           JOIN seasons m ON m.id = %(sid)s
           JOIN fields f ON f.id = t.field_id
           WHERE t.field_id <> m.field_id
             AND t.season = m.season
             AND t.crop IS NOT DISTINCT FROM m.crop
             AND t.feature_vector IS NOT NULL
             AND vector_dims(t.feature_vector) = vector_dims(m.feature_vector)
           ORDER BY t.feature_vector <-> m.feature_vector
           LIMIT %(k)s""",
        {"sid": season_id, "k": k},
    ).fetchall()

    for t in twins:
        t["differences"] = differences(conn, me, t)
    return {"season_id": season_id, "crop": me["crop"], "season": me["season"], "year": me["year"],
            "your_yield_mid_t_ha": me["yield_mid_t_ha"], "twins": twins}


def _diary_inputs(conn, season_id: str) -> dict:
    rows = conn.execute(
        "SELECT activity_type, count(*) AS n FROM diary_entries WHERE season_id = %s GROUP BY activity_type",
        (season_id,),
    ).fetchall()
    return {r["activity_type"]: r["n"] for r in rows}


def differences(conn, me: dict, twin: dict) -> list[dict]:
    """What the twin did differently, as {code, values..., text} (the app words it per language)."""
    out = []
    if me["sowing_date"] and twin["sowing_date"]:
        gap = twin["sowing_date"].timetuple().tm_yday - me["sowing_date"].timetuple().tm_yday
        if abs(gap) >= 7:
            code = "sowed_later" if gap > 0 else "sowed_earlier"
            out.append({"code": code, "days": abs(gap),
                        "text": f"Sowed {abs(gap)} days {'later' if gap > 0 else 'earlier'} than you."})
    if twin["variety"] and twin["variety"] != me["variety"]:
        out.append({"code": "variety", "variety": twin["variety"], "text": f"Grew variety {twin['variety']}."})
    if twin["irrigation_type"] and twin["irrigation_type"] != me["irrigation_type"]:
        out.append({"code": "irrigation", "irrigation": twin["irrigation_type"],
                    "text": f"Irrigation: {twin['irrigation_type']}."})
    mine, theirs = _diary_inputs(conn, me["id"]), _diary_inputs(conn, twin["season_id"])
    for act in ("fertilizer", "irrigation", "pesticide", "weeding"):
        if theirs.get(act, 0) != mine.get(act, 0) and (theirs.get(act) or mine.get(act)):
            out.append({"code": "diary", "activity": act, "theirs": theirs.get(act, 0), "mine": mine.get(act, 0),
                        "text": f"Recorded {theirs.get(act, 0)} {act} entries (you: {mine.get(act, 0)})."})
    if twin["stress_events"] == 0:
        out.append({"code": "no_stress", "text": "No stress events detected in their season."})
    return out
