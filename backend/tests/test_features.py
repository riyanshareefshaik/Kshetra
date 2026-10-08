# ruff: noqa: DTZ011 - the app uses the local calendar day, so the tests do too
"""API tests for weather alerts, irrigation, pests, fertilizer, market, claims, schemes, groups and login."""
import io
from datetime import date, timedelta

import jwt
import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.ml.fertilizer import calculate, rate
from app.services import forecast, market
from app.services.ocr import parse_soil_card


def fake_forecast(lat, lon):
    today = date.today()
    days = [today + timedelta(days=i) for i in range(-7, 7)]
    n = len(days)
    hours = [f"{d.isoformat()}T{h:02d}:00" for d in days for h in range(24)]
    return {"daily": {"time": [d.isoformat() for d in days], "precipitation_sum": [0.0] * 8 + [90.0] + [0.0] * 5,
                      "precipitation_probability_max": [10] * n, "temperature_2m_max": [33.0] * n,
                      "temperature_2m_min": [23.0] * n, "wind_speed_10m_max": [8.0] * n,
                      "et0_fao_evapotranspiration": [5.0] * n},
            "hourly": {"time": hours, "relative_humidity_2m": [95] * len(hours), "temperature_2m": [23.0] * len(hours)}}


@pytest.fixture
def conn(db_url):
    with psycopg.connect(db_url, row_factory=dict_row) as c:
        yield c


def test_today_alerts_pests_and_irrigation(client, monkeypatch):
    monkeypatch.setattr(forecast, "fetch_forecast", fake_forecast)
    fid = client.ids[0]
    sow = (date.today() - timedelta(days=40)).isoformat()
    r = client.get(f"/api/fields/{fid}/today", params={"crop": "maize", "sowing_date": sow})
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out["days"]) == 14
    assert any(a["type"] == "heavy_rain" for a in out["alerts"])
    assert {p["pest"] for p in out["pests"]} == {"Fall armyworm", "Turcicum leaf blight"}
    assert out["irrigation"]["crop"] == "maize" and out["irrigation"]["status"] in {"ok", "irrigate_soon", "irrigate_now"}
    no_crop = client.get(f"/api/fields/{fid}/today").json()
    assert no_crop["irrigation"]["status"] in {"no_crop", "paddy", "ok", "irrigate_soon", "irrigate_now", "harvested"}


def test_fertilizer_ratings_and_products():
    assert rate("n", 250) == "low" and rate("p", 18) == "medium" and rate("k", 300) == "high"
    std = calculate("paddy", (120, 60, 40), None, 1.0)
    assert std["dose"] == {"n_kg_ha": 120, "p2o5_kg_ha": 60, "k2o_kg_ha": 40}
    prods = {p["product"]: p for p in std["products"]}
    assert prods["DAP"]["kg_per_ha"] == 130 and prods["UREA"]["kg_per_ha"] == 210 and prods["MOP"]["kg_per_ha"] == 67
    assert prods["DAP"]["bags"] == 3.0 and std["notes"][0]["code"] == "no_soil_test"
    adj = calculate("paddy", (120, 60, 40), {"n_kg_ha": 250, "p_kg_ha": 30, "k_kg_ha": 150, "zn_ppm": 0.4, "ph": 8.8}, 2.0)
    assert adj["dose"] == {"n_kg_ha": 150, "p2o5_kg_ha": 45, "k2o_kg_ha": 40}
    assert {n["code"] for n in adj["notes"]} == {"zinc_low", "alkaline"}


def test_soil_card_text_parsing():
    text = """SOIL HEALTH CARD
    pH 7.9   EC 0.45 dS/m   Organic Carbon (OC) 0.42 %
    Available Nitrogen (N) 212 kg/ha
    Available Phosphorus (P) 18.5 kg/ha
    Available Potassium (K) 310 kg/ha
    Zinc (Zn) 0.52 ppm"""
    assert parse_soil_card(text) == {"n_kg_ha": 212.0, "p_kg_ha": 18.5, "k_kg_ha": 310.0, "ph": 7.9,
                                     "oc_pct": 0.42, "ec_ds_m": 0.45, "zn_ppm": 0.52}


