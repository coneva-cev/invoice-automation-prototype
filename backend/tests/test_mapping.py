"""Unit tests for MaLo-based recipient mapping."""

from __future__ import annotations

import pytest

from app.classification import classify_pdf
from app.mapping import load_mapping, resolve_recipient

from .factories import MappingRow, invoice_pdf, make_mapping_xlsx


def _mapping(*rows: MappingRow):
    return load_mapping(make_mapping_xlsx(list(rows)))


def test_single_malo_resolves():
    mapping = _mapping(
        MappingRow(["50000000001"], "Acme GmbH", "billing@acme.example")
    )
    doc = classify_pdf(invoice_pdf("TARIF_ONLY", malo="50000000001"), "a.pdf")
    r = resolve_recipient(doc, mapping)
    assert r.matched
    assert r.to == ["billing@acme.example"]
    assert r.unternehmen == "Acme GmbH"


def test_multi_malo_shares_one_entry():
    mapping = _mapping(
        MappingRow(
            ["50000000001", "50000000002", "50000000003"],
            "Bürger GmbH",
            "mb@buerger.example",
        )
    )
    # index has one key per malo
    assert set(mapping) == {"50000000001", "50000000002", "50000000003"}
    # each malo resolves to the same customer with full malo list
    for m in ("50000000001", "50000000002", "50000000003"):
        doc = classify_pdf(invoice_pdf("TARIF_ONLY", malo=m), "a.pdf")
        r = resolve_recipient(doc, mapping)
        assert r.matched
        assert r.to == ["mb@buerger.example"]
        assert sorted(r.malos) == [
            "50000000001",
            "50000000002",
            "50000000003",
        ]


def test_cc_includes_ceo():
    mapping = _mapping(
        MappingRow(
            ["50000000001"],
            "Acme GmbH",
            "billing@acme.example",
            cc_email="extern@acme.example",
            ceo_email="ceo@acme.example",
        )
    )
    doc = classify_pdf(invoice_pdf("TARIF_ONLY", malo="50000000001"), "a.pdf")
    r = resolve_recipient(doc, mapping)
    assert r.cc == ["extern@acme.example", "ceo@acme.example"]


def test_unmatched_malo():
    mapping = _mapping(
        MappingRow(["50000000001"], "Acme GmbH", "billing@acme.example")
    )
    doc = classify_pdf(invoice_pdf("TARIF_ONLY", malo="59999999999"), "a.pdf")
    r = resolve_recipient(doc, mapping)
    assert not r.matched
    assert r.warnings


def test_missing_primary_email_warns():
    mapping = _mapping(MappingRow(["50000000001"], "Acme GmbH", ""))
    doc = classify_pdf(invoice_pdf("TARIF_ONLY", malo="50000000001"), "a.pdf")
    r = resolve_recipient(doc, mapping)
    assert r.matched
    assert not r.to
    assert any("primary email" in w.lower() for w in r.warnings)


def test_malo_normalization_handles_float_artifact():
    # openpyxl may hand back "50000000001.0" for numeric cells
    from app.mapping.mapper import _norm_malo, _split_malos

    assert _norm_malo("50000000001.0") == "50000000001"
    assert _split_malos("50000000001, 50000000002;50000000003") == [
        "50000000001",
        "50000000002",
        "50000000003",
    ]


def test_empty_mapping_raises_or_matches_nothing():
    mapping = _mapping()
    doc = classify_pdf(invoice_pdf("TARIF_ONLY", malo="50000000001"), "a.pdf")
    r = resolve_recipient(doc, mapping)
    assert not r.matched


def test_mapping_missing_malo_column_raises():
    from openpyxl import Workbook
    import io

    wb = Workbook()
    ws = wb.active
    ws.title = "Mapping"
    ws.append(["Unternehmen", "Primary Email"])
    ws.append(["Acme", "a@example.com"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError):
        load_mapping(buf.getvalue())
