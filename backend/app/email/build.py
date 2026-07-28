"""Build reviewable email drafts from a processed batch.

Input is the dict returned by ``POST /api/upload/process`` (its ``emails`` and
``documents`` blocks). Output is a list of :class:`EmailDraft`.

Rules
-----
* Only *matched* email groups produce drafts (unmatched docs have no
  recipient, so nothing to send).
* Bodies are fixed *per category*, and a customer may have both an invoice and
  a Gutschrift in the same batch, so each email group is **split by category**
  into up to one draft per category present. This keeps every rendered body
  unambiguous.
* Attachments are referenced by ``doc_id`` (bytes stay in the BatchStore).
"""

from __future__ import annotations

import uuid

from .models import DraftAttachment, DraftStatus, EmailDraft
from .template import render_email


def _index_documents(documents: list[dict]) -> dict[str, dict]:
    """Map doc_id -> document payload for quick lookup."""
    return {d["doc_id"]: d for d in documents if d.get("doc_id")}


def build_drafts(process_result: dict) -> list[EmailDraft]:
    """Generate one draft per (matched customer, document category).

    Args:
        process_result: the dict from ``/api/upload/process`` (must include
            ``batch_id``, ``emails`` and ``documents``).

    Returns:
        Ordered list of drafts (invoice drafts before gutschrift for a given
        customer, following category iteration order).
    """
    batch_id: str = process_result["batch_id"]
    docs_by_id = _index_documents(process_result.get("documents", []))
    drafts: list[EmailDraft] = []

    for group in process_result.get("emails", []):
        if not group.get("matched"):
            continue  # unmatched groups have no recipient — skip

        to = list(group.get("to", []))
        cc = list(group.get("cc", []))
        unternehmen = group.get("unternehmen")
        malos = list(group.get("malos", []))

        # Bucket this customer's documents by category.
        by_category: dict[str, list[dict]] = {}
        for doc_id in group.get("doc_ids", []):
            doc = docs_by_id.get(doc_id)
            if doc is None:
                continue
            category = doc.get("category", "UNKNOWN")
            by_category.setdefault(category, []).append(doc)

        # One draft per category present (stable order: INVOICE, GUTSCHRIFT, then rest).
        ordered = sorted(
            by_category.items(),
            key=lambda kv: {"INVOICE": 0, "GUTSCHRIFT": 1}.get(kv[0], 2),
        )
        for category, docs in ordered:
            attachments = [
                DraftAttachment(
                    doc_id=d["doc_id"],
                    filename=d["filename"],
                    category=d.get("category", "UNKNOWN"),
                    subtype=d.get("subtype"),
                )
                for d in docs
            ]
            subject, html = render_email(
                category=category,
                unternehmen=unternehmen,
                documents=[{"filename": d["filename"]} for d in docs],
                malos=malos,
            )

            warnings: list[str] = []
            if category == "UNKNOWN":
                warnings.append(
                    "Contains documents with unknown category; using default body."
                )
            if not to:
                warnings.append("No TO recipient resolved.")

            drafts.append(
                EmailDraft(
                    draft_id=uuid.uuid4().hex,
                    batch_id=batch_id,
                    category=category,
                    unternehmen=unternehmen,
                    to=to,
                    cc=cc,
                    subject=subject,
                    html=html,
                    attachments=attachments,
                    status=DraftStatus.READY if to else DraftStatus.BLOCKED,
                    warnings=warnings,
                )
            )

    return drafts
