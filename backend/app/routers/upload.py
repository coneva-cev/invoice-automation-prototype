"""PDF upload + classification + recipient mapping endpoints (pipeline step 2).

Two endpoints:
  POST /api/upload/classify  -> classify PDFs only (no mapping)
  POST /api/upload/process   -> classify PDFs + resolve recipients from the
                                uploaded mapping xlsx, grouped one email per
                                customer (all their MaLos bundled together).
"""

from __future__ import annotations

from collections import Counter, OrderedDict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from ..bundling import BundleFile, build_pdf_bundle
from ..classification import Category, ClassifiedDocument, classify_pdf
from ..mapping import load_mapping, resolve_recipient
from ..storage import get_store
from app.dependencies.auth import require_admin

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
async def classify_uploads(
    files: list[UploadFile] = File(...),
    _: dict = Depends(require_admin),
) -> dict:
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
    _: dict = Depends(require_admin),
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

    # Persist the uploaded PDFs so later steps (Portal bundle upload, SendGrid
    # attachments) can retrieve the actual bytes. Deleted when the flow ends.
    store = get_store()
    batch_id = store.create_batch()

    documents: list[ClassifiedDocument] = []
    doc_ids: list[str | None] = []
    for file in files:
        if not _is_pdf(file):
            documents.append(
                ClassifiedDocument(
                    filename=file.filename or "unknown",
                    category=Category.UNKNOWN,
                    warnings=[f"Not a PDF (content-type={file.content_type})."],
                )
            )
            doc_ids.append(None)
            continue
        raw = await file.read()
        documents.append(classify_pdf(raw, file.filename or "unknown"))
        doc_ids.append(store.add_document(batch_id, file.filename or "document.pdf", raw))

    # Group into emails keyed by the customer's full MaLo set.
    emails: "OrderedDict[tuple, dict]" = OrderedDict()
    doc_payloads: list[dict] = []
    unmatched = 0
    matched_malos: set[str] = set()

    for doc, doc_id in zip(documents, doc_ids):
        recipient = resolve_recipient(doc, mapping)
        if not recipient.matched:
            unmatched += 1
        elif recipient.malo:
            matched_malos.add(recipient.malo)

        payload = doc.model_dump()
        payload["doc_id"] = doc_id
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
                "doc_ids": [],
                "warnings": list(recipient.warnings),
            }
            emails[key] = bucket
        bucket["documents"].append(doc.filename)
        if doc_id is not None:
            bucket["doc_ids"].append(doc_id)

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
        "batch_id": batch_id,
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


@router.get("/upload/batch/{batch_id}/document/{doc_id}")
def get_stored_document(
    batch_id: str,
    doc_id: str,
    _: dict = Depends(require_admin),
) -> FileResponse:
    """Return a stored PDF by id (for SendGrid attachments / inspection)."""
    store = get_store()
    try:
        stored = store.get_document(batch_id, doc_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(
        stored.path, media_type="application/pdf", filename=stored.filename
    )


@router.get("/upload/batch/{batch_id}/bundle")
def bundle_stored_batch(
    batch_id: str,
    _: dict = Depends(require_admin),
) -> Response:
    """Zip all stored PDFs of a batch (the Portal bulk-upload artifact)."""
    store = get_store()
    try:
        stored = store.list_documents(batch_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Batch not found.")
    if not stored:
        raise HTTPException(status_code=404, detail="Batch has no documents.")

    result = build_pdf_bundle(
        [BundleFile(s.filename, s.path.read_bytes()) for s in stored]
    )
    return Response(
        content=result.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="portal_bundle.zip"',
            "X-Bundle-File-Count": str(result.file_count),
        },
    )


@router.delete("/upload/batch/{batch_id}")
def delete_batch(
    batch_id: str,
    _: dict = Depends(require_admin),
) -> dict:
    """Delete a batch's stored PDFs. Call when the flow completes."""
    store = get_store()
    try:
        deleted = store.delete_batch(batch_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid batch id.")
    if not deleted:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return {"deleted": batch_id}


@router.post("/upload/bundle")
async def bundle_uploads(
    files: list[UploadFile] = File(...),
    _: dict = Depends(require_admin),
) -> Response:
    """Zip all uploaded PDFs into one flat archive for the Portal bulk upload.

    Returns the zip as a binary download. This is the internal artifact the
    Portal-upload step (step 4) hands to the Portal API. Bundle metadata
    (final names, renames, skipped) is returned in response headers.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    bundle_files: list[BundleFile] = []
    for file in files:
        if not _is_pdf(file):
            raise HTTPException(
                status_code=422,
                detail=f"Not a PDF: {file.filename} ({file.content_type}).",
            )
        bundle_files.append(
            BundleFile(filename=file.filename or "document.pdf", content=await file.read())
        )

    result = build_pdf_bundle(bundle_files)
    headers = {
        "Content-Disposition": 'attachment; filename="portal_bundle.zip"',
        "X-Bundle-File-Count": str(result.file_count),
    }
    if result.renamed:
        headers["X-Bundle-Renamed"] = str(len(result.renamed))
    if result.skipped:
        headers["X-Bundle-Skipped"] = str(len(result.skipped))

    return Response(
        content=result.content,
        media_type="application/zip",
        headers=headers,
    )
