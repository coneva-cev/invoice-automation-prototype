"""Tests for batch PDF storage + the retention flow end-to-end."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.storage.batch_store import BatchStore

from .factories import (
    MappingRow,
    gutschrift_pdf,
    invoice_pdf,
    make_mapping_xlsx,
)


# --------------------------------------------------------------------------- #
# BatchStore unit
# --------------------------------------------------------------------------- #
def test_store_roundtrip(tmp_path):
    store = BatchStore(root=tmp_path)
    batch = store.create_batch()
    doc_id = store.add_document(batch, "a.pdf", b"%PDF-1.4 content")
    got = store.get_document(batch, doc_id)
    assert got.filename == "a.pdf"
    assert got.path.read_bytes() == b"%PDF-1.4 content"


def test_store_delete_batch(tmp_path):
    store = BatchStore(root=tmp_path)
    batch = store.create_batch()
    store.add_document(batch, "a.pdf", b"x")
    assert store.batch_exists(batch)
    assert store.delete_batch(batch)
    assert not store.batch_exists(batch)
    with pytest.raises(KeyError):
        store.list_documents(batch)


def test_store_rejects_path_traversal(tmp_path):
    store = BatchStore(root=tmp_path)
    with pytest.raises(ValueError):
        store.get_document("../evil", "x")


# --------------------------------------------------------------------------- #
# Retention flow via endpoints: process -> retrieve -> bundle -> delete
# --------------------------------------------------------------------------- #
def test_process_returns_batch_and_doc_ids(client, pdf_upload, mapping_upload):
    files = pdf_upload(
        {
            "a.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "b.pdf": gutschrift_pdf(malo="50000000002"),
        }
    )
    files.append(
        mapping_upload(
            make_mapping_xlsx(
                [
                    MappingRow(["50000000001"], "Acme", "a@x.example"),
                    MappingRow(["50000000002"], "Erz", "e@x.example"),
                ]
            )
        )
    )
    data = client.post("/api/upload/process", files=files).json()
    assert data["batch_id"]
    # every classified doc has a retrievable doc_id
    for d in data["documents"]:
        assert d["doc_id"]
    # emails carry doc_ids for attachment
    for e in data["emails"]:
        assert "doc_ids" in e


def test_stored_pdf_is_retrievable_and_intact(
    client, pdf_upload, mapping_upload
):
    pdf = invoice_pdf("FIXPRICE", malo="50000000001")
    files = pdf_upload({"a.pdf": pdf})
    files.append(
        mapping_upload(
            make_mapping_xlsx([MappingRow(["50000000001"], "Acme", "a@x.example")])
        )
    )
    data = client.post("/api/upload/process", files=files).json()
    batch_id = data["batch_id"]
    doc_id = data["documents"][0]["doc_id"]

    # SendGrid attachment path: fetch the exact bytes back
    r = client.get(f"/api/upload/batch/{batch_id}/document/{doc_id}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == pdf

    # Portal path: zip all stored PDFs of the batch
    rb = client.get(f"/api/upload/batch/{batch_id}/bundle")
    assert rb.status_code == 200
    with zipfile.ZipFile(io.BytesIO(rb.content)) as zf:
        assert zf.namelist() == ["a.pdf"]
        assert zf.read("a.pdf") == pdf

    # cleanup at end of flow
    rd = client.delete(f"/api/upload/batch/{batch_id}")
    assert rd.status_code == 200
    # gone afterward
    assert (
        client.get(f"/api/upload/batch/{batch_id}/document/{doc_id}").status_code
        == 404
    )


def test_delete_unknown_batch_404(client):
    assert client.delete("/api/upload/batch/deadbeef").status_code == 404
