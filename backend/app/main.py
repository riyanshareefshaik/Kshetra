"""Kshetra API: field history from space, yield reasons and next-season guidance."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.session import db_ok

app = FastAPI(
    title="Kshetra API",
    description="Rebuilds a field's seasonal history from free satellite data and guides the next season.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": "ok" if db_ok() else "unreachable"}
