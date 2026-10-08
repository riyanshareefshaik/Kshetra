"""Reference data shipped with the repo (database/seeds)."""
import csv
from pathlib import Path

SEEDS = Path(__file__).resolve().parents[3] / "database" / "seeds"
if not SEEDS.exists():                       # Docker image: seeds copied next to the app
    SEEDS = Path(__file__).resolve().parents[2] / "seeds"


def load_crop_varieties(conn, only_if_empty: bool = False) -> int:
    if only_if_empty and conn.execute("SELECT EXISTS (SELECT 1 FROM crop_varieties) AS e").fetchone()["e"]:
        return 0
    path = SEEDS / "crop_varieties.csv"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["states"] = [s.strip() for s in r["states"].split(";") if s.strip()]
        for k in ("duration_days", "recommended_n_kg_ha", "seed_cost_rs_per_ha", "other_cost_rs_per_ha"):
            r[k] = float(r[k]) if r[k] else None
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO crop_varieties (crop, variety, season, duration_days, sowing_window_start, sowing_window_end,
                   water_need, recommended_n_kg_ha, seed_cost_rs_per_ha, other_cost_rs_per_ha, states, source)
               VALUES (%(crop)s, %(variety)s, %(season)s, %(duration_days)s, %(sowing_window_start)s,
                       %(sowing_window_end)s, %(water_need)s, %(recommended_n_kg_ha)s, %(seed_cost_rs_per_ha)s,
                       %(other_cost_rs_per_ha)s, %(states)s, %(source)s)
               ON CONFLICT (crop, variety, season) DO UPDATE SET
                   duration_days = EXCLUDED.duration_days, sowing_window_start = EXCLUDED.sowing_window_start,
                   sowing_window_end = EXCLUDED.sowing_window_end, water_need = EXCLUDED.water_need,
                   recommended_n_kg_ha = EXCLUDED.recommended_n_kg_ha,
                   seed_cost_rs_per_ha = EXCLUDED.seed_cost_rs_per_ha,
                   other_cost_rs_per_ha = EXCLUDED.other_cost_rs_per_ha, states = EXCLUDED.states,
                   source = EXCLUDED.source""",
            rows,
        )
    conn.commit()
    return len(rows)
