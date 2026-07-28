"""Rule-based classifier for coneva PDF documents.

The ruleset was derived from and verified against the sample set
(29 invoices + 49 Gutschriften). Markers are mutually exclusive between
categories; invoice subtypes are decided by the energy line items.

Detection markers
-----------------
Category:
  GUTSCHRIFT : "Gutschrift gemäß Vertrag zur Stromvermarktung"
  INVOICE    : "Verbrauchsabrechnung für Ihre Stromlieferung"

Invoice subtype (energy line items):
  TARIF_ONLY        : "EPEX SPOT Preis"
  OPTIMIZATION_ONLY : "coneva Flex Preis" AND NOT "coneva Profit Share"
  COMBINED          : "coneva Flex Preis" AND "coneva Profit Share"
  FIXPRICE          : "coneva Fix Preis"
"""

from __future__ import annotations

import io
import re

from .models import (
    Category,
    ClassifiedDocument,
    DocumentFields,
    InvoiceSubtype,
)

# --- Category markers -------------------------------------------------------
_MARKER_GUTSCHRIFT = "Gutschrift gemäß Vertrag zur Stromvermarktung"
_MARKER_INVOICE = "Verbrauchsabrechnung für Ihre Stromlieferung"

# --- Invoice subtype markers (energy line items) ----------------------------
_MARKER_TARIF = "EPEX SPOT Preis"
_MARKER_FLEX = "coneva Flex Preis"
_MARKER_PROFIT_SHARE = "coneva Profit Share"
_MARKER_FIXPRICE = "coneva Fix Preis"


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract text from all pages. Imported lazily to keep import cheap."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _detect_category(text: str) -> Category:
    if _MARKER_GUTSCHRIFT in text:
        return Category.GUTSCHRIFT
    if _MARKER_INVOICE in text:
        return Category.INVOICE
    return Category.UNKNOWN


def _detect_invoice_subtype(text: str) -> InvoiceSubtype:
    if _MARKER_FIXPRICE in text:
        return InvoiceSubtype.FIXPRICE
    if _MARKER_FLEX in text:
        if _MARKER_PROFIT_SHARE in text:
            return InvoiceSubtype.COMBINED
        return InvoiceSubtype.OPTIMIZATION_ONLY
    if _MARKER_TARIF in text:
        return InvoiceSubtype.TARIF_ONLY
    return InvoiceSubtype.UNKNOWN


def _first(text: str, label: str) -> str | None:
    """Grab the value after 'Label:' on the same line."""
    m = re.search(rf"{re.escape(label)}:\s*(.+)", text)
    if not m:
        return None
    value = m.group(1).strip()
    return value or None


def _parse_amount_de(raw: str) -> float | None:
    """German number '6.693,67' -> 6693.67."""
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _extract_customer_name(text: str) -> str | None:
    """Recipient name = first non-empty line after the coneva sender line.

    Both templates print a single-line sender footer
    'coneva GmbH | <street> | <zip> München' immediately before the
    recipient address block.
    """
    m = re.search(r"coneva GmbH \|[^\n]*M(?:ü|ue)nchen[^\n]*\n", text)
    if not m:
        return None
    tail = text[m.end():]
    for line in tail.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return None


def _extract_fields(text: str, category: Category) -> DocumentFields:
    location = _first(text, "Verbrauchsstelle") or _first(text, "Standort der Anlage")

    amount = None
    # Invoice: 'Rechnungsbetrag ... 183,24 EUR'; Gutschrift: 'Gutschrift ... EUR'
    label = "Rechnungsbetrag" if category is Category.INVOICE else "Gutschrift"
    m = re.search(rf"{label}\s+([\d.]+,\d{{2}})\s*EUR", text)
    if m:
        amount = _parse_amount_de(m.group(1))

    return DocumentFields(
        rechnungsnummer=_first(text, "Rechnungsnummer"),
        rechnungsdatum=_first(text, "Rechnungsdatum"),
        leistungszeitraum=_first(text, "Leistungszeitraum"),
        kundennummer=_first(text, "Kundennummer"),
        marktlokation=_first(text, "Marktlokation"),
        netzbetreiber=_first(text, "Netzbetreiber"),
        location=location,
        customer_name=_extract_customer_name(text),
        amount_eur=amount,
    )


def classify_pdf_text(text: str, filename: str) -> ClassifiedDocument:
    """Classify from already-extracted text (unit-test friendly)."""
    warnings: list[str] = []

    category = _detect_category(text)
    if category is Category.UNKNOWN:
        warnings.append("No known category marker found (not an invoice or Gutschrift).")

    subtype: InvoiceSubtype | None = None
    if category is Category.INVOICE:
        subtype = _detect_invoice_subtype(text)
        if subtype is InvoiceSubtype.UNKNOWN:
            warnings.append("Invoice with no recognized energy line item; subtype UNKNOWN.")

    fields = _extract_fields(text, category)
    if category is not Category.UNKNOWN and not fields.rechnungsnummer:
        warnings.append("Could not extract Rechnungsnummer.")

    return ClassifiedDocument(
        filename=filename,
        category=category,
        subtype=subtype,
        fields=fields,
        warnings=warnings,
    )


def classify_pdf(pdf_bytes: bytes, filename: str) -> ClassifiedDocument:
    """Classify a PDF given its raw bytes and original filename."""
    try:
        text = _extract_text(pdf_bytes)
    except Exception as exc:  # noqa: BLE001 - surface as an UNKNOWN doc, don't crash
        return ClassifiedDocument(
            filename=filename,
            category=Category.UNKNOWN,
            warnings=[f"Failed to read PDF text: {exc}"],
        )
    return classify_pdf_text(text, filename)