def test_soil_test_api_and_fertilizer_endpoint(client):
    fid = client.ids[1]
    r = client.post(f"/api/fields/{fid}/soil-tests", json={"n_kg_ha": 250, "p_kg_ha": 30, "k_kg_ha": 150})
    assert r.status_code == 201
    out = client.get(f"/api/fields/{fid}/fertilizer", params={"crop": "paddy", "season": "kharif"}).json()
    assert out["ratings"] == {"n": "low", "p": "high", "k": "medium"} and out["dose"]["n_kg_ha"] == 150
    assert out["soil_test_date"] and out["total_cost_rs"] > 0
    assert client.get(f"/api/fields/{fid}/fertilizer", params={"crop": "banana", "season": "kharif"}).status_code == 404

    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1500, 600), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 42)
    except OSError:
        font = ImageFont.load_default(size=42)
    for i, line in enumerate(["Available Nitrogen (N) 212 kg/ha", "Available Phosphorus (P) 18 kg/ha",
                              "Available Potassium (K) 310 kg/ha", "pH 7.9"]):
        d.text((40, 40 + i * 110), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = client.post(f"/api/fields/{fid}/soil-tests/card", files={"image": ("card.png", buf.getvalue(), "image/png")})
    assert r.status_code == 201, r.text
    assert r.json()["values"]["n_kg_ha"] == 212 and r.json()["saved"]["source"] == "soil_health_card"
    assert len(client.get(f"/api/fields/{fid}/soil-tests").json()) == 2


def test_market_trend_mandis_and_seasonality(client, conn, monkeypatch):
    monkeypatch.setattr(market, "geocode", lambda m, d, s: {"lat": 16.5, "lon": 80.6 + 0.1 * len(m) / 10})
    today = date.today()
    rows = []
    for back in range(0, 400, 3):
        day = today - timedelta(days=back)
        price = 2300 + (200 if day.month in (3, 4) else 0) + (150 if back < 28 else 0)
        rows.append((day, "Andhra Pradesh", "Krishna", "Vijayawada", "Paddy(Dhan)(Common)", "", price, price, price))
        rows.append((day, "Andhra Pradesh", "Guntur", "Tenali", "Paddy(Dhan)(Common)", "", price + 50, price + 50, price + 50))
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO mandi_prices VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", rows)
    conn.commit()
    out = client.get(f"/api/fields/{client.ids[0]}/market", params={"crop": "paddy"}).json()
    assert len(out["trend"]) >= 50 and out["markets"][0]["market"] == "Tenali"
    assert all(m["distance_km"] is not None for m in out["markets"])
    assert out["reference"]["source"].startswith("Agmarknet")
    text = " ".join(a["text"] for a in out["advice"])
    assert "rising" in text and "Best nearby option" in text
    if today.month not in (3, 4):
        assert "usually highest in" in text


def test_claims_flood_and_post_harvest(client, conn):
    fid = client.ids[2]
    season = conn.execute("SELECT id, harvest_date FROM seasons WHERE field_id = %s AND harvest_date IS NOT NULL "
                          "ORDER BY harvest_date DESC LIMIT 1", (fid,)).fetchone()
    start = date.today() - timedelta(days=1)
    conn.execute("""INSERT INTO events (field_id, season_id, event_type, start_date, end_date, severity, origin, evidence)
                    VALUES (%s, %s, 'flood', %s, %s, 0.8, 'detected', %s)""",
                 (fid, season["id"], start, start, Jsonb({"max_rain_3day_mm": 180, "radar_standing_water": True})))
    h = season["harvest_date"]
    conn.execute("UPDATE field_timeseries SET rainfall_mm = 40 WHERE field_id = %s AND date BETWEEN %s AND %s",
                 (fid, h + timedelta(days=3), h + timedelta(days=5)))
    conn.commit()
    out = client.get(f"/api/fields/{fid}/claims").json()
    kinds = {c["kind"] for c in out["claims"]}
    assert {"localised", "post_harvest"} <= kinds and out["helpline"] == "14447"
    flood = next(c for c in out["claims"] if c["kind"] == "localised" and c["start_date"] == start.isoformat())
    assert flood["open"] and 0 < flood["hours_left"] <= 72
    pdf = client.get(f"/api/fields/{fid}/claims/{flood['id']}.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"/api/fields/{fid}/claims/nope.pdf").status_code == 404


def test_schemes_match_profile(client):
    out = client.get("/api/schemes").json()
    ids = {s["id"] for s in out["schemes"]}
    assert {"pm_kisan", "pmfby", "kcc", "enam", "ap_annadata_sukhibhava", "pmksy_pdmc"} <= ids
    assert out["schemes"][0]["level"] == "state"
    assert all(s["link"].startswith("https://") and s["why"] for s in out["schemes"])


def test_groups_dashboard_and_sharing(client, conn):
    g = client.post("/api/groups", json={"name": "Kankipadu FPO", "district": "Testdistrict"}).json()
    assert g["role"] == "admin" and len(g["join_code"]) == 6
    owners = [r["owner_id"] for r in conn.execute("SELECT owner_id FROM fields ORDER BY name LIMIT 3").fetchall()]
    for i, o in enumerate(owners):
        conn.execute("INSERT INTO group_members (group_id, user_id, share_with_group) VALUES (%s, %s, %s)",
                     (g["id"], o, i < 2))
    conn.commit()
    d = client.get(f"/api/groups/{g['id']}/dashboard").json()
    assert d["members"] == 4 and d["members_sharing"] == 3 and len(d["fields"]) == 2
    assert d["yields"] and d["area_ha"] > 1
    assert client.post("/api/groups/join", json={"code": "ZZZZZZ"}).status_code == 404
    assert client.put(f"/api/groups/{g['id']}/share", json={"share_with_group": False}).json()["share_with_group"] is False
    assert client.delete(f"/api/groups/{g['id']}/members/me").status_code == 204
    assert client.get(f"/api/groups/{g['id']}/dashboard").status_code == 404


def test_login_mode_isolates_farmers(client, monkeypatch):
    from app.config import get_settings
    secret = "unit-test-secret-unit-test-secret!!"
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    get_settings.cache_clear()
    try:
        def hdr(sub):
            tok = jwt.encode({"sub": sub, "aud": "authenticated", "email": f"{sub}@example.in"}, secret, algorithm="HS256")
            return {"Authorization": f"Bearer {tok}"}
        assert client.get("/api/fields").status_code == 401
        poly = {"type": "Polygon", "coordinates": [[[80.7, 16.4], [80.701, 16.4], [80.701, 16.401], [80.7, 16.401], [80.7, 16.4]]]}
        mine = client.post("/api/fields", json={"name": "A's field", "boundary": poly, "start_ingest": False}, headers=hdr("a"))
        assert mine.status_code == 201
        fid = mine.json()["id"]
        assert [f["id"] for f in client.get("/api/fields", headers=hdr("a")).json()] == [fid]
        assert client.get("/api/fields", headers=hdr("b")).json() == []
        assert client.get(f"/api/fields/{fid}", headers=hdr("b")).status_code == 404
        assert client.get(f"/api/fields/{client.ids[0]}", headers=hdr("a")).status_code == 404
        me = client.get("/api/users/me", headers=hdr("a")).json()
        assert me["email"] == "a@example.in" and me["auth_mode"] == "supabase"
        assert client.delete(f"/api/fields/{fid}", headers=hdr("a")).status_code == 204
    finally:
        get_settings.cache_clear()
