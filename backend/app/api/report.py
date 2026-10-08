"""F12 one-click field health report PDF."""
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import db, field_or_404
from app.services.report_pdf import render_pdf

router = APIRouter(prefix="/api", tags=["report"])


@router.get("/fields/{field_id}/report.pdf")
def report(field_id: str, conn=Depends(db)):
    f = field_or_404(conn, field_id)
    pdf, digest = render_pdf(conn, field_id)
    name = "".join(c if c.isalnum() else "-" for c in (f["name"] or "field")).strip("-").lower() or "field"
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="kshetra-{name}-report.pdf"', "X-Report-SHA256": digest})
