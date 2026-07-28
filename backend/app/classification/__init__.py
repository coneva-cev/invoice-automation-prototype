"""PDF classification package.

Classifies uploaded coneva PDF documents into a category (invoice vs.
Gutschrift/credit note) and, for invoices, a subtype (tarif-only,
optimization-only, combined, fixprice). Produces an internal
``ClassifiedDocument`` object that later steps (validation, portal upload,
email dispatch) branch on.
"""

from .models import (
    Category,
    ClassifiedDocument,
    InvoiceSubtype,
    DocumentFields,
)
from .classifier import classify_pdf, classify_pdf_text

__all__ = [
    "Category",
    "InvoiceSubtype",
    "DocumentFields",
    "ClassifiedDocument",
    "classify_pdf",
    "classify_pdf_text",
]
