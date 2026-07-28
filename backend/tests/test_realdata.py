"""Regression tests against the real sample dataset.

These run only when the gitignored ``backend/samples/`` folder is present
(i.e. locally with the real PDFs). They are skipped in CI / fresh checkouts.

Expected counts are pinned to the known sample set:
  - 29 invoices, 49 Gutschriften (78 total)
  - subtypes: TARIF_ONLY 23, OPTIMIZATION_ONLY 3, COMBINED 2, FIXPRICE 1
"""

from __future__ import annotations

import glob
import os
from collections import Counter

import pytest

from app.classification import Category, classify_pdf

from .conftest import has_samples

pytestmark = pytest.mark.realdata

_INVOICE_GLOB = "260526_ZIP_Stromrechnungen_LZ_04_26/*.pdf"
_GUTSCHRIFT_GLOB = "ZIP_Dateien_DV_Gutschrift_LZ_0626/*.pdf"

EXPECTED_SUBTYPES = {
    "TARIF_ONLY": 23,
    "OPTIMIZATION_ONLY": 3,
    "COMBINED": 2,
    "FIXPRICE": 1,
}


@pytest.mark.skipif(not has_samples(), reason="real samples/ not present")
def test_all_invoices_classify(samples_dir):
    files = glob.glob(str(samples_dir / _INVOICE_GLOB))
    if not files:
        pytest.skip("invoice samples not present")
    subtypes: Counter = Counter()
    for f in files:
        doc = classify_pdf(open(f, "rb").read(), os.path.basename(f))
        assert doc.category is Category.INVOICE, f"{f} -> {doc.category}"
        assert not doc.needs_review, f"{f}: {doc.warnings}"
        subtypes[doc.subtype.value] += 1
    assert len(files) == 29
    assert dict(subtypes) == EXPECTED_SUBTYPES


@pytest.mark.skipif(not has_samples(), reason="real samples/ not present")
def test_all_gutschriften_classify(samples_dir):
    files = glob.glob(str(samples_dir / _GUTSCHRIFT_GLOB))
    if not files:
        pytest.skip("gutschrift samples not present")
    for f in files:
        doc = classify_pdf(open(f, "rb").read(), os.path.basename(f))
        assert doc.category is Category.GUTSCHRIFT, f"{f} -> {doc.category}"
        assert not doc.needs_review, f"{f}: {doc.warnings}"
    assert len(files) == 49


@pytest.mark.skipif(not has_samples(), reason="real samples/ not present")
def test_full_batch_endpoint_via_mapping(
    client, samples_dir, pdf_upload, mapping_upload
):
    mapping_path = samples_dir / "Mapping_MaLo_Empfaenger_TEMPLATE.xlsx"
    if not mapping_path.exists():
        pytest.skip("generated mapping template not present")

    pdfs = glob.glob(str(samples_dir / _INVOICE_GLOB)) + glob.glob(
        str(samples_dir / _GUTSCHRIFT_GLOB)
    )
    files = pdf_upload(
        {os.path.basename(f): open(f, "rb").read() for f in pdfs}
    )
    files.append(mapping_upload(mapping_path.read_bytes()))
    r = client.post("/api/upload/process", files=files)
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["categories"] == {"INVOICE": 29, "GUTSCHRIFT": 49}
    assert s["unmatched_documents"] == 0
    assert s["emails_to_send"] == 67
