"""PDF upload + classification + recipient mapping endpoints (pipeline step 2).

Two endpoints:
  POST /api/upload/classify  -> classify PDFs only (no mapping)
  POST /api/upload/process   -> classify PDFs + resolve recipients from the
                                uploaded mapping xlsx, grouped one email per
                                customer (all their MaLos bundled together).
"""

from __future__ import annotations

from collections import Counter, OrderedDict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..classification import Category, ClassifiedDocument, classify_pdf
from ..mapping import load_mapping, resolve_recipient

router = APIRouter(tags=["upload"])


def _is_pdf(file: UploadFile) -> bool:
    return file.content_type == "application/pdf" or (
        file.filename or ""
    ).lower().endswith(".pdf")


async def _classify_files(files: list[UploadFile]) -> list[ClassifiedDocument]:
    documents: list[ClassifiedDocument] = []
    for file in files:
        if not _is_pdf(file):
            documents.append(
                ClassifiedDocument(
                    filename=file.filename or "unknown",
                    category=Category.UNKNOWN,
                    warnings=[f"Not a PDF (content-type={file.content_type})."],
                )
            )
            continue
        raw = await file.read()
        documents.append(classify_pdf(raw, file.filename or "unknown"))
    return documents


def _summary(documents: list[ClassifiedDocument]) -> dict:
    return {
        "categories": dict(Counter(d.category.value for d in documents)),
        "invoice_subtypes": dict(
            Counter(
                d.subtype.value
                for d in documents
                if d.category is Category.INVOICE and d.subtype is not None
            )
        ),
        "needs_review": sum(1 for d in documents if d.needs_review),
    }


@router.post("/upload/classify")
async def classify_uploads(files: list[UploadFile] = File(...)) -> dict:
    """Classify uploaded PDFs and return internal document objects + summary."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    documents = await _classify_files(files)
    return {
        "total": len(documents),
        "summary": _summary(documents),
        "documents": [d.model_dump() for d in documents],
    }


@router.post("/upload/process")
async def process_uploads(
    files: list[UploadFile] = File(...),
    mapping_file: UploadFile = File(...),
) -> dict:
    """Classify PDFs, resolve recipients from the mapping xlsx, group per email.

    Returns:
      - documents: classified docs, each with a ``recipient`` block
      - emails: one entry per customer, bundling all their documents
      - summary: category/subtype/review counts + mapping stats
    """
    if not files:
        raise HTTPException(status_code=400, detail="No PDF files uploaded.")

    mapping_bytes = await mapping_file.read()
    try:
        mapping = load_mapping(mapping_bytes)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid mapping file: {exc}")

    documents = await _classify_files(files)

    # Group into emails keyed by the customer's full MaLo set.
    emails: "OrderedDict[tuple, dict]" = OrderedDict()
    doc_payloads: list[dict] = []
    unmatched = 0
    matched_malos: set[str] = set()

    for doc in documents:
        recipient = resolve_recipient(doc, mapping)
        if not recipient.matched:
            unmatched += 1
        elif recipient.malo:
            matched_malos.add(recipient.malo)

        payload = doc.model_dump()
        payload["recipient"] = recipient.model_dump()
        doc_payloads.append(payload)

        # Key: sorted MaLo set for matched customers; filename for unmatched
        # (so unmatched docs each stand alone and never merge).
        if recipient.matched:
            key = ("customer", tuple(sorted(recipient.malos)))
        else:
            key = ("unmatched", doc.filename)

        bucket = emails.get(key)
        if bucket is None:
            bucket = {
                "matched": recipient.matched,
                "unternehmen": recipient.unternehmen,
                "to": recipient.to,
                "cc": recipient.cc,
                "malos": recipient.malos,
                "documents": [],
                "warnings": list(recipient.warnings),
            }
            emails[key] = bucket
        bucket["documents"].append(doc.filename)

    # Case 2: mapping entries (recipients) with no matching PDF in this batch.
    # De-duplicate by customer entry (a customer may own several MaLos).
    orphan_recipients: list[dict] = []
    seen_entries: set[int] = set()
    for entry in mapping.values():
        if id(entry) in seen_entries:
            continue
        seen_entries.add(id(entry))
        if not any(m in matched_malos for m in entry.malos):
            orphan_recipients.append(
                {
                    "unternehmen": entry.unternehmen,
                    "kundennummer": entry.kundennummer,
                    "malos": entry.malos,
                    "to": entry.to_addresses,
                    "cc": entry.cc_addresses,
                }
            )

    return {
        "total": len(documents),
        "summary": {
            **_summary(documents),
            "emails_to_send": sum(1 for b in emails.values() if b["matched"]),
            "unmatched_documents": unmatched,
            "recipients_without_pdf": len(orphan_recipients),
            "mapping_entries": len(seen_entries),
        },
        "emails": list(emails.values()),
        "documents": doc_payloads,
        # Case 1 lives in documents[].recipient.matched == false.
        # Case 2: recipients present in mapping but with no PDF this batch.
        "orphan_recipients": orphan_recipients,
    }
