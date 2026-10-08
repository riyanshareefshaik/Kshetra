"""PMFBY claim helper (feature 7)."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.auth import current_user
from app.api.deps import db, field_or_404
from app.services import claims
from app.services.report_pdf import _env

router = APIRouter(prefix="/api", tags=["claims"])


@router.get("/fields/{field_id}/claims")
def list_claims(field_id: str, conn=Depends(db), user=Depends(current_user)):
    field_or_404(conn, field_id, user)
    return {"claims": claims.candidates(conn, field_id), "helpline": claims.HELPLINE, "steps": claims.STEPS,
            "documents": claims.DOCUMENTS}


@router.get("/fields/{field_id}/claims/{claim_id}.pdf")
def claim_pdf(field_id: str, claim_id: str, conn=Depends(db), user=Depends(current_user)):
    from weasyprint import HTML

    field = field_or_404(conn, field_id, user)
    claim = next((c for c in claims.candidates(conn, field_id) if c["id"] == claim_id), None)
    if claim is None:
        raise HTTPException(404, "claim not found")
    html = _env.get_template("claim.html").render(
        claim=claim, field=field, steps=claims.STEPS, documents=claims.DOCUMENTS, helpline=claims.HELPLINE,
        generated=datetime.now(UTC).strftime("%d %b %Y %H:%M UTC"))
    return Response(HTML(string=html).write_pdf(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="pmfby-evidence-{claim["start_date"]}.pdf"'})
