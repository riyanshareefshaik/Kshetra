"""PMFBY claim helper (feature 7).

Under PMFBY, *localised* losses (inundation, hailstorm, landslide, cloudburst, natural fire) and
*post-harvest* losses (crop cut and left to dry in the field, damaged by cyclonic or unseasonal rain
within 14 days of harvest) are assessed per farm only if reported within 72 hours: on the Crop
Insurance app, the Krishi Rakshak helpline 14447, the insurer, the bank, a CSC or the agriculture
office. Widespread drought or flood is settled area-wide without individual reports.

Kshetra flags satellite/weather events that may qualify and prepares the evidence. Satellite
detection can lag a few days, so the farmer should report as soon as they notice damage.
"""
from datetime import UTC, datetime, timedelta

HELPLINE = "14447"
REPORT_HOURS = 72
POST_HARVEST_DAYS = 14
POST_HARVEST_RAIN_MM = 50          # 3-day rain that can damage a cut crop lying in the field

KIND = {
    "flood": ("Inundation (flooding)", "localised"),
    "waterlogging": ("Inundation (waterlogging)", "localised"),
    "sudden_damage": ("Sudden crop damage (e.g. hailstorm, fire, cloudburst)", "localised"),
}
STEPS = [
    (f"Report within {REPORT_HOURS} hours: Crop Insurance app, or call the Krishi Rakshak helpline {HELPLINE} "
     "(toll free), or tell your bank branch, CSC or agriculture office."),
    "Note the ticket / docket number you are given: it is your proof that you reported in time.",
    "Keep photos of the damaged crop with the date, and this evidence sheet, for the surveyor's visit.",
]
DOCUMENTS = ["Aadhaar card", "Bank passbook (account linked to Aadhaar)", "Land record or tenancy certificate (e.g. CCRC)",
             "Sowing certificate / crop declaration", "PMFBY policy or premium receipt", "Photos of the damage"]


def candidates(conn, field_id: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    rows = conn.execute(
        """SELECT e.id::text, e.event_type, e.start_date, e.end_date, e.severity, e.evidence,
                  s.crop, s.season, s.year
           FROM events e LEFT JOIN seasons s ON s.id = e.season_id
           WHERE e.field_id = %s AND e.origin = 'detected' AND e.event_type = ANY(%s)
           ORDER BY e.start_date DESC""",
        (field_id, list(KIND)),
    ).fetchall()
    out = []
    for r in rows:
        label, kind = KIND[r["event_type"]]
        out.append(_claim(r["id"], label, kind, r["start_date"], r["end_date"], r["severity"], r["evidence"],
                          r["crop"], r["season"], r["year"], now))
    # Post-harvest: heavy rain within 14 days after a detected harvest.
    harvests = conn.execute(
        "SELECT id::text, crop, season, year, harvest_date FROM seasons WHERE field_id = %s AND harvest_date IS NOT NULL",
        (field_id,),
    ).fetchall()
    for h in harvests:
        rain = conn.execute(
            """SELECT date, sum(rainfall_mm) OVER (ORDER BY date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS r3
               FROM field_timeseries WHERE field_id = %s AND date BETWEEN %s AND %s ORDER BY r3 DESC NULLS LAST LIMIT 1""",
            (field_id, h["harvest_date"], h["harvest_date"] + timedelta(days=POST_HARVEST_DAYS)),
        ).fetchone()
        if rain and rain["r3"] and rain["r3"] >= POST_HARVEST_RAIN_MM:
            out.append(_claim(f"post-{h['id']}", "Post-harvest rain damage (crop lying in the field)", "post_harvest",
                              rain["date"] - timedelta(days=2), rain["date"], min(rain["r3"] / 150, 1.0),
                              {"rain_3day_mm": round(rain["r3"], 1), "days_after_harvest": (rain["date"] - h["harvest_date"]).days},
                              h["crop"], h["season"], h["year"], now))
    return sorted(out, key=lambda c: c["start_date"], reverse=True)


def _claim(cid, label, kind, start, end, severity, evidence, crop, season, year, now):
    deadline = datetime.combine(start, datetime.min.time(), UTC) + timedelta(hours=REPORT_HOURS)
    hours_left = (deadline - now).total_seconds() / 3600
    return {"id": cid, "label": label, "kind": kind, "start_date": start, "end_date": end,
            "severity": severity, "evidence": evidence, "crop": crop, "season": season, "year": year,
            "report_by": deadline.isoformat(), "hours_left": round(hours_left) if hours_left > 0 else 0,
            "open": hours_left > 0}
