"""Tests for the PDF zip bundler + /api/upload/bundle endpoint."""

from __future__ import annotations

import io
import zipfile

from app.bundling import BundleFile, build_pdf_bundle

from .factories import gutschrift_pdf, invoice_pdf


def _names_in_zip(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.namelist()


# --------------------------------------------------------------------------- #
# build_pdf_bundle
# --------------------------------------------------------------------------- #
def test_bundle_is_flat_and_complete():
    files = [
        BundleFile("a.pdf", invoice_pdf("TARIF_ONLY", malo="50000000001")),
        BundleFile("b.pdf", gutschrift_pdf(malo="50000000002")),
    ]
    result = build_pdf_bundle(files)
    assert result.file_count == 2
    names = _names_in_zip(result.content)
    assert names == ["a.pdf", "b.pdf"]
    # flat: no directory separators
    assert all("/" not in n for n in names)


def test_bundle_is_valid_zip_with_intact_contents():
    pdf = invoice_pdf("FIXPRICE", malo="50000000003")
    result = build_pdf_bundle([BundleFile("x.pdf", pdf)])
    with zipfile.ZipFile(io.BytesIO(result.content)) as zf:
        assert zf.testzip() is None  # no corrupt entries
        assert zf.read("x.pdf") == pdf  # bytes preserved exactly


def test_duplicate_names_are_decollided():
    pdf = invoice_pdf("TARIF_ONLY", malo="50000000001")
    files = [BundleFile("dup.pdf", pdf) for _ in range(3)]
    result = build_pdf_bundle(files)
    names = _names_in_zip(result.content)
    assert names == ["dup.pdf", "dup (1).pdf", "dup (2).pdf"]
    assert result.file_count == 3
    assert result.renamed  # collisions recorded


def test_empty_content_is_skipped():
    files = [
        BundleFile("good.pdf", invoice_pdf("TARIF_ONLY", malo="50000000001")),
        BundleFile("empty.pdf", b""),
    ]
    result = build_pdf_bundle(files)
    assert result.file_count == 1
    assert "empty.pdf" in result.skipped


def test_missing_extension_gets_pdf():
    result = build_pdf_bundle(
        [BundleFile("noext", invoice_pdf("TARIF_ONLY", malo="50000000001"))]
    )
    assert _names_in_zip(result.content) == ["noext.pdf"]


# --------------------------------------------------------------------------- #
# /api/upload/bundle endpoint
# --------------------------------------------------------------------------- #
def test_bundle_endpoint(client, pdf_upload):
    files = pdf_upload(
        {
            "inv.pdf": invoice_pdf("COMBINED", malo="50000000001"),
            "gut.pdf": gutschrift_pdf(malo="50000000002"),
        }
    )
    r = client.post("/api/upload/bundle", files=files)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["x-bundle-file-count"] == "2"
    names = _names_in_zip(r.content)
    assert sorted(names) == ["gut.pdf", "inv.pdf"]


def test_bundle_endpoint_rejects_non_pdf(client):
    files = [("files", ("note.txt", b"hello", "text/plain"))]
    r = client.post("/api/upload/bundle", files=files)
    assert r.status_code == 422


def test_bundle_endpoint_rejects_empty(client):
    r = client.post("/api/upload/bundle", files=[])
    assert r.status_code in (400, 422)
