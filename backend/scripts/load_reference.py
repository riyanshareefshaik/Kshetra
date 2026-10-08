"""Load district crop statistics (area, production, yield) into district_yields.

Two free sources, both downloaded by hand once (no API key needed):

  * ICRISAT District Level Database (wide CSV: "RICE AREA (1000 ha)", ...):
        python -m scripts.load_reference icrisat data/icrisat_dld.csv
  * Ministry of Agriculture district APY data (long CSV with State, District,
    Year, Season, Crop, Area, Production), from data.desagri.gov.in or the
    data.gov.in "District-wise, season-wise crop production statistics" set:
        python -m scripts.load_reference apy data/district_apy.csv

ICRISAT's free edition ends around 2017, so for the 2017+ seasons Kshetra
detects, the Ministry APY data is the one that overlaps. Crop names are mapped
to Kshetra's crop keys; crops Kshetra does not model are skipped.
"""
import argparse
import csv
import re
from pathlib import Path

from app.db.session import get_conn

# Source crop name (lower case) -> Kshetra crop key
CROP_ALIASES = {
    "rice": "paddy", "paddy": "paddy",
    "maize": "maize",
    "cotton": "cotton", "cotton(lint)": "cotton", "cotton (lint)": "cotton",
    "urad": "pulses", "blackgram": "pulses", "black gram": "pulses", "urad(blackgram)": "pulses",
    "moong": "pulses", "greengram": "pulses", "green gram": "pulses", "moong(green gram)": "pulses",
    "chillies": "chilli", "dry chillies": "chilli", "chilli": "chilli",
    "sugarcane": "sugarcane",
}
SEASONS = {"kharif": "kharif", "rabi": "rabi", "summer": "zaid", "zaid": "zaid",
           "whole year": "total", "total": "total", "autumn": "kharif", "winter": "rabi"}
BALE_T = 0.17                  # cotton is reported in bales of 170 kg lint
LINT_TO_SEED_COTTON = 1 / 0.34  # ginning out-turn ~34%; farmers sell seed cotton (kapas)


def crop_key(name: str) -> str | None:
    return CROP_ALIASES.get(re.sub(r"\s+", " ", name.strip().lower()))


def start_year(text: str) -> int:
    """'2019', '2019-20', '2019 - 2020' -> 2019"""
    return int(re.match(r"\s*(\d{4})", str(text)).group(1))


def _num(v) -> float | None:
    try:
        x = float(str(v).replace(",", "").strip())
        return x if x >= 0 else None
    except ValueError:
        return None


def _col(header: list[str], *candidates: str) -> str:
    lower = {h.lower().strip(): h for h in header}
    for c in candidates:
        if c in lower:
            return lower[c]
    raise KeyError(f"none of {candidates} in CSV header")


def parse_icrisat(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        state_c, dist_c, year_c = _col(header, "state name"), _col(header, "dist name"), _col(header, "year")
        crops = {}
        for h in header:
            m = re.match(r"(.+?) (AREA|PRODUCTION|YIELD) \(", h.strip(), re.IGNORECASE)
            if m and crop_key(m.group(1)):
                crops.setdefault(m.group(1), {})[m.group(2).upper()] = h
        for r in reader:
            for name, cols in crops.items():
                key = crop_key(name)
                area = _num(r.get(cols.get("AREA", ""), ""))
                prod = _num(r.get(cols.get("PRODUCTION", ""), ""))
                yld = _num(r.get(cols.get("YIELD", ""), ""))     # kg/ha
                if not area:
                    continue
                y = yld / 1000 if yld else (prod / area if prod else None)
                if key == "cotton" and y:
                    y *= LINT_TO_SEED_COTTON
                rows.append({"state": r[state_c].strip().title(), "district": r[dist_c].strip().title(),
                             "year": start_year(r[year_c]), "season": "total", "crop": key,
                             "area_ha": area * 1000, "production_t": prod * 1000 if prod else None,
                             "yield_t_ha": round(y, 3) if y else None, "source": "icrisat_dld"})
    return rows


def parse_apy(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        h = reader.fieldnames or []
        c = {
            "state": _col(h, "state_name", "state"), "district": _col(h, "district_name", "district"),
            "year": _col(h, "crop_year", "year"), "season": _col(h, "season"), "crop": _col(h, "crop"),
            "area": _col(h, "area", "area (hectare)", "area_ha"),
            "prod": _col(h, "production", "production (tonnes)", "production_t"),
        }
        for r in reader:
            key = crop_key(r[c["crop"]])
            season = SEASONS.get(r[c["season"]].strip().lower())
            area, prod = _num(r[c["area"]]), _num(r[c["prod"]])
            if not key or not season or not area:
                continue
            if key == "cotton" and prod:
                prod = prod * BALE_T * LINT_TO_SEED_COTTON
            rows.append({"state": r[c["state"]].strip().title(), "district": r[c["district"]].strip().title(),
                         "year": start_year(r[c["year"]]), "season": season, "crop": key,
                         "area_ha": area, "production_t": prod,
                         "yield_t_ha": round(prod / area, 3) if prod else None, "source": "data_gov_in"})
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    """Black gram + green gram both map to 'pulses': sum them per district-year-season."""
    out: dict[tuple, dict] = {}
    for r in rows:
        k = (r["state"], r["district"], r["year"], r["season"], r["crop"], r["source"])
        if k not in out:
            out[k] = dict(r)
            continue
        o = out[k]
        o["area_ha"] += r["area_ha"]
        o["production_t"] = (o["production_t"] or 0) + (r["production_t"] or 0) or None
        o["yield_t_ha"] = round(o["production_t"] / o["area_ha"], 3) if o["production_t"] else None
    return list(out.values())


def load(rows: list[dict]) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO district_yields (state, district, year, season, crop, area_ha, production_t, yield_t_ha, source)
               VALUES (%(state)s, %(district)s, %(year)s, %(season)s, %(crop)s, %(area_ha)s, %(production_t)s,
                       %(yield_t_ha)s, %(source)s)
               ON CONFLICT (state, district, year, season, crop, source) DO UPDATE
                  SET area_ha = EXCLUDED.area_ha, production_t = EXCLUDED.production_t,
                      yield_t_ha = EXCLUDED.yield_t_ha""",
            rows,
        )
        conn.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Load district crop statistics into district_yields")
    ap.add_argument("format", choices=["icrisat", "apy"])
    ap.add_argument("csv", type=Path)
    args = ap.parse_args()
    rows = aggregate(parse_icrisat(args.csv) if args.format == "icrisat" else parse_apy(args.csv))
    print(f"loaded {load(rows)} district-crop-year rows")


if __name__ == "__main__":
    main()
