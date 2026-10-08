"""When and where to sell (feature 6)."""
from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.api.deps import db, field_or_404
from app.services.market import market_view

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/fields/{field_id}/market")
def market(field_id: str, crop: str, conn=Depends(db), user=Depends(current_user)):
    return market_view(conn, crop, field_or_404(conn, field_id, user))
