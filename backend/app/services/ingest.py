"""Build a field's history: soil, weather, Sentinel-2, Sentinel-1 and NISAR -> Postgres.

    ingest_field(conn, field_id)

Every external response goes through api_cache, so re-running is cheap and a
field that was ingested once never needs the network again. A source that
fails (no key yet, API down) is recorded in fields.ingest_error and skipped;
the rest still load.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, timedelta
from functools import partial
from pathlib import Path

import httpx
import pandas as pd
import psycopg

from app.config import get_settings
from app.ml.ndvi_gapfill import fill_and_smooth
from app.services import earth_engine, nisar, soil, weather
from app.services.cache import cached, ttl_for_period

log = logging.getLogger(__name__)

START_YEAR = 2017
NISAR_S_DIR = Path(__file__).resolve().parents[3] / "data" / "nisar_s"

TS_COLUMNS = [
    "ndvi", "ndvi_smoothed", "ndvi_source", "cloud_pct",
    "sar_vv", "sar_vh",
    "nisar_l_hh", "nisar_l_hv", "nisar_s_hh", "nisar_s_hv",
    "rainfall_mm", "temp_max_c", "temp_min_c", "temp_mean_c", "et0_mm", "soil_moisture",
]
SOURCE_TAGS = {
    "ndvi": "s2", "sar_vv": "s1", "nisar_l_hh": "nisar_l", "nisar_s_hh": "nisar_s", "rainfall_mm": "weather",
}


@dataclass
class Fetchers:
    """External calls, swappable in tests."""
    soilgrids: Callable = soil.fetch_soilgrids
    open_meteo: Callable = weather.fetch_open_meteo
    nasa_power: Callable = weather.fetch_nasa_power
    s2: Callable = earth_engine.fetch_s2_ndvi
    s1: Callable = earth_engine.fetch_s1_sar
    nisar_search: Callable = nisar.search_l_band
    nisar_resolve: Callable = nisar.resolve_signed_url
    nisar_read_url: Callable = nisar.read_gcov_url
    nisar_read_file: Callable = nisar.read_gcov_file


@dataclass
class IngestReport:
    field_id: str
    rows: int = 0
    counts: dict = dc_field(default_factory=dict)
    errors: list = dc_field(default_factory=list)


def _years(start: date, end: date):
    for y in range(start.year, end.year + 1):
        yield y, max(start, date(y, 1, 1)), min(end, date(y, 12, 31))


def _load_field(conn, field_id: str) -> dict:
    row = conn.execute(
        "SELECT id::text, ST_AsGeoJSON(boundary)::json AS geometry,"
        " ST_Y(location) AS lat, ST_X(location) AS lon FROM fields WHERE id = %s",
        (field_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"field {field_id} not found")
    return row


def _set_status(conn, field_id: str, status: str, error: str | None = None):
    conn.execute(
        "UPDATE fields SET ingest_status = %s, ingest_error = %s, updated_at = now() WHERE id = %s",
        (status, error, field_id),
    )
    conn.commit()


def ingest_field(
    conn: psycopg.Connection,
    field_id: str,
    start: date | None = None,
    end: date | None = None,
    http: httpx.Client | None = None,
    fetchers: Fetchers | None = None,
) -> IngestReport:
    f = fetchers or Fetchers()
    start = start or date(START_YEAR, 1, 1)
    end = end or date.today() - timedelta(days=1)  # noqa: DTZ011 - local calendar day
    own_http = http is None
    http = http or httpx.Client(headers={"User-Agent": "Kshetra/0.1 (hackathon; non-commercial)"})
    report = IngestReport(field_id=field_id)

    fld = _load_field(conn, field_id)
    geom, lat, lon = fld["geometry"], fld["lat"], fld["lon"]
    _set_status(conn, field_id, "running")

    def attempt(name: str, fn: Callable):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - one bad source must not stop the rest
            log.warning("ingest %s: %s failed: %s", field_id, name, exc)
            report.errors.append(f"{name}: {type(exc).__name__}: {exc}"[:300])
            return None

    try:
        # --- soil (Layer 1)
        soil_params = {"lat": round(lat, 5), "lon": round(lon, 5)}
        soil_row = attempt("soilgrids", lambda: soil.parse_soilgrids(
            cached(conn, "soilgrids", soil_params, partial(f.soilgrids, http, lat, lon))))
        if soil_row:
            cols = ", ".join(f"{k} = %({k})s" for k in soil_row)
            conn.execute(f"UPDATE fields SET {cols} WHERE id = %(id)s", {**soil_row, "id": field_id})
            conn.commit()

        frames: list[pd.DataFrame] = []

        def add(rows):
            if rows:
                frames.append(pd.DataFrame(rows).assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date"))

        for year, y0, y1 in _years(start, end):
            add(attempt(f"weather {year}", partial(_weather, conn, http, f, lat, lon, y0, y1, report)))
            add(attempt(f"sentinel2 {year}", partial(_sentinel, conn, "gee_s2", f.s2, earth_engine.parse_s2, geom, y0, y1)))
            add(attempt(f"sentinel1 {year}", partial(_sentinel, conn, "gee_s1", f.s1, earth_engine.parse_s1, geom, y0, y1)))

        add(attempt("nisar L-band", lambda: _nisar_l(conn, http, f, field_id, geom, start, end)))
        add(attempt("nisar S-band", lambda: _nisar_s(conn, f, field_id, geom)))

        if not frames:
            raise RuntimeError("no data from any source")

        daily = _assemble(frames, start, end)
        report.counts = {
            "ndvi_obs": int(daily["ndvi"].notna().sum()),
            "sentinel1": int(daily["sar_vv"].notna().sum()),
            "nisar_l": int(daily["nisar_l_hh"].notna().sum()),
            "nisar_s": int(daily["nisar_s_hh"].notna().sum()),
            "weather_days": int(daily["rainfall_mm"].notna().sum()),
        }
        if daily["ndvi"].notna().any():
            daily = fill_and_smooth(daily)
        report.counts["ndvi_filled"] = int((daily["ndvi_source"] == "sar_fill").sum())
        report.rows = _upsert(conn, field_id, daily)

        status = "done" if report.counts["ndvi_obs"] and report.counts["weather_days"] else "failed"
        _set_status(conn, field_id, status, "; ".join(report.errors) or None)
    except Exception as exc:  # noqa: BLE001 - always record the failure on the field
        conn.rollback()
        report.errors.append(f"{type(exc).__name__}: {exc}")
        _set_status(conn, field_id, "failed", "; ".join(report.errors)[:2000])
    finally:
        if own_http:
            http.close()
    return report


def _weather(conn, http, f: Fetchers, lat, lon, y0: date, y1: date, report: IngestReport) -> list[dict]:
    """Open-Meteo for one period, NASA POWER if Open-Meteo fails."""
    params = {"lat": round(lat, 4), "lon": round(lon, 4), "start": y0, "end": y1}
    ttl = ttl_for_period(y1)
    try:
        payload = cached(conn, "open_meteo", params, partial(f.open_meteo, http, lat, lon, y0, y1), ttl)
        return weather.parse_open_meteo(payload)
    except Exception as exc:  # noqa: BLE001 - fall back to the second free source
        report.errors.append(f"open_meteo {y0.year}: {exc}"[:300])
        payload = cached(conn, "nasa_power", params, partial(f.nasa_power, http, lat, lon, y0, y1), ttl)
        return weather.parse_nasa_power(payload)


def _sentinel(conn, source: str, fetch: Callable, parse: Callable, geom, y0: date, y1: date) -> list[dict]:
    params = {"geometry": geom, "start": y0, "end": y1}
    return parse(cached(conn, source, params, partial(fetch, geom, y0, y1), ttl_for_period(y1)))


def _read_nisar_l(f: Fetchers, http, token: str, granule: dict, field_id: str, geom) -> dict:
    band, acq, stats = f.nisar_read_url(f.nisar_resolve(http, granule["url"], token), {field_id: geom})
    acq = acq or date.fromisoformat(granule["date"])
    return {"band": band, "date": acq.isoformat(), "stats": stats.get(field_id)}


def _read_nisar_s(f: Fetchers, path: Path, field_id: str, geom) -> dict:
    band, acq, stats = f.nisar_read_file(path, {field_id: geom})
    return {"band": band, "date": acq.isoformat() if acq else None, "stats": stats.get(field_id)}


def _nisar_l(conn, http, f: Fetchers, field_id, geom, start, end) -> list[dict]:
    token = get_settings().earthdata_token
    if not token:
        raise RuntimeError("EARTHDATA_TOKEN not set; skipping NISAR L-band")
    nisar_start = max(start, date(2025, 7, 1))
    if nisar_start > end:
        return []
    granules = cached(conn, "nisar_l_search", {"geometry": geom, "start": nisar_start, "end": end},
                      lambda: f.nisar_search(http, geom, nisar_start, end), timedelta(days=1))
    rows = []
    for g in granules:
        read = partial(_read_nisar_l, f, http, token, g, field_id, geom)
        res = cached(conn, "nisar_l", {"granule": g["id"], "geometry": geom}, read)
        if res["stats"]:
            rows.append(nisar.to_rows(res["band"], date.fromisoformat(res["date"]), res["stats"]))
    return rows


def _nisar_s(conn, f: Fetchers, field_id, geom) -> list[dict]:
    rows = []
    for path in sorted(NISAR_S_DIR.glob("*.h5")):
        read = partial(_read_nisar_s, f, path, field_id, geom)
        res = cached(conn, "nisar_s", {"file": path.name, "geometry": geom}, read)
        if res["stats"] and res["date"]:
            rows.append(nisar.to_rows(res["band"], date.fromisoformat(res["date"]), res["stats"]))
    return rows


def _assemble(frames: list[pd.DataFrame], start: date, end: date) -> pd.DataFrame:
    """Combine all sources onto one daily index (first non-null value per column and day)."""
    combined = pd.concat(frames).groupby(level=0).first()
    idx = pd.date_range(start, end, freq="D", name="date")
    daily = combined.reindex(idx)
    for col in TS_COLUMNS:
        if col not in daily:
            daily[col] = None
        if col != "ndvi_source":
            daily[col] = pd.to_numeric(daily[col], errors="coerce")
    return daily


def _upsert(conn, field_id: str, daily: pd.DataFrame) -> int:
    has_data = daily[[c for c in TS_COLUMNS if c != "ndvi_source"]].notna().any(axis=1)
    df = daily[has_data]
    records = []
    for day, r in df.iterrows():
        rec = {c: (None if pd.isna(r[c]) else r[c]) for c in TS_COLUMNS}
        rec = {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
               for k, v in rec.items()}
        rec["sources"] = [tag for col, tag in SOURCE_TAGS.items() if rec.get(col) is not None]
        if rec["ndvi_source"] == "sar_fill":
            rec["sources"] = [t for t in rec["sources"] if t != "s2"] + ["sar_fill"]
        rec["field_id"], rec["date"] = field_id, day.date()
        records.append(rec)

    cols = ["field_id", "date", *TS_COLUMNS, "sources"]
    sql = (
        f"INSERT INTO field_timeseries ({', '.join(cols)}) VALUES ({', '.join(f'%({c})s' for c in cols)}) "
        f"ON CONFLICT (field_id, date) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[2:])
    )
    with conn.cursor() as cur:
        cur.executemany(sql, records)
    conn.commit()
    return len(records)
