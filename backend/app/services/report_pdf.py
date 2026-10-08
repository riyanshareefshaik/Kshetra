"""Field health report PDF (F12) for crop loans and PMFBY insurance claims.

HTML (Jinja2) -> PDF (WeasyPrint, BSD). Charts are drawn as inline SVG, so no
plotting library or network access is needed. The report states its data
sources and methods, marks estimates as ranges, and carries a SHA-256 digest of
the data it was built from so a bank can check a copy was not edited.
"""
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.ml.analyze import load_timeseries

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
CHART_YEARS = 4


def _svg_ndvi(ts, seasons, width=720, height=170) -> str:
    if ts.empty or ts["ndvi_smoothed"].notna().sum() == 0:
        return ""
    end = ts.index.max()
    ts = ts.loc[end - timedelta(days=365 * CHART_YEARS):]
    t0, t1 = ts.index.min(), ts.index.max()
    span = max((t1 - t0).days, 1)
    pad_l, pad_b = 34, 22
    w, h = width - pad_l - 6, height - pad_b - 6

    def x(d):
        return pad_l + w * (d - t0).days / span

    def y(v):
        return 6 + h * (1 - v)

    parts = []
    for s in seasons:
        a = max(pd.Timestamp(s["sowing_date"]), t0)
        b = pd.Timestamp(s["harvest_date"]) if s["harvest_date"] else t1
        if b <= t0:
            continue
        xa, xb = x(a), x(b)
        parts.append(f'<rect x="{xa:.1f}" y="6" width="{max(xb - xa, 1):.1f}" height="{h}" fill="#e8f3e8"/>')
        parts.append(f'<text x="{(xa + xb) / 2:.1f}" y="16" font-size="8" text-anchor="middle" fill="#2e5d32">'
                     f'{s["crop"] or "?"}</text>')
    for v in (0.0, 0.5, 1.0):
        parts.append(f'<line x1="{pad_l}" x2="{pad_l + w}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#ddd" stroke-width="0.5"/>')
        parts.append(f'<text x="{pad_l - 4}" y="{y(v) + 3:.1f}" font-size="8" text-anchor="end" fill="#666">{v:.1f}</text>')
    for yr in range(t0.year + 1, t1.year + 1):
        d = pd.Timestamp(yr, 1, 1)
        parts.append(f'<text x="{x(d):.1f}" y="{height - 6}" font-size="8" text-anchor="middle" fill="#666">{yr}</text>')
    pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in ts["ndvi_smoothed"].dropna().items())
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#2f7d32" stroke-width="1.4"/>')
    obs = ts[ts["ndvi_source"] == "s2"]["ndvi"].dropna()
    parts += [f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="1.2" fill="#1b5e20"/>' for d, v in obs.items()]
    fill = ts[ts["ndvi_source"] == "sar_fill"]["ndvi"].dropna()
    parts += [f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="1.2" fill="#7e57c2"/>' for d, v in fill.items()]
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">{"".join(parts)}</svg>'


def _svg_boundary(geojson: dict, size=150) -> str:
    ring = geojson["coordinates"][0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1e-6
    pts = " ".join(f"{10 + (size - 20) * (px - min(xs)) / span:.1f},{size - 10 - (size - 20) * (py - min(ys)) / span:.1f}"
                   for px, py in ring)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">'
            f'<polygon points="{pts}" fill="#c8e6c9" stroke="#2e7d32" stroke-width="1.5"/></svg>')


def build_report_data(conn, field_id: str) -> dict:
    f = conn.execute(
        """SELECT id::text, name, village, district, state, area_ha, boundary_source, irrigation_type,
                  soil_texture, clay_pct, sand_pct, ph_h2o, soc_g_per_kg, is_synthetic,
                  ST_AsGeoJSON(boundary)::json AS boundary, ST_Y(location) AS lat, ST_X(location) AS lon
           FROM fields WHERE id = %s""",
        (field_id,),
    ).fetchone()
    if f is None:
        raise ValueError("field not found")
    seasons = conn.execute(
        """SELECT id::text, year, season, crop, crop_confidence, crop_status, crop_confirmed_by_farmer, variety,
                  sowing_date, peak_date, harvest_date, date_detection, in_progress, yield_low_t_ha,
                  yield_mid_t_ha, yield_high_t_ha, yield_is_forecast, yield_method, shap_reasons
           FROM seasons WHERE field_id = %s ORDER BY sowing_date""",
        (field_id,),
    ).fetchall()
    events = conn.execute(
        """SELECT e.event_type, e.start_date, e.end_date, e.severity, e.origin, e.evidence, s.year, s.season, s.crop
           FROM events e LEFT JOIN seasons s ON s.id = e.season_id
           WHERE e.field_id = %s ORDER BY e.start_date""",
        (field_id,),
    ).fetchall()
    sources = conn.execute(
        "SELECT unnest(sources) AS src, count(*) AS n FROM field_timeseries WHERE field_id = %s GROUP BY 1",
        (field_id,),
    ).fetchall()
    span = conn.execute("SELECT min(date) AS a, max(date) AS b FROM field_timeseries WHERE field_id = %s",
                        (field_id,)).fetchone()
    return {"field": f, "seasons": seasons, "events": events, "sources": {r["src"]: r["n"] for r in sources},
            "period": span}


def render_pdf(conn, field_id: str) -> tuple[bytes, str]:
    from weasyprint import HTML

    data = build_report_data(conn, field_id)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    ts = load_timeseries(conn, field_id)
    html = _env.get_template("report.html").render(
        **data,
        ndvi_svg=_svg_ndvi(ts, data["seasons"]),
        boundary_svg=_svg_boundary(data["field"]["boundary"]),
        generated=datetime.now(UTC).strftime("%d %b %Y %H:%M UTC"),
        digest=digest,
        today=date.today(),  # noqa: DTZ011 - local calendar day
    )
    return HTML(string=html).write_pdf(), digest
