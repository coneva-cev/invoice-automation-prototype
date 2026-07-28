"""PDF invoice generation endpoints.

STUB: renders a minimal Jinja2 HTML template to PDF via WeasyPrint and
streams it back. Replace the template + data model with the real invoice
layout once finalized.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from app.dependencies.auth import require_permission

router = APIRouter(tags=["pdf"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


class InvoiceLineItem(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0.0

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price


class InvoiceRequest(BaseModel):
    invoice_number: str = "DRAFT-0001"
    customer_name: str = "Sample Customer"
    currency: str = "EUR"
    items: list[InvoiceLineItem] = []


@router.post("/pdf/invoice")
def generate_invoice_pdf(
    payload: InvoiceRequest,
    _: dict = Depends(require_permission("admin")),
) -> Response:
    """Render an invoice PDF from the given data and return it as a download."""
    # Imported lazily so the app can still boot for non-PDF endpoints even if
    # the native WeasyPrint dependencies are not yet installed.
    from weasyprint import HTML

    subtotal = sum(item.total for item in payload.items)

    template = _env.get_template("invoice.html")
    html = template.render(
        invoice=payload,
        subtotal=subtotal,
    )
    pdf_bytes = HTML(string=html).write_pdf()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="invoice-{payload.invoice_number}.pdf"'
            )
        },
    )
