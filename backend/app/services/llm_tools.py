"""Tools the LLM may call to answer "Ask your field" (F10).

The LLM never sees the database directly and never chooses which field to
read: the field id comes from the request and is bound here. Every result
carries the numbers it is based on so the answer can cite them.
"""
from datetime import date

from app.ml.field_twins import find_twins
from app.ml.simulator import FieldContext, Scenario, simulate
from app.services import memory

SEASON_PARAMS = {
    "type": "object",
    "properties": {
        "year": {"type": "integer", "description": "Sowing year of the season, e.g. 2023"},
        "season": {"type": "string", "enum": ["kharif", "rabi", "zaid"]},
    },
    "required": ["year", "season"],
}

TOOLS = [
    {"name": "get_field_summary",
     "description": "Field size, location, soil, irrigation, and a list of all detected seasons with crop and "
                    "yield range. Call this first for general questions.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_season",
     "description": "Details of one season: sowing/peak/harvest dates, crop and confidence, yield range, stress "
                    "events with evidence.",
     "parameters": SEASON_PARAMS},
    {"name": "get_yield_explanation",
     "description": "Yield range of one season and the likely reasons (SHAP or rule-based) it was higher or lower.",
     "parameters": SEASON_PARAMS},
    {"name": "find_field_twins",
     "description": "The 5 most similar fields for one season and what they did differently.",
     "parameters": SEASON_PARAMS},
    {"name": "search_diary",
     "description": "Search the farmer's diary notes and earlier questions for a topic (e.g. 'urea', 'pest').",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "run_what_if",
     "description": "Simulate a future season: yield range, risk and profit for a crop, sowing date, nitrogen "
                    "and irrigation, using this field's past weather.",
     "parameters": {"type": "object", "properties": {
         "crop": {"type": "string", "enum": ["paddy", "maize", "cotton", "pulses", "chilli", "sugarcane"]},
         "season": {"type": "string", "enum": ["kharif", "rabi", "zaid"]},
         "sowing_date": {"type": "string", "description": "MM-DD, e.g. 07-15"},
         "n_kg_ha": {"type": "number", "description": "Nitrogen in kg per hectare"},
         "irrigation": {"type": "string", "enum": ["rainfed", "supplemental", "full"]},
     }, "required": ["crop", "season"]}},
]


def _season_row(conn, field_id: str, year: int, season: str) -> dict | None:
    return conn.execute(
        """SELECT id::text, year, season, crop, crop_confidence, crop_status, crop_alternatives, variety,
                  sowing_date, peak_date, harvest_date, peak_ndvi, date_detection, in_progress,
                  yield_low_t_ha, yield_mid_t_ha, yield_high_t_ha, yield_is_forecast, yield_method, shap_reasons
           FROM seasons WHERE field_id = %s AND year = %s AND season = %s""",
        (field_id, year, season),
    ).fetchone()


def _iso(d):
    return d.isoformat() if isinstance(d, date) else d


def get_field_summary(conn, field_id: str) -> dict:
    f = conn.execute(
        """SELECT name, district, state, area_ha, irrigation_type, soil_texture, clay_pct, ph_h2o,
                  soc_g_per_kg, ingest_status FROM fields WHERE id = %s""",
        (field_id,),
    ).fetchone()
    if f is None:
        return {"error": "field not found"}
    seasons = conn.execute(
        """SELECT year, season, crop, crop_status, round(crop_confidence::numeric, 2) AS crop_confidence,
                  yield_low_t_ha, yield_mid_t_ha, yield_high_t_ha, in_progress
           FROM seasons WHERE field_id = %s ORDER BY sowing_date""",
        (field_id,),
    ).fetchall()
    f["area_ha"] = float(f["area_ha"]) if f["area_ha"] is not None else None
    return {"field": f, "seasons": seasons, "source": "Kshetra field record and detected seasons"}


def get_season(conn, field_id: str, year: int, season: str) -> dict:
    s = _season_row(conn, field_id, year, season)
    if s is None:
        return {"error": f"no {season} {year} season detected for this field"}
    events = conn.execute(
        "SELECT event_type, start_date, end_date, severity, evidence FROM events WHERE season_id = %s ORDER BY start_date",
        (s["id"],),
    ).fetchall()
    out = {k: _iso(v) for k, v in s.items() if k not in ("id", "shap_reasons")}
    out["events"] = [{k: _iso(v) for k, v in e.items()} for e in events]
    out["source"] = "Sentinel-2/Sentinel-1/NISAR season detection and weather records"
    return out


def get_yield_explanation(conn, field_id: str, year: int, season: str) -> dict:
    s = _season_row(conn, field_id, year, season)
    if s is None:
        return {"error": f"no {season} {year} season detected for this field"}
    return {"crop": s["crop"], "yield_t_ha": {"low": s["yield_low_t_ha"], "mid": s["yield_mid_t_ha"],
                                             "high": s["yield_high_t_ha"]},
            "is_forecast": s["yield_is_forecast"], "method": s["yield_method"], "likely_reasons": s["shap_reasons"],
            "source": "Kshetra yield model (" + (s["yield_method"] or "none") + ")"}


def find_field_twins_tool(conn, field_id: str, year: int, season: str) -> dict:
    s = _season_row(conn, field_id, year, season)
    if s is None:
        return {"error": f"no {season} {year} season detected for this field"}
    out = find_twins(conn, s["id"])
    for t in out["twins"]:
        t.pop("field_id", None)            # other farmers' fields stay anonymous
        t["sowing_date"] = _iso(t["sowing_date"])
    out["source"] = "Similar field-seasons (k-nearest neighbours)"
    return out


def search_diary(conn, field_id: str, query: str) -> dict:
    hits = memory.search(conn, field_id, query, limit=5)
    return {"matches": hits, "source": "Farmer diary and earlier questions"}


def run_what_if(conn, field_id: str, crop: str, season: str, sowing_date: str | None = None,
                n_kg_ha: float | None = None, irrigation: str = "rainfed") -> dict:
    v = conn.execute(
        "SELECT * FROM crop_varieties WHERE crop = %s AND season = %s ORDER BY variety LIMIT 1", (crop, season)
    ).fetchone()
    if v is None:
        return {"error": f"no {crop} variety data for {season}"}
    if sowing_date:
        m, d = (int(x) for x in sowing_date.split("-"))
    else:
        m, d = (int(x) for x in v["sowing_window_start"].split("-"))
    rec = float(v["recommended_n_kg_ha"] or 0)
    sc = Scenario(crop=crop, variety=v["variety"], season=season, sowing_month_day=(m, d),
                  duration_days=int(v["duration_days"]), n_kg_ha=rec if n_kg_ha is None else float(n_kg_ha),
                  recommended_n_kg_ha=rec, irrigation=irrigation, water_need=v["water_need"] or "medium",
                  seed_cost_rs_ha=float(v["seed_cost_rs_per_ha"] or 0),
                  other_cost_rs_ha=float(v["other_cost_rs_per_ha"] or 0))
    try:
        res = simulate(FieldContext(conn, field_id), sc)
    except LookupError as exc:
        return {"error": str(exc)}
    res.pop("per_year", None)
    res["source"] = "What-if simulation over this field's past weather"
    return res


IMPLEMENTATIONS = {
    "get_field_summary": get_field_summary,
    "get_season": get_season,
    "get_yield_explanation": get_yield_explanation,
    "find_field_twins": find_field_twins_tool,
    "search_diary": search_diary,
    "run_what_if": run_what_if,
}


def call_tool(conn, field_id: str, name: str, args: dict) -> dict:
    fn = IMPLEMENTATIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(conn, field_id, **(args or {}))
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
