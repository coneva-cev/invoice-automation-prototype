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
)
from ..email.config import (
    allowed_destinations,
    build_send_mode_view,
    resolve_app_mode,
    resolve_bcc,
    resolve_send_plan,
)
from ..email.sender import EmailSenderConfigError, build_sender
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
    """Report the active email mode + available destinations for the UI."""
    return build_send_mode_view()


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


class SendDestination(BaseModel):
    """The chosen send destination for this request.

    ``kind`` is one of the destinations the current app mode permits (see
    ``/email/mode``). ``replace_to`` is the address ALL recipients are diverted
    to for test-mode destinations; it must belong to an allowed domain. The
    server re-validates everything via ``resolve_send_plan`` — this body is only
    a request, never trusted.
    """

    kind: str
    replace_to: str | None = None


class SendRequest(BaseModel):
    """Optional body for the send endpoint.

    When ``draft_ids`` is provided, only those drafts are sent (used to send a
    user-selected subset — e.g. excluding drafts whose documents failed to
    upload to the Portal). When omitted, all sendable drafts are sent.

    ``destination`` selects where the emails go (Mailpit / SendGrid sandbox /
    SendGrid to a coneva address / SendGrid live). Required in the UI; if
    omitted the server picks a safe default for the current mode.
    """

    draft_ids: list[str] | None = None
    destination: SendDestination | None = None


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


def _test_mode_annotate(
    subject: str, html: str, orig_to: list[str], orig_cc: list[str]
) -> tuple[str, str]:
    """Prefix the subject and inject a banner listing the intended recipients.

    Applied only in Test Mode so the diverted test email shows who it *would*
    have gone to. Production emails are never modified by this.
    """
    intended = ", ".join(orig_to + orig_cc) or "—"
    new_subject = f"[TEST \u2192 {intended}] {subject}"
    banner = (
        '<div style="margin:0 0 16px;padding:12px 16px;border:2px solid #b91c1c;'
        "background:#fef2f2;color:#991b1b;font-family:Arial,Helvetica,sans-serif;"
        'font-size:13px;">'
        "<strong>TEST MODE</strong> \u2014 this email was diverted to a test "
        f"address. Intended recipient(s): {intended}. Real recipients did not "
        "receive it.</div>"
    )
    lower = html.lower()
    idx = lower.find("<body")
    if idx != -1:
        end = html.find(">", idx)
        if end != -1:
            return new_subject, html[: end + 1] + banner + html[end + 1 :]
    return new_subject, banner + html


@router.post("/batch/{batch_id}/drafts/send")
def send_drafts(
    batch_id: str,
    payload: SendRequest | None = None,
    _: dict = Depends(require_admin),
) -> dict:
    """Send selected drafts to the chosen destination.

    Safety is centralised in ``resolve_send_plan`` (the single authority): it
    validates the requested destination against the app mode (``EMAIL_MODE``)
    and, for test destinations, requires + domain-checks the replacement
    address. If the plan is not OK the whole send is refused (HTTP 400) and
    nothing is sent (fail-closed).

    When the plan carries a ``replace_to`` address, EVERY recipient (To/Cc/Bcc)
    of EVERY email is replaced with it — enforced here, the single point where
    the ``OutboundEmail`` is built, so no transport or UI path can bypass it —
    and the email is annotated with the intended recipient for verification.
    """
    drafts = _load_drafts(batch_id)
    store = get_store()

    selected_ids: set[str] | None = (
        set(payload.draft_ids) if payload and payload.draft_ids is not None else None
    )

    # --- Resolve + validate the send plan (the single guardrail authority) ---
    dest = payload.destination if payload else None
    plan = resolve_send_plan(
        kind=dest.kind if dest else None,
        replace_to=dest.replace_to if dest else None,
    )
    if not plan.ok:
        # Fail-closed: refuse the entire send. Nothing is sent.
        raise HTTPException(status_code=400, detail=plan.error)

    bcc = resolve_bcc()
    try:
        sender = build_sender(plan.backend, sandbox=plan.sandbox)
    except EmailSenderConfigError as exc:
        # Missing/invalid transport config (e.g. no SendGrid API key). Refuse
        # cleanly rather than surfacing a raw 500.
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - any other transport setup failure
        raise HTTPException(
            status_code=400,
            detail=f"Could not initialise the email transport: {exc}",
        )

    _log.warning(
        "Email send for batch %s: mode=%s destination=%s backend=%s sandbox=%s "
        "replace_to=%s delivers_real=%s",
        batch_id,
        resolve_app_mode(),
        plan.kind,
        plan.backend,
        plan.sandbox,
        plan.replace_to or "-",
        plan.delivers_real,
    )

    results: list[dict] = []
    for draft in drafts:
        # Skip drafts the caller did not select for this send.
        if selected_ids is not None and draft.draft_id not in selected_ids:
            continue
        if draft.status is DraftStatus.SENT:
            # Blanket send (no explicit selection) never re-sends already-sent
            # drafts, to avoid accidental duplicate customer mail. A resend must
            # be explicit: the caller lists the SENT draft's id in draft_ids.
            if selected_ids is None:
                results.append(
                    {"draft_id": draft.draft_id, "sent": True, "status": "SENT",
                     "detail": "Already sent."}
                )
                continue
            # else: fall through and re-send this explicitly-selected draft.
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

        # Build the final recipients + content from the validated plan. When the
        # plan replaces recipients, ALL of To/Cc/Bcc become the single test
        # address and the email is annotated with the intended recipient.
        if plan.replace_to is not None:
            out_to = [plan.replace_to]
            out_cc: list[str] = []
            out_bcc: list[str] = []
            subject, html = _test_mode_annotate(
                draft.subject, draft.html, draft.to, draft.cc
            )
        else:
            out_to = draft.to
            out_cc = draft.cc
            out_bcc = bcc
            subject, html = draft.subject, draft.html

        outbound = OutboundEmail(
            draft_id=draft.draft_id,
            to=out_to,
            cc=out_cc,
            bcc=out_bcc,
            subject=subject,
            html=html,
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
        # What actually happened, for the UI.
        "mode": {
            "app_mode": resolve_app_mode(),
            "destination": plan.kind,
            "backend": plan.backend,
            "sandbox": plan.sandbox,
            "replaced_to": plan.replace_to,
            "delivers_real": plan.delivers_real,
            "bcc": [] if plan.replace_to is not None else bcc,
        },
    }
