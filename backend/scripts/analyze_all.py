"""Re-run season, crop, stress and yield analysis for every field (e.g. after training).

    python -m scripts.analyze_all
"""
from app.db.session import get_conn
from app.ml.analyze import analyze_field


def main():
    with get_conn() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id::text FROM fields WHERE ingest_status = 'done'").fetchall()]
        for fid in ids:
            print(fid, analyze_field(conn, fid))


if __name__ == "__main__":
    main()
