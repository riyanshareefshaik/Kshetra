import os
from pathlib import Path

import psycopg
import pytest
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
        c.execute("TRUNCATE users, fields, api_cache CASCADE")
        c.commit()
