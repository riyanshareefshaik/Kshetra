"""Government scheme finder (feature 8): which schemes fit this farmer, and why.

The list is curated in database/seeds/schemes.json (benefits change: every entry links to the
official site, and the app says to check current rules). Matching uses only what Kshetra knows:
state, land area, irrigation, crops, and whether there is a recent soil test.
"""
import json
from datetime import date, timedelta
from pathlib import Path

from app.db.seeds import SEEDS

SMALL_FARMER_HA = 2.0


def load() -> list[dict]:
    return json.loads(Path(SEEDS / "schemes.json").read_text(encoding="utf-8"))


def profile(conn, user_id: str | None, local: bool) -> dict:
    owner = None if local else user_id
    fields = conn.execute(
        """SELECT f.id, f.state, f.area_ha, f.irrigation_type,
                  (SELECT max(test_date) FROM soil_tests t WHERE t.field_id = f.id) AS soil_test,
                  (SELECT count(*) FROM seasons s WHERE s.field_id = f.id AND s.crop IS NOT NULL) AS seasons
           FROM fields f WHERE (%s::uuid IS NULL OR f.owner_id = %s::uuid)""",
        (owner, owner),
    ).fetchall()
    area = sum(float(f["area_ha"] or 0) for f in fields)
    tests = [f["soil_test"] for f in fields if f["soil_test"]]
    return {
        "fields": len(fields),
        "area_ha": round(area, 2),
        "states": sorted({f["state"] for f in fields if f["state"]}),
        "irrigation": sorted({f["irrigation_type"] or "unknown" for f in fields}),
        "grows_crops": any(f["seasons"] for f in fields),
        "last_soil_test": max(tests) if tests else None,
    }


def match(schemes: list[dict], p: dict, today: date) -> list[dict]:
    out = []
    small = 0 < p["area_ha"] <= SMALL_FARMER_HA
    for s in schemes:
        rule, why = s["rule"], None
        if rule == "all":
            why = "Open to all farmers."
        elif rule == "landowner" and p["fields"]:
            why = "You have farmland in Kshetra; available to land-owning families (exclusions apply)."
        elif rule == "grows_crop" and p["fields"]:
            why = "Protects the crops you grow against weather losses."
        elif rule == "no_micro_irrigation" and not ({"drip", "sprinkler"} & set(p["irrigation"])):
            why = ("You do not use drip or sprinkler yet" + ("; as a small farmer you get the higher 55% subsidy."
                                                              if small else "."))
        elif rule == "pump_or_rainfed" and ({"borewell", "rainfed", "unknown"} & set(p["irrigation"])):
            why = "Your fields are rainfed or use a pump; a solar pump cuts diesel/electricity costs."
        elif rule == "no_recent_soil_test" and (p["last_soil_test"] is None
                                                or p["last_soil_test"] < today - timedelta(days=3 * 365)):
            why = "No soil test in the last 3 years; a free test gives exact fertilizer doses."
        elif rule == "state" and s.get("state") in p["states"]:
            why = f"You farm in {s['state']}."
        if why:
            out.append({**{k: v for k, v in s.items() if k != "rule"}, "why": why})
    return sorted(out, key=lambda s: s["level"] != "state")
