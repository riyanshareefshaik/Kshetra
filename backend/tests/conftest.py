import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

SCHEMA = Path(__file__).resolve().parents[2] / "database" / "schema.sql"


@pytest.fixture(scope="session")
def db_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set (needs Postgres + PostGIS + pgvector)")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute(SCHEMA.read_text())
    return url


@pytest.fixture
def conn(db_url):
    with psycopg.connect(db_url, row_factory=dict_row) as c:
        yield c
        c.rollback()
        c.execute("TRUNCATE users, fields, api_cache, district_yields, mandi_prices, crop_varieties CASCADE")
        c.commit()


@pytest.fixture(scope="module")
def client(db_url, monkeypatch_module):
    monkeypatch_module.setenv("DATABASE_URL", db_url)
    monkeypatch_module.setenv("LLM_PROVIDER_ORDER", "fake")
    monkeypatch_module.setenv("GEE_PROJECT", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from tests.fixtures import seed
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
