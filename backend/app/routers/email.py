"""Email draft generation, review, and sending (pipeline steps 4/5).

Flow
----
1. ``POST /api/email/batch/{batch_id}/drafts`` — generate drafts from the
   processed batch (one per customer+category), persist, and return them.
2. ``GET  /api/email/batch/{batch_id}/drafts`` — list persisted drafts.
3. ``GET  /api/email/batch/{batch_id}/drafts/{draft_id}/preview`` — rendered
   HTML body (for an iframe preview in the UI).
4. ``GET  .../drafts/{draft_id}/attachment/{doc_id}`` — inline PDF preview.
5. ``PATCH .../drafts/{draft_id}`` — edit recipients/subject (body is fixed;
   the HTML is re-rendered when the subject changes).
6. ``POST /api/email/batch/{batch_id}/drafts/send`` — materialize attachments
   and send via the configured backend; returns per-draft results.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ..email import (
    DraftPatch,
    DraftStatus,
    EmailAttachment,
    EmailDraft,
    OutboundEmail,
    build_drafts,
    get_sender,
)
from ..email.config import resolve_email_config
from ..email.template import render_email
from ..storage import get_store
from app.dependencies.auth import require_admin

router = APIRouter(tags=["email"], prefix="/email")
_log = logging.getLogger("app.email")


def _load_drafts(batch_id: str) -> list[EmailDraft]:
    store = get_store()
    try:
        raw = store.load_drafts(batch_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Batch not found.")
    return [EmailDraft(**d) for d in raw]


def _persist(batch_id: str, drafts: list[EmailDraft]) -> None:
    get_store().save_drafts(batch_id, [d.model_dump() for d in drafts])


@router.get("/mode")
def email_mode(
    _: dict = Depends(require_admin),
) -> dict:
    """Report the active send mode so the UI can show it before sending."""
    cfg = resolve_email_config()
    return {
        "app_env": cfg.app_env,
        "backend": cfg.backend,
        "sandbox": cfg.sandbox,
        "delivers": cfg.delivers,
        "label": cfg.mode_label,
        "real_send_blocked": cfg.real_send_blocked,
    }


@router.post("/batch/{batch_id}/drafts")
def generate_drafts(
    batch_id: str,
    _: dict = Depends(require_admin),
) -> dict:
    """(Re)generate email drafts for a processed batch and persist them."""
    store = get_store()
    try:
        result = store.load_result(batch_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Batch not found.")
    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Batch has no processed result; run /upload/process first.",
        )
    drafts = build_drafts(result)
    _persist(batch_id, drafts)
    return {
        "batch_id": batch_id,
        "total": len(drafts),
        "ready": sum(1 for d in drafts if d.status is DraftStatus.READY),
        "drafts": [d.model_dump() for d in drafts],
    }


@router.get("/batch/{batch_id}/drafts")
def list_drafts(
    batch_id: str,
    _: dict = Depends(require_admin),
) -> dict:
    drafts = _load_drafts(batch_id)
    return {
        "batch_id": batch_id,
        "total": len(drafts),
        "drafts": [d.model_dump() for d in drafts],
    }


def _find(drafts: list[EmailDraft], draft_id: str) -> EmailDraft:
    for d in drafts:
        if d.draft_id == draft_id:
            return d
    raise HTTPException(status_code=404, detail="Draft not found.")


class SendRequest(BaseModel):
    """Optional body for the send endpoint.

    When ``draft_ids`` is provided, only those drafts are sent (used to send a
    user-selected subset — e.g. excluding drafts whose documents failed to
    upload to the Portal). When omitted, all sendable drafts are sent.
    """

    draft_ids: list[str] | None = None


@router.get("/batch/{batch_id}/drafts/{draft_id}/preview", response_class=HTMLResponse)
def preview_draft(
    batch_id: str,
    draft_id: str,
    _: dict = Depends(require_admin),
) -> HTMLResponse:
    """Return the rendered HTML body for an iframe preview."""
    draft = _find(_load_drafts(batch_id), draft_id)
    return HTMLResponse(content=draft.html)


@router.get("/batch/{batch_id}/drafts/{draft_id}/attachment/{doc_id}")
def preview_attachment(
    batch_id: str,
    draft_id: str,
    doc_id: str,
    _: dict = Depends(require_admin),
) -> FileResponse:
    """Return an attached PDF inline for preview."""
    draft = _find(_load_drafts(batch_id), draft_id)
    if not any(a.doc_id == doc_id for a in draft.attachments):
        raise HTTPException(status_code=404, detail="Attachment not on draft.")
    store = get_store()
    try:
        stored = store.get_document(batch_id, doc_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(
        stored.path,
        media_type="application/pdf",
        filename=stored.filename,
        content_disposition_type="inline",
    )


@router.patch("/batch/{batch_id}/drafts/{draft_id}")
def patch_draft(
    batch_id: str,
    draft_id: str,
    patch: DraftPatch,
    _: dict = Depends(require_admin),
) -> dict:
    """Edit a draft's recipients / subject. Body stays fixed (re-rendered)."""
    drafts = _load_drafts(batch_id)
    draft = _find(drafts, draft_id)

    if patch.to is not None:
        draft.to = patch.to
    if patch.cc is not None:
        draft.cc = patch.cc
    if patch.subject is not None:
        draft.subject = patch.subject

    # Re-render body so an edited subject propagates into the HTML <title>/text.
    _, draft.html = render_email(
        category=draft.category,
        unternehmen=draft.unternehmen,
        documents=[{"filename": a.filename} for a in draft.attachments],
        malos=[],
        subject=draft.subject,
    )
    # Recompute sendability.
    if draft.status in (DraftStatus.READY, DraftStatus.BLOCKED):
        draft.status = DraftStatus.READY if draft.to else DraftStatus.BLOCKED

    _persist(batch_id, drafts)
    return draft.model_dump()


