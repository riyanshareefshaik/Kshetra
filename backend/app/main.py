"""Kshetra API: field history from space, yield reasons and next-season guidance."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    advisory,
    ask,
    claims,
    diary,
    fertilizer,
    fields,
    groups,
    market,
    planning,
    report,
    schemes,
    seasons,
    users,
    voice,
)
from app.config import get_settings
from app.db.seeds import load_crop_varieties
from app.db.session import db_ok, get_conn

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kshetra")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        with get_conn() as conn:
            n = load_crop_varieties(conn, only_if_empty=True)
            if n:
                log.info("loaded %d crop varieties", n)
    except Exception as exc:  # noqa: BLE001 - the API still starts (e.g. to report /health) without a DB
        log.warning("startup seed skipped: %s", exc)
    yield


app = FastAPI(
    title="Kshetra API",
    description="Rebuilds a field's seasonal history from free satellite data and guides the next season.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Report-SHA256", "Content-Disposition"],
)
for module in (fields, seasons, planning, ask, diary, voice, report, users, advisory, fertilizer, market, claims,
               schemes, groups):
    app.include_router(module.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": "ok" if db_ok() else "unreachable"}
