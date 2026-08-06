"""Document management endpoints — proxies to the Coneva monitoring API.

Routes are gated on the ``Invoice Automation Admin`` role (``require_admin``).
The monitoring API itself is called with the backend's machine-to-machine
service credentials (client_credentials; see ``services/token_exchange.py``),
not the individual user's token — Auth0 Custom Token Exchange is not enabled on
the tenant, so a true on-behalf-of flow is unavailable. Per-user access is still
enforced because ``require_admin`` runs before any monitoring call.

Pattern for future monitoring API routes
-----------------------------------------
1. Add ``_: dict = Depends(require_admin)`` to authorise the user.
2. Call ``await get_monitoring_token()`` to obtain a monitoring-scoped token.
3. For calls that target a single tenant, pass the tenant's ``topologyId``
   as the ``authorization-scope`` header. For multi-tenant endpoints (like
   bulk upload) use the static value from ``MONITORING_API_BULK_UPLOAD_SCOPE``.
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.dependencies.auth import require_admin
from app.services.token_exchange import get_monitoring_token

from ..bundling import BundleFile, build_pdf_bundle
from ..storage import get_store

router = APIRouter(tags=["documents"])

_MONITORING_BASE_URL = os.environ["MONITORING_API_BASE_URL"]
# Static authorization-scope for the multi-tenant bulk-upload endpoint.
# For single-tenant monitoring API calls this header must be set to the
# target tenant's topologyId (passed dynamically by the caller).
_BULK_UPLOAD_SCOPE = os.environ["MONITORING_API_BULK_UPLOAD_SCOPE"]

# `sendEmailNotification` is intentionally hardcoded to false: this application
# sends recipient emails itself (the "Send emails" step). The monitoring API
# must never send its own notifications for these uploads, or customers would
# receive duplicate mail.
_SEND_EMAIL_NOTIFICATION = False

_BULK_UPLOAD_URL = (
    f"{_MONITORING_BASE_URL}/v2/documents-bulk-upload"
    f"?sendEmailNotification={str(_SEND_EMAIL_NOTIFICATION).lower()}"
)


async def _send_to_monitoring(
    filename: str,
    content: bytes,
    content_type: str,
) -> httpx.Response:
    """Acquire a monitoring-API token and PUT one file to the bulk-upload.

    Shared by the single-file and batch (zip) upload routes. Returns the raw
    ``httpx.Response`` so callers can pass through the monitoring API's status
    code and body (including per-file OK/ERROR results) transparently.

    Raises:
        HTTP 502: Token acquisition failed or the monitoring API was
            unreachable at the transport level.
    """
    monitoring_token = await get_monitoring_token()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            return await client.put(
                _BULK_UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {monitoring_token}",
                    "authorization-scope": _BULK_UPLOAD_SCOPE,
                    "X-Requested-With": "Python",
                },
                files={"file": (filename, content, content_type)},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach monitoring API: {exc}",
        )


def _passthrough(monitoring_response: httpx.Response) -> Response:
    """Forward the monitoring API's status code and body to the client.

    4xx/5xx responses are forwarded as-is so the frontend can display the
    error and offer a retry.
    """
    return Response(
        content=monitoring_response.content,
        status_code=monitoring_response.status_code,
        media_type=monitoring_response.headers.get(
            "content-type", "application/json"
        ),
    )


@router.put("/documents/bulk-upload")
async def bulk_upload_document(
    file: UploadFile = File(...),
    _: dict = Depends(require_admin),
) -> Response:
    """Upload a single document to the monitoring API's bulk-upload endpoint.

    The user is authorised via ``require_admin``; the monitoring API is called
    with the backend's service credentials. The monitoring API's response
    (status + body) is passed through transparently.
    """
    content = await file.read()
    monitoring_response = await _send_to_monitoring(
        file.filename or "upload",
        content,
        file.content_type or "application/octet-stream",
    )
    return _passthrough(monitoring_response)


@router.post("/documents/batch/{batch_id}/bulk-upload")
async def bulk_upload_batch(
    batch_id: str,
    include_unmatched: bool = False,
    _: dict = Depends(require_admin),
) -> Response:
    """Bundle a batch's PDFs into a single ZIP and bulk-upload it to the Portal.

    Builds the flat PDF bundle server-side (no round-trip through the browser)
    and PUTs the zip to the monitoring API's ``documents-bulk-upload`` endpoint
    using the backend's service credentials. The user is authorised via
    ``require_admin`` first. The Portal unpacks the zip and returns a per-file
    result map, e.g.::

        { "Gutschrift_..._51485303759.pdf": "OK",
          "Gutschrift_..._50889204761.pdf": "ERROR: No tenant found with malo: ..." }

    That body and its status code are passed through unchanged so the frontend
    can render a per-file results table and offer a retry on failure.

    By default only documents that matched a recipient in the validation step
    are uploaded (documents that failed validation would just error out at the
    Portal). Pass ``include_unmatched=true`` to upload every document in the
    batch regardless of validation outcome.

    Raises:
        HTTP 404: Unknown batch or the batch has no documents (after filtering).
        HTTP 502: Token acquisition failed or the monitoring API was unreachable.
        HTTP 4xx/5xx: Forwarded from the monitoring API.
    """
    store = get_store()
    try:
        stored = store.list_documents(batch_id)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Batch not found.")
    if not stored:
        raise HTTPException(status_code=404, detail="Batch has no documents.")

    if not include_unmatched:
        # Restrict to documents that matched a recipient during validation.
        result = store.load_result(batch_id)
        if result is not None:
            matched_doc_ids = {
                d.get("doc_id")
                for d in result.get("documents", [])
                if d.get("doc_id") and (d.get("recipient") or {}).get("matched")
            }
            stored = [s for s in stored if s.doc_id in matched_doc_ids]
        if not stored:
            raise HTTPException(
                status_code=404,
                detail="No validated (matched) documents to upload.",
            )

    bundle = build_pdf_bundle(
        [BundleFile(s.filename, s.path.read_bytes()) for s in stored]
    )
    monitoring_response = await _send_to_monitoring(
        "portal_bundle.zip",
        bundle.content,
        "application/zip",
    )
    return _passthrough(monitoring_response)
