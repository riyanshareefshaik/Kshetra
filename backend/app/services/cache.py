"""Read-through cache of external API responses in the api_cache table.

Every external call goes through `cached()`, so once a field is ingested the
demo runs from Postgres alone. Historical data never expires; data that can
still change (the current year, recent weather) gets a TTL.
"""
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb


def request_key(params: dict) -> str:
    """Stable hash of request parameters (order-independent)."""
    blob = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:40]


def cached(
    conn: psycopg.Connection,
    source: str,
    params: dict,
    fetch: Callable[[], Any],
    ttl: timedelta | None = None,
) -> Any:
    """Return the cached response for (source, params), or call fetch() and store it."""
    key = request_key(params)
    row = conn.execute(
        "SELECT response FROM api_cache WHERE source = %s AND request_key = %s"
        " AND (expires_at IS NULL OR expires_at > now())",
        (source, key),
    ).fetchone()
    if row is not None:
        return row["response"] if isinstance(row, dict) else row[0]

    response = _jsonable(fetch())
    expires = datetime.now(UTC) + ttl if ttl else None
    conn.execute(
        """
        INSERT INTO api_cache (source, request_key, request, response, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (source, request_key) DO UPDATE
           SET response = EXCLUDED.response, fetched_at = now(), expires_at = EXCLUDED.expires_at
        """,
        (source, key, Jsonb(_jsonable(params)), Jsonb(response), expires),
    )
    conn.commit()
    return response


def _jsonable(obj: Any) -> Any:
    """Round-trip through JSON so dates become ISO strings, matching what a cache hit returns."""
    return json.loads(json.dumps(obj, default=str))


def ttl_for_period(end) -> timedelta | None:
    """Data whose period ended over 10 days ago is final; newer data is refreshed daily."""
    end_dt = datetime(end.year, end.month, end.day, tzinfo=UTC)
    if datetime.now(UTC) - end_dt > timedelta(days=10):
        return None
    return timedelta(days=1)
