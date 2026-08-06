"""Monitoring API token service.

Obtains an access token scoped to the monitoring/Portal API so the backend can
call it on behalf of the application.

Auth model
----------
The backend uses the OAuth 2.0 **client_credentials** grant with its
machine-to-machine application (``AUTH0_CLIENT_ID`` / ``AUTH0_CLIENT_SECRET``),
which is authorised for the monitoring API audience and carries the
``PORTAL_POSTBOX:WRITE`` permission.

Note: this is a *service* identity, not the end user's. Per-user authorisation
is still enforced upstream — every route that calls the monitoring API depends
on ``require_admin`` first, so only users with the ``Invoice Automation Admin``
role can trigger these calls. (A true on-behalf-of / RFC 8693 token exchange
that preserves the user's ``sub`` would require Auth0 Custom Token Exchange to
be enabled on the tenant, which it is not.)

Tokens are cached in-process until shortly before they expire, since a
client_credentials token is not user-specific and can be reused across requests.

Usage
-----
    from app.services.token_exchange import get_monitoring_token

    token = await get_monitoring_token()
    # use as Bearer for monitoring API calls
"""

from __future__ import annotations

import os
import time

import httpx
from fastapi import HTTPException, status

_AUTH0_DOMAIN = os.environ["AUTH0_DOMAIN"]
_AUTH0_CLIENT_ID = os.environ["AUTH0_CLIENT_ID"]
_AUTH0_CLIENT_SECRET = os.environ["AUTH0_CLIENT_SECRET"]
_MONITORING_API_AUDIENCE = os.environ["MONITORING_API_AUDIENCE"]

_TOKEN_ENDPOINT = f"https://{_AUTH0_DOMAIN}/oauth/token"
_GRANT_TYPE = "client_credentials"

# Refresh a little before actual expiry to avoid races on the boundary.
_EXPIRY_SKEW_SECONDS = 60

# In-process cache: {audience: (access_token, expires_at_epoch)}.
_token_cache: dict[str, tuple[str, float]] = {}


async def get_token_for_audience(audience: str) -> str:
    """Return a cached or freshly minted access token for ``audience``.

    Uses the backend's machine-to-machine credentials (client_credentials).

    Raises:
        HTTP 502: Auth0 rejected the request or was unreachable.
    """
    cached = _token_cache.get(audience)
    if cached is not None:
        token, expires_at = cached
        if time.time() < expires_at - _EXPIRY_SKEW_SECONDS:
            return token

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                _TOKEN_ENDPOINT,
                json={
                    "grant_type": _GRANT_TYPE,
                    "client_id": _AUTH0_CLIENT_ID,
                    "client_secret": _AUTH0_CLIENT_SECRET,
                    "audience": audience,
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Auth0 token endpoint: {exc}",
        )

    if response.status_code != 200:
        body = (
            response.json()
            if response.headers.get("content-type", "").startswith(
                "application/json"
            )
            else {}
        )
        error_description = (
            body.get("error_description") or body.get("error") or response.text
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Auth0 token request failed: {error_description}",
        )

    data = response.json()
    access_token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    _token_cache[audience] = (access_token, time.time() + expires_in)
    return access_token


async def get_monitoring_token() -> str:
    """Return an access token scoped to the monitoring API.

    Convenience wrapper around ``get_token_for_audience`` for the monitoring API
    audience configured via ``MONITORING_API_AUDIENCE`` in the environment.
    """
    return await get_token_for_audience(_MONITORING_API_AUDIENCE)
