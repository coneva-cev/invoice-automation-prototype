"""Document management endpoints — proxies to the Coneva monitoring API.

All routes in this router exchange the user's incoming access token for one
scoped to the monitoring API (token exchange, RFC 8693) before forwarding
requests. The user's identity (``sub``) is preserved in the exchanged token
so the monitoring API can enforce its own RBAC independently.

Pattern for future monitoring API routes
-----------------------------------------
1. Add ``_: dict = Depends(require_permission("admin"))`` to validate the
   user's invoice-automation token.
2. Add ``raw_token: str = Depends(get_raw_token)`` to get the raw Bearer
   string for exchange.
3. Call ``await get_monitoring_token(raw_token)`` to obtain the
   monitoring-scoped token.
4. For calls that target a single tenant, pass the tenant's ``topologyId``
   as the ``authorization-scope`` header.  For multi-tenant endpoints (like
   bulk upload) use the static value from ``MONITORING_API_BULK_UPLOAD_SCOPE``.
"""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.dependencies.auth import get_raw_token, require_permission
from app.services.token_exchange import get_monitoring_token

router = APIRouter(tags=["documents"])

_MONITORING_BASE_URL = os.environ["MONITORING_API_BASE_URL"]
# Static authorization-scope for the multi-tenant bulk-upload endpoint.
# For single-tenant monitoring API calls this header must be set to the
# target tenant's topologyId (passed dynamically by the caller).
_BULK_UPLOAD_SCOPE = os.environ["MONITORING_API_BULK_UPLOAD_SCOPE"]


@router.put("/documents/bulk-upload")
async def bulk_upload_document(
    file: UploadFile = File(...),
    send_email_notification: bool = False,
    _: dict = Depends(require_permission("admin")),
    raw_token: str = Depends(get_raw_token),
) -> Response:
    """Upload a document to the monitoring API's bulk-upload endpoint.

    Exchanges the user's access token for one scoped to the monitoring API
    before forwarding the file. The monitoring API receives the upload as a
    multipart PUT request, identical to calling it directly.

    Args:
        file: The document to upload (any content type).
        send_email_notification: Forwarded as the ``sendEmailNotification``
            query parameter to the monitoring API (default ``False``).

    Returns:
        The monitoring API's response body and status code, passed through
        transparently so the frontend can handle any API-level errors.

    Raises:
        HTTP 502: Auth0 token exchange failed or the monitoring API was
            unreachable.
        HTTP 4xx/5xx: Forwarded from the monitoring API.
    """
    monitoring_token = await get_monitoring_token(raw_token)

    file_bytes = await file.read()
    monitoring_url = (
        f"{_MONITORING_BASE_URL}/v2/documents-bulk-upload"
        f"?sendEmailNotification={str(send_email_notification).lower()}"
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            monitoring_response = await client.put(
                monitoring_url,
                headers={
                    "Authorization": f"Bearer {monitoring_token}",
                    "authorization-scope": _BULK_UPLOAD_SCOPE,
                    "X-Requested-With": "Idea",
                },
                files={
                    "file": (
                        file.filename or "upload",
                        file_bytes,
                        file.content_type or "application/octet-stream",
                    )
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach monitoring API: {exc}",
        )

    return Response(
        content=monitoring_response.content,
        status_code=monitoring_response.status_code,
        media_type=monitoring_response.headers.get("content-type", "application/json"),
    )
