"""Synthetic fixture builders for tests.

Generates *committable* test data (no real customer info) that reproduces the
text markers the classifier keys on. Minimal PDFs are hand-built (no external
PDF-writer dependency) so tests run anywhere, including CI without WeasyPrint's
native libraries.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from openpyxl import Workbook


# --------------------------------------------------------------------------- #
# Minimal text-extractable PDF (no reportlab / weasyprint needed)
# --------------------------------------------------------------------------- #
def make_pdf(lines: list[str]) -> bytes:
    """Build a one-page PDF whose text (via pypdf) is exactly ``lines``."""
    body = ["BT /F1 10 Tf"]
    y = 780
    for ln in lines:
        esc = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        body.append(f"1 0 0 1 50 {y} Tm ({esc}) Tj")
        y -= 14
    body.append("ET")
    content = "\n".join(body).encode("cp1252", "replace")

    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n"
        + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
    ]

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        b"trailer\n<< /Size "
        + str(len(objs) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref).encode()
        + b"\n%%EOF"
    )
    return out.getvalue()


# --------------------------------------------------------------------------- #
# Document text templates (mirror the real coneva PDFs' markers)
# --------------------------------------------------------------------------- #
def _header_lines(
    *,
    rechnungsnummer: str,
    malo: str,
    kundennummer: str,
    customer: str,
    netzbetreiber: str = "Test Netz GmbH",
    location: str = "Teststraße 1",
) -> list[str]:
    return [
        "coneva GmbH | Paul-Heyse-Straße 2-4 | 80336 München",
        customer,
        location,
        "12345 Teststadt",
        f"Rechnungsdatum: 01.01.2026",
        f"Rechnungsnummer: {rechnungsnummer}",
        "Leistungszeitraum: Januar 2026",
        f"Kundennummer: {kundennummer}",
        f"Marktlokation: {malo}",
        f"Netzbetreiber: {netzbetreiber}",
    ]


def invoice_pdf(
    subtype: str,
    *,
    malo: str,
    kundennummer: str = "6000001",
    customer: str = "Test Kunde GmbH",
    rechnungsnummer: str = "91000001",
) -> bytes:
    """Build an INVOICE PDF for a given subtype.

    subtype in {"TARIF_ONLY","OPTIMIZATION_ONLY","COMBINED","FIXPRICE"}.
    """
    lines = ["Verbrauchsabrechnung für Ihre Stromlieferung"]
    lines += _header_lines(
        rechnungsnummer=rechnungsnummer,
        malo=malo,
        kundennummer=kundennummer,
        customer=customer,
    )
    lines.append("Ihr Stromverbrauch im Detail")
    lines.append("Grundgebühr 10,00 EUR")
    if subtype == "TARIF_ONLY":
        lines.append("EPEX SPOT Preis 100,00 kWh 6,10 ct/kWh")
        lines.append("Managementgebühr 100,00 kWh 1,50 ct/kWh")
    elif subtype == "OPTIMIZATION_ONLY":
        lines.append("coneva Flex Preis 100,00 kWh 8,60 ct/kWh")
        lines.append("Managementgebühr 100,00 kWh 1,00 ct/kWh")
    elif subtype == "COMBINED":
        lines.append("coneva Flex Preis 100,00 kWh 4,28 ct/kWh")
        lines.append("coneva Profit Share 15% 446,12 EUR")
        lines.append("Managementgebühr 100,00 kWh 1,13 ct/kWh")
    elif subtype == "FIXPRICE":
        lines.append("coneva Fix Preis 100,00 kWh 12,00 ct/kWh")
    else:
        raise ValueError(f"unknown subtype {subtype!r}")
    lines.append("Summe Energie 56,06 EUR")
    lines.append("Rechnungsbetrag 183,24 EUR")
    return make_pdf(lines)


def gutschrift_pdf(
    *,
    malo: str,
    kundennummer: str = "6000002",
    customer: str = "Test Erzeuger GmbH",
    rechnungsnummer: str = "92000001",
) -> bytes:
    """Build a GUTSCHRIFT (credit note) PDF."""
    lines = ["Gutschrift gemäß Vertrag zur Stromvermarktung"]
    lines += _header_lines(
        rechnungsnummer=rechnungsnummer,
        malo=malo,
        kundennummer=kundennummer,
        customer=customer,
        location="Standort der Anlage: Zeitlhof 1",
    )
    lines.append("Vermarktete Einspeisemenge 58.931,68 kWh 9,54 ct/kWh")
    lines.append("Gutschrift 6.693,67 EUR")
    return make_pdf(lines)


def unknown_pdf() -> bytes:
    """A PDF that matches no category marker."""
    return make_pdf(["Some unrelated document", "with no known markers"])


# --------------------------------------------------------------------------- #
# Mapping xlsx builder
# --------------------------------------------------------------------------- #
@dataclass
class MappingRow:
    malos: list[str]
    unternehmen: str
    primary_email: str
    kundennummer: str = ""
    cc_email: str = ""
    ceo_email: str = ""


def make_mapping_xlsx(rows: list[MappingRow], sheet: str = "Mapping") -> bytes:
    """Build a mapping workbook in the current MaLo-list format."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(
        [
            "MaLo",
            "Kundennummer",
            "Unternehmen",
            "Primary Email",
            "CC Email (extern)",
            "CEO Email",
        ]
    )
    for r in rows:
        ws.append(
            [
                ", ".join(r.malos),
                r.kundennummer,
                r.unternehmen,
                r.primary_email,
                r.cc_email,
                r.ceo_email,
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
