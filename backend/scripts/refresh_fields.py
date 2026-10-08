"""Pull the latest satellite, NISAR, weather and soil data for every field, then re-analyse.

    python -m scripts.refresh_fields                    # all fields, 2017 -> yesterday
    python -m scripts.refresh_fields --start 2024-01-01 # only re-fetch recent data

Fields are normally created and refreshed from the app (Map page). Use this
after adding keys (e.g. EARTHDATA_TOKEN) or to bring all fields up to date.
Already-fetched data comes from api_cache, so re-runs are fast.
"""
import argparse
import logging
from datetime import date

from app.db.session import get_conn
from app.ml.analyze import analyze_field
from app.services.ingest import ingest_field


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=date.fromisoformat, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with get_conn() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id::text FROM fields ORDER BY created_at").fetchall()]
        if not ids:
            print("No fields yet: add one on the Map page.")
        for fid in ids:
            rep = ingest_field(conn, fid, start=args.start)
            print(f"{fid}: {rep.rows} rows {rep.counts}")
            for err in rep.errors:
                print(f"   ! {err}")
            if rep.rows:
                print(f"   seasons: {analyze_field(conn, fid)}")


if __name__ == "__main__":
    main()
