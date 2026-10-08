"""End-to-end API tests on synthetic fields (no network, no keys)."""
import io
import json
import time

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.services import memory


@pytest.fixture(scope="module")
def client(db_url, monkeypatch_module):
    monkeypatch_module.setenv("DATABASE_URL", db_url)
    monkeypatch_module.setenv("LLM_PROVIDER_ORDER", "fake")
    monkeypatch_module.setenv("GEE_PROJECT", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from scripts.seed_synthetic import seed
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        ids = seed(conn, 6)
    from app.main import app
    with TestClient(app) as c:
        c.ids = ids
        yield c
    with psycopg.connect(db_url) as conn:
        conn.execute("TRUNCATE users, fields, api_cache, district_yields, crop_varieties CASCADE")
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def kharif_season(client, fid, year=2023):
    return next(s for s in client.get(f"/api/fields/{fid}/seasons").json()
                if s["season"] == "kharif" and s["year"] == year)


def test_health_and_fields(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    fields = client.get("/api/fields").json()
    assert len(fields) == 6 and all(f["is_synthetic"] for f in fields)
    f = client.get(f"/api/fields/{client.ids[0]}").json()
    assert f["boundary"]["type"] == "Polygon" and f["area_ha"] > 0.5
    assert client.get("/api/fields/not-a-uuid").status_code == 404
    assert client.get("/api/fields/00000000-0000-0000-0000-000000000000").status_code == 404


def test_create_update_delete_field(client):
    poly = {"type": "Polygon", "coordinates": [[[80.70, 16.40], [80.701, 16.40], [80.701, 16.401],
                                                 [80.70, 16.401], [80.70, 16.40]]]}
    r = client.post("/api/fields", json={"name": "Drawn", "boundary": poly, "start_ingest": False})
    assert r.status_code == 201 and r.json()["boundary_source"] == "drawn"
    fid = r.json()["id"]
    pin = client.post("/api/fields", json={"lat": 16.5, "lon": 80.6, "start_ingest": False}).json()
    assert pin["boundary_source"] == "pin_buffer" and 0.7 < pin["area_ha"] < 0.9
    bad = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    assert client.post("/api/fields", json={"boundary": bad}).status_code == 422
    assert client.post("/api/fields", json={"name": "nothing"}).status_code == 422
    r = client.patch(f"/api/fields/{fid}", json={"irrigation_type": "borewell", "name": "Renamed"})
    assert r.json()["irrigation_type"] == "borewell" and r.json()["name"] == "Renamed"
    assert client.delete(f"/api/fields/{fid}").status_code == 204
    assert client.delete(f"/api/fields/{pin['id']}").status_code == 204


def test_auto_boundary_falls_back_without_earth_engine(client):
    r = client.post("/api/fields/auto-boundary", json={"lat": 16.44, "lon": 80.78}).json()
    assert r["boundary_source"] == "pin_buffer" and "square" in r["note"]


def test_timeseries_steps_and_rain_sums(client):
    rows = client.get(f"/api/fields/{client.ids[0]}/timeseries",
                      params={"start": "2023-07-01", "end": "2023-07-31", "step": 7}).json()
    steps = [r for r in rows if r["is_step"]]
    assert 3 <= len(steps) <= 5
    assert all(abs(r["rain_step_mm"] - 56.0) < 1e-6 for r in steps)     # 7 days x 8 mm
    assert any(r["ndvi"] is not None for r in rows)


def test_seasons_why_twins_and_confirm(client):
    s = kharif_season(client, client.ids[0])
    assert s["crop"] == "paddy" and s["crop_status"] == "confident"
    assert s["yield_low_t_ha"] < s["yield_mid_t_ha"] < s["yield_high_t_ha"]
    why = client.get(f"/api/seasons/{s['id']}/why").json()
    assert why["method"] == "baseline" and "not proven causes" in why["note"]
    twins = client.get(f"/api/seasons/{s['id']}/twins").json()
    assert len(twins["twins"]) == 5 and all("field_id" not in t for t in twins["twins"])
    r = client.patch(f"/api/seasons/{s['id']}", json={"crop": "maize", "variety": "Hybrid"}).json()
    assert r["crop"] == "maize" and r["crop_confirmed_by_farmer"] and r["crop_confidence"] == 1.0
    assert client.patch(f"/api/seasons/{s['id']}", json={"crop": "banana"}).status_code == 422
    client.patch(f"/api/seasons/{s['id']}", json={"crop": "paddy"})
    events = client.get(f"/api/fields/{client.ids[0]}/events").json()
    assert all(e["event_type"] for e in events)


def test_what_if_is_fast_and_responds_to_inputs(client):
    fid = client.ids[1]
    body = {"crop": "paddy", "season": "kharif", "sowing_date": "07-10", "n_kg_ha": 120, "irrigation": "full"}
    t0 = time.perf_counter()
    r = client.post(f"/api/fields/{fid}/what-if", json=body)
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    res = r.json()
    assert elapsed < 1.0, f"what-if took {elapsed:.2f}s"
    y = res["yield_t_ha"]
    assert 0 < y["low"] <= y["mid"] <= y["high"]
    assert res["profit"]["price"]["source"].startswith("MSP 2026-27")
    assert res["profit"]["low_rs_ha"] <= res["profit"]["mid_rs_ha"] <= res["profit"]["high_rs_ha"]
    assert res["risk"]["level"] in ("low", "medium", "high")
    low_n = client.post(f"/api/fields/{fid}/what-if", json={**body, "n_kg_ha": 20}).json()
    assert low_n["yield_t_ha"]["mid"] < y["mid"]
    rabi = {"crop": "paddy", "season": "rabi", "sowing_date": "12-15", "n_kg_ha": 150}
    dry = client.post(f"/api/fields/{fid}/what-if", json={**rabi, "irrigation": "rainfed"}).json()
    wet = client.post(f"/api/fields/{fid}/what-if", json={**rabi, "irrigation": "full"}).json()
    assert dry["yield_t_ha"]["mid"] < wet["yield_t_ha"]["mid"] and dry["risk"]["level"] == "high"
    assert client.post(f"/api/fields/{fid}/what-if", json={**body, "sowing_date": "02-31"}).status_code == 422
    assert client.post(f"/api/fields/{fid}/what-if", json={**body, "crop": "wheat"}).status_code == 404


def test_planner_top_three(client):
    r = client.get(f"/api/fields/{client.ids[0]}/plan", params={"season": "rabi"}).json()
    opts = r["options"]
    assert 1 <= len(opts) <= 3
    scores = [o["score"] for o in opts if o.get("score") is not None]
    assert scores == sorted(scores, reverse=True)
    assert all("sowing_window" in o and "yield_t_ha" in o for o in opts)


def fake_provider(script):
    """Provider that follows a script of replies (tool calls, then text)."""
    state = {"i": 0}

    def chat(_client, messages):
        reply = script[min(state["i"], len(script) - 1)]
        state["i"] += 1
        return reply
    return chat


def test_ask_grounded_answer_saved_to_memory(client, db_url, monkeypatch):
    from app.services import llm
    monkeypatch.setattr(memory, "_embedder_override", lambda text: [0.01 * (len(text) % 7 + 1)] * 384)
    script = [{"content": "", "tool_calls": [{"id": "1", "name": "get_yield_explanation",
                                              "args": {"year": 2023, "season": "kharif"}}]},
              {"content": "Kharif 2023 paddy yield was likely 4.5-5.6 t/ha (get_yield_explanation).",
               "tool_calls": []}]
    monkeypatch.setattr(llm, "PROVIDERS", {"fake": fake_provider(script)})
    r = client.post(f"/api/fields/{client.ids[0]}/ask", json={"question": "How was my 2023 kharif yield?",
                                                               "language": "en"}).json()
    assert r["answered"] and r["provider"] == "fake"
    assert r["sources"][0]["tool"] == "get_yield_explanation" and r["sources"][0]["data"]["crop"] == "paddy"
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        assert conn.execute("SELECT count(*) AS n FROM semantic_memory WHERE kind = 'qa'").fetchone()["n"] >= 1
    hist = client.get(f"/api/fields/{client.ids[0]}/ask/history").json()
    assert hist[0]["question"] == "How was my 2023 kharif yield?"


def test_ask_without_tools_says_i_dont_know(client, monkeypatch):
    from app.services import llm
    monkeypatch.setattr(llm, "PROVIDERS", {"fake": fake_provider([{"content": "Yields are 9 t/ha.", "tool_calls": []}])})
    r = client.post(f"/api/fields/{client.ids[0]}/ask", json={"question": "ఎంత దిగుబడి?", "language": "te"}).json()
    assert not r["answered"] and r["answer"] == llm.DONT_KNOW["te"]
    monkeypatch.setattr(llm, "PROVIDERS", {})
    r = client.post(f"/api/fields/{client.ids[0]}/ask", json={"question": "anything", "language": "hi"}).json()
    assert not r["answered"] and r["answer"].startswith(llm.DONT_KNOW["hi"])


def test_tools_cannot_reach_other_fields(client):
    from app.db.session import get_conn
    from app.services.llm_tools import call_tool
    with get_conn() as conn:
        out = call_tool(conn, client.ids[0], "get_field_summary", {"field_id": client.ids[1]})
    assert "error" in out and "bad arguments" in out["error"]


def test_diary_text_entry_parsed_and_searchable(client):
    fid = client.ids[2]
    r = client.post(f"/api/fields/{fid}/diary", data={"text": "ఈరోజు 3 బస్తాల యూరియా వేశాను, ఖర్చు 800 రూపాయలు",
                                                      "language": "te", "entry_date": "2025-08-05"})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["activity_type"] == "fertilizer"
    assert e["structured"] == {"activity_type": "fertilizer", "product": "urea", "quantity": 3.0, "unit": "bag",
                               "cost_rs": 800.0, "quantity_kg": 135.0}
    entries = client.get(f"/api/fields/{fid}/diary").json()
    assert len(entries) == 2
    from app.db.session import get_conn
    from app.services.llm_tools import call_tool
    with get_conn() as conn:
        hits = call_tool(conn, fid, "search_diary", {"query": "యూరియా"})["matches"]
    assert hits and ("యూరియా" in hits[0]["content"] or "urea" in hits[0]["content"].lower())
    assert client.post(f"/api/fields/{fid}/diary", data={"text": "  "}).status_code == 422


def test_seed_packet_ocr(client):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1400, 700), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 44)
    except OSError:
        font = ImageFont.load_default(size=44)
    lines = ["TRUTHFULLY LABELLED SEED", "Kind: Paddy", "Variety: BPT 5204", "Lot No: AP-24-1187",
             "Date of Test: 12/05/2025", "Valid upto: 11/02/2026", "Germination: 85%", "Net Wt: 25 kg"]
    for i, line in enumerate(lines):
        d.text((40, 30 + i * 80), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = client.post("/api/seed-packet", files={"image": ("packet.png", buf.getvalue(), "image/png")},
                    data={"field_id": client.ids[3]})
    assert r.status_code == 200, r.text
    p = r.json()["seed_packet"]
    assert p["variety"].startswith("BPT 5204") and p["lot_no"] == "AP-24-1187"
    assert p["germination_pct"] == 85 and p["valid_upto"] == "11/02/2026"
    assert r.json()["diary_entry_id"]


def test_voice_without_engines_is_503(client, monkeypatch):
    from app.services import voice
    monkeypatch.setattr(voice, "whisper_asr", lambda *a, **k: (_ for _ in ()).throw(voice.VoiceError("not installed")))
    r = client.post("/api/voice/transcribe", files={"audio": ("a.wav", b"RIFF0000WAVE", "audio/wav")},
                    data={"language": "te"})
    assert r.status_code == 503


def test_report_pdf(client):
    r = client.get(f"/api/fields/{client.ids[0]}/report.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert len(r.headers["x-report-sha256"]) == 64
    assert "attachment" in r.headers["content-disposition"]


def test_consent_and_insights(client):
    demo = client.get("/api/users/demo").json()
    assert demo["data_sharing_consent"] is False                     # off by default
    on = client.put(f"/api/users/{demo['id']}/consent", json={"data_sharing_consent": True}).json()
    assert on["data_sharing_consent"] is True and on["consent_updated_at"]
    ins = client.get("/api/insights", params={"crop": "paddy"}).json()
    assert ins["min_group_size"] == 5 and ins["groups"]
    g = ins["groups"][0]
    assert g["n_fields"] >= 5 and set(g) >= {"district", "crop", "avg_yield_mid_t_ha"}
    assert not ({"field_id", "owner_id", "lat", "lon", "boundary"} & set(g))
    client.put(f"/api/users/{demo['id']}/consent", json={"data_sharing_consent": False})


def test_crop_varieties_loaded(client):
    rows = client.get("/api/crop-varieties", params={"season": "kharif"}).json()
    assert {r["crop"] for r in rows} >= {"paddy", "cotton", "maize"}
    json.dumps(rows)
