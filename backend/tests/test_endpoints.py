"""Integration tests for the upload endpoints via FastAPI TestClient."""

from __future__ import annotations

from .factories import (
    MappingRow,
    gutschrift_pdf,
    invoice_pdf,
    make_mapping_xlsx,
    unknown_pdf,
)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --------------------------------------------------------------------------- #
# /api/upload/classify
# --------------------------------------------------------------------------- #
def test_classify_endpoint(client, pdf_upload):
    files = pdf_upload(
        {
            "inv1.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "inv2.pdf": invoice_pdf("FIXPRICE", malo="50000000002"),
            "gut1.pdf": gutschrift_pdf(malo="50000000003"),
        }
    )
    r = client.post("/api/upload/classify", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["summary"]["categories"] == {"INVOICE": 2, "GUTSCHRIFT": 1}
    assert data["summary"]["invoice_subtypes"] == {
        "TARIF_ONLY": 1,
        "FIXPRICE": 1,
    }


def test_classify_rejects_empty(client):
    r = client.post("/api/upload/classify", files=[])
    assert r.status_code in (400, 422)


def test_classify_non_pdf_flagged(client):
    files = [("files", ("note.txt", b"hello", "text/plain"))]
    r = client.post("/api/upload/classify", files=files)
    assert r.status_code == 200
    doc = r.json()["documents"][0]
    assert doc["category"] == "UNKNOWN"


# --------------------------------------------------------------------------- #
# /api/upload/process (classification + mapping)
# --------------------------------------------------------------------------- #
def _process(client, pdf_upload, mapping_upload, pdfs, rows):
    files = pdf_upload(pdfs)
    files.append(mapping_upload(make_mapping_xlsx(rows)))
    r = client.post("/api/upload/process", files=files)
    assert r.status_code == 200, r.text
    return r.json()


def test_process_happy_path(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "a.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "b.pdf": gutschrift_pdf(malo="50000000002"),
        },
        [
            MappingRow(["50000000001"], "Acme GmbH", "a@acme.example"),
            MappingRow(["50000000002"], "Erzeuger GmbH", "e@erz.example"),
        ],
    )
    s = data["summary"]
    assert data["total"] == 2
    assert s["emails_to_send"] == 2
    assert s["unmatched_documents"] == 0
    assert s["recipients_without_pdf"] == 0


def test_process_multi_malo_single_email(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "b1.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "b2.pdf": invoice_pdf("TARIF_ONLY", malo="50000000002"),
            "b3.pdf": invoice_pdf("TARIF_ONLY", malo="50000000003"),
        },
        [
            MappingRow(
                ["50000000001", "50000000002", "50000000003"],
                "Bürger GmbH",
                "mb@buerger.example",
            ),
        ],
    )
    assert data["total"] == 3
    assert data["summary"]["emails_to_send"] == 1  # bundled
    email = data["emails"][0]
    assert len(email["documents"]) == 3
    assert email["to"] == ["mb@buerger.example"]


def test_process_pdf_without_recipient(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "known.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "orphan.pdf": invoice_pdf("TARIF_ONLY", malo="59999999999"),
        },
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    assert data["summary"]["unmatched_documents"] == 1
    unmatched = [
        d for d in data["documents"] if not d["recipient"]["matched"]
    ]
    assert len(unmatched) == 1
    assert unmatched[0]["fields"]["marktlokation"] == "59999999999"


def test_process_recipient_without_pdf(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"a.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001")},
        [
            MappingRow(["50000000001"], "Acme GmbH", "a@acme.example"),
            MappingRow(["50000000099"], "Ghost GmbH", "ghost@example.com"),
        ],
    )
    assert data["summary"]["recipients_without_pdf"] == 1
    orphans = data["orphan_recipients"]
    assert len(orphans) == 1
    assert orphans[0]["unternehmen"] == "Ghost GmbH"


def test_process_both_mismatches(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "ok.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "orphan.pdf": gutschrift_pdf(malo="59999999999"),
        },
        [
            MappingRow(["50000000001"], "Acme GmbH", "a@acme.example"),
            MappingRow(["50000000099"], "Ghost GmbH", "ghost@example.com"),
        ],
    )
    assert data["summary"]["unmatched_documents"] == 1
    assert data["summary"]["recipients_without_pdf"] == 1


def test_process_unknown_pdf_counts_review(
    client, pdf_upload, mapping_upload
):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"weird.pdf": unknown_pdf()},
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    assert data["summary"]["needs_review"] >= 1
    # unknown pdf has no malo -> unmatched, and its recipient row is orphan
    assert data["summary"]["unmatched_documents"] == 1


def test_process_invalid_mapping_file(client, pdf_upload, mapping_upload):
    files = pdf_upload({"a.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001")})
    files.append(mapping_upload(b"not an xlsx", name="bad.xlsx"))
    r = client.post("/api/upload/process", files=files)
    assert r.status_code == 422
