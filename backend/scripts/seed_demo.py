"""Load the demo fields, build their history from free satellite and weather data, and analyse it.

    cd backend
    python -m scripts.seed_demo                 # all demo fields, 2017 -> yesterday
    python -m scripts.seed_demo --start 2023-01-01 --limit 2

Needs: DATABASE_URL, and `earthengine authenticate` + GEE_PROJECT for Sentinel data.
Optional: EARTHDATA_TOKEN (NISAR L-band); NISAR S-band GCOV files in data/nisar_s/.
Everything fetched is cached in api_cache, so running it again is fast and offline-safe.
"""
import argparse
import json
import logging
from datetime import date
from pathlib import Path

from app.db.session import get_conn
from app.ml.analyze import analyze_field
from app.services.ingest import ingest_field

SEED_FILE = Path(__file__).resolve().parents[2] / "database" / "seeds" / "demo_fields.geojson"
DEMO_PHONE = "demo-farmer"


def upsert_demo_fields(conn) -> list[str]:
    owner = conn.execute(
        "INSERT INTO users (name, phone, preferred_language) VALUES ('Demo farmer', %s, 'te')"
        " ON CONFLICT (phone) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (DEMO_PHONE,),
    ).fetchone()["id"]
    ids = []
    for feat in json.loads(SEED_FILE.read_text())["features"]:
        p = feat["properties"]
        existing = conn.execute(
            "SELECT id::text FROM fields WHERE owner_id = %s AND name = %s", (owner, p["name"])
        ).fetchone()
        if existing:
            ids.append(existing["id"])
            continue
        row = conn.execute(
            "INSERT INTO fields (owner_id, name, boundary, boundary_source, district, state)"
            " VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s) RETURNING id::text",
            (owner, p["name"], json.dumps(feat["geometry"]), p["boundary_source"], p["district"], p["state"]),
        ).fetchone()
        ids.append(row["id"])
    conn.commit()
    return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=date.fromisoformat, default=None)
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with get_conn() as conn:
        ids = upsert_demo_fields(conn)[: args.limit]
        for fid in ids:
            rep = ingest_field(conn, fid, start=args.start, end=args.end)
            print(f"{fid}: {rep.rows} rows {rep.counts}")
            for err in rep.errors:
                print(f"   ! {err}")
            if rep.rows:
                print(f"   seasons: {analyze_field(conn, fid)}")


if __name__ == "__main__":
    main()
