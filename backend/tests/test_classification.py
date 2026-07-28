"""Unit tests for the PDF classification ruleset."""

from __future__ import annotations

import pytest

from app.classification import (
    Category,
    InvoiceSubtype,
    classify_pdf,
    classify_pdf_text,
)

from .factories import gutschrift_pdf, invoice_pdf, make_pdf, unknown_pdf


# --------------------------------------------------------------------------- #
# Category detection
# --------------------------------------------------------------------------- #
def test_invoice_category():
    doc = classify_pdf(invoice_pdf("TARIF_ONLY", malo="50000000001"), "inv.pdf")
    assert doc.category is Category.INVOICE
    assert not doc.needs_review


def test_gutschrift_category():
    doc = classify_pdf(gutschrift_pdf(malo="50000000002"), "gut.pdf")
    assert doc.category is Category.GUTSCHRIFT
    assert doc.subtype is None  # Gutschriften have no invoice subtype
    assert not doc.needs_review


def test_unknown_category_flags_review():
    doc = classify_pdf(unknown_pdf(), "weird.pdf")
    assert doc.category is Category.UNKNOWN
    assert doc.needs_review
    assert doc.warnings


def test_categories_are_mutually_exclusive():
    inv = classify_pdf_text(
        "Verbrauchsabrechnung für Ihre Stromlieferung\nEPEX SPOT Preis", "a"
    )
    gut = classify_pdf_text(
        "Gutschrift gemäß Vertrag zur Stromvermarktung\n"
        "Vermarktete Einspeisemenge",
        "b",
    )
    assert inv.category is Category.INVOICE
    assert gut.category is Category.GUTSCHRIFT


# --------------------------------------------------------------------------- #
# Invoice subtype detection
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "subtype,expected",
    [
        ("TARIF_ONLY", InvoiceSubtype.TARIF_ONLY),
        ("OPTIMIZATION_ONLY", InvoiceSubtype.OPTIMIZATION_ONLY),
        ("COMBINED", InvoiceSubtype.COMBINED),
        ("FIXPRICE", InvoiceSubtype.FIXPRICE),
    ],
)
def test_invoice_subtypes(subtype, expected):
    doc = classify_pdf(invoice_pdf(subtype, malo="50000000003"), "inv.pdf")
    assert doc.category is Category.INVOICE
    assert doc.subtype is expected
    assert not doc.needs_review


def test_combined_requires_both_flex_and_profit_share():
    # Flex present but no Profit Share => OPTIMIZATION_ONLY, not COMBINED
    opt = classify_pdf_text(
        "Verbrauchsabrechnung für Ihre Stromlieferung\nconeva Flex Preis", "a"
    )
    assert opt.subtype is InvoiceSubtype.OPTIMIZATION_ONLY
    both = classify_pdf_text(
        "Verbrauchsabrechnung für Ihre Stromlieferung\n"
        "coneva Flex Preis\nconeva Profit Share",
        "b",
    )
    assert both.subtype is InvoiceSubtype.COMBINED


def test_fixprice_takes_precedence():
    doc = classify_pdf_text(
        "Verbrauchsabrechnung für Ihre Stromlieferung\nconeva Fix Preis", "a"
    )
    assert doc.subtype is InvoiceSubtype.FIXPRICE


def test_invoice_without_energy_line_is_unknown_subtype():
    doc = classify_pdf_text(
        "Verbrauchsabrechnung für Ihre Stromlieferung\n(no energy lines)", "a"
    )
    assert doc.category is Category.INVOICE
    assert doc.subtype is InvoiceSubtype.UNKNOWN
    assert doc.needs_review


# --------------------------------------------------------------------------- #
# Field extraction
# --------------------------------------------------------------------------- #
def test_field_extraction_invoice():
    doc = classify_pdf(
        invoice_pdf(
            "TARIF_ONLY",
            malo="50123456789",
            kundennummer="6009999",
            customer="Musterfirma GmbH",
            rechnungsnummer="91000042",
        ),
        "inv.pdf",
    )
    f = doc.fields
    assert f.marktlokation == "50123456789"
    assert f.kundennummer == "6009999"
    assert f.rechnungsnummer == "91000042"
    assert f.customer_name == "Musterfirma GmbH"
    assert f.amount_eur == 183.24


def test_field_extraction_gutschrift_amount():
    doc = classify_pdf(gutschrift_pdf(malo="50000000009"), "gut.pdf")
    assert doc.fields.amount_eur == 6693.67
    assert doc.fields.customer_name == "Test Erzeuger GmbH"


def test_missing_rechnungsnummer_warns():
    text = (
        "Verbrauchsabrechnung für Ihre Stromlieferung\n"
        "EPEX SPOT Preis\nMarktlokation: 50000000000"
    )
    doc = classify_pdf_text(text, "a")
    assert any("Rechnungsnummer" in w for w in doc.warnings)


# --------------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------------- #
def test_corrupt_pdf_bytes_do_not_crash():
    doc = classify_pdf(b"not a real pdf", "broken.pdf")
    assert doc.category is Category.UNKNOWN
    assert doc.needs_review


def test_empty_pdf_is_unknown():
    doc = classify_pdf(make_pdf([]), "empty.pdf")
    assert doc.category is Category.UNKNOWN
