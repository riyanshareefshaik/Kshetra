"""Layer 4 semantic memory: embeddings of diary notes and past Q&A in pgvector.

Embeddings come from the open-source multilingual model
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (Apache 2.0,
384 dims, Telugu/Hindi/English), run locally. The model is optional
(requirements-ai.txt): without it, notes are still saved in their own tables
and search falls back to plain text matching.
"""
import logging
from functools import lru_cache

from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMS = 384

_embedder_override = None   # tests set a fake embedder here


@lru_cache(maxsize=1)
def _model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.info("sentence-transformers not installed; semantic memory uses text search")
        return None
    try:
        return SentenceTransformer(MODEL_NAME)
    except Exception as exc:  # noqa: BLE001 - offline without a cached model
        log.warning("could not load %s: %s", MODEL_NAME, exc)
        return None


def embed(text: str) -> list[float] | None:
    if _embedder_override is not None:
        return _embedder_override(text)
    model = _model()
    if model is None:
        return None
    return [round(float(x), 6) for x in model.encode(text, normalize_embeddings=True)]


def remember(conn, *, field_id: str | None, owner_id: str | None, kind: str, source_id: str | None,
             content: str, language: str | None, metadata: dict | None = None) -> bool:
    vec = embed(content)
    if vec is None:
        return False
    conn.execute(
        """INSERT INTO semantic_memory (field_id, owner_id, kind, source_id, content, language, embedding, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (field_id, owner_id, kind, source_id, content, language, str(vec), Jsonb(metadata or {})),
    )
    return True


def search(conn, field_id: str, query: str, limit: int = 5) -> list[dict]:
    vec = embed(query)
    if vec is not None:
        rows = conn.execute(
            """SELECT kind, content, language, created_at::date AS date,
                      round((1 - (embedding <=> %s::vector))::numeric, 3) AS similarity
               FROM semantic_memory WHERE field_id = %s
               ORDER BY embedding <=> %s::vector LIMIT %s""",
            (str(vec), field_id, str(vec), limit),
        ).fetchall()
        hits = [r for r in rows if r["similarity"] >= 0.3]
        if hits:
            return [{**r, "date": r["date"].isoformat(), "similarity": float(r["similarity"])} for r in hits]
    # Text fallback over the diary itself.
    patterns = [f"%{w}%" for w in (w for w in query.split() if len(w) > 2)] or [f"%{query}%"]
    rows = conn.execute(
        """SELECT 'diary' AS kind, coalesce(text_en, raw_text) AS content, language, entry_date AS date
           FROM diary_entries WHERE field_id = %s
             AND (raw_text ILIKE ANY(%s) OR coalesce(text_en, '') ILIKE ANY(%s))
           ORDER BY entry_date DESC LIMIT %s""",
        (field_id, patterns, patterns, limit),
    ).fetchall()
    return [{**r, "date": r["date"].isoformat()} for r in rows]
