"""Government scheme finder (feature 8)."""
from datetime import date

from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.deps import db
from app.services import schemes

router = APIRouter(prefix="/api", tags=["schemes"])


@router.get("/schemes")
def my_schemes(conn=Depends(db), user=Depends(current_user)):
    p = schemes.profile(conn, user["id"], user["mode"] != "supabase")
    return {"profile": p, "schemes": schemes.match(schemes.load(), p, date.today()),  # noqa: DTZ011
            "note": "Benefits and rules change. Always confirm on the official website or at your Rythu Seva Kendra."}