@router.post("/batch/{batch_id}/drafts/send")
def send_drafts(
    batch_id: str,
    payload: SendRequest | None = None,
    _: dict = Depends(require_admin),
) -> dict:
    """Send sendable drafts via the configured backend.

    If ``payload.draft_ids`` is provided, only those drafts are considered for
    sending (others are skipped). This lets the UI send a user-selected subset —
    by default only drafts whose documents uploaded to the Portal successfully.
    """
    drafts = _load_drafts(batch_id)
    store = get_store()
    sender = get_sender()

    selected_ids: set[str] | None = (
        set(payload.draft_ids) if payload and payload.draft_ids is not None else None
    )

    # Resolve + log the active send mode so it's never a surprise which
    # transport ran (and whether anything was actually delivered).
    cfg = resolve_email_config()
    _log.warning(
        "Email send for batch %s: backend=%s sandbox=%s delivers=%s (%s)",
        batch_id,
        cfg.backend,
        cfg.sandbox,
        cfg.delivers,
        cfg.mode_label,
    )

    results: list[dict] = []
    for draft in drafts:
        # Skip drafts the caller did not select for this send.
        if selected_ids is not None and draft.draft_id not in selected_ids:
            continue
        if draft.status is DraftStatus.SENT:
            results.append(
                {"draft_id": draft.draft_id, "sent": True, "status": "SENT",
                 "detail": "Already sent."}
            )
            continue
        if not draft.to:
            draft.status = DraftStatus.BLOCKED
            results.append(
                {"draft_id": draft.draft_id, "sent": False, "status": "BLOCKED",
                 "detail": "No recipient."}
            )
            continue

        # Materialize attachment bytes from the store.
        attachments: list[EmailAttachment] = []
        missing = False
        for a in draft.attachments:
            try:
                stored = store.get_document(batch_id, a.doc_id)
            except (KeyError, ValueError):
                missing = True
                break
            attachments.append(
                EmailAttachment(filename=a.filename, content=stored.path.read_bytes())
            )
        if missing:
            draft.status = DraftStatus.FAILED
            draft.error = "An attachment PDF is missing from storage."
            results.append(
                {"draft_id": draft.draft_id, "sent": False, "status": "FAILED",
                 "detail": draft.error}
            )
            continue

        outbound = OutboundEmail(
            draft_id=draft.draft_id,
            to=draft.to,
            cc=draft.cc,
            subject=draft.subject,
            html=draft.html,
            attachments=attachments,
        )
        res = sender.send(outbound)
        draft.status = res.status
        draft.error = None if res.sent else res.detail
        results.append(res.model_dump())

    _persist(batch_id, drafts)
    return {
        "batch_id": batch_id,
        "sent": sum(1 for r in results if r["sent"]),
        "failed": sum(1 for r in results if not r["sent"]),
        "results": results,
        # Active send mode so the UI can show exactly what happened.
        "mode": {
            "app_env": cfg.app_env,
            "backend": cfg.backend,
            "sandbox": cfg.sandbox,
            "delivers": cfg.delivers,
            "label": cfg.mode_label,
            "real_send_blocked": cfg.real_send_blocked,
        },
    }
