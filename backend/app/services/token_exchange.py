"""Auth0 Token Exchange service.

Exchanges a user's access token (scoped to the invoice automation API) for a
new access token scoped to a downstream API, preserving the user's identity
(``sub`` claim) so the downstream API can enforce its own RBAC on the user.

This implements RFC 8693 (OAuth 2.0 Token Exchange) as supported by Auth0.

Auth0 requirements
------------------
* The backend M2M application (identified by AUTH0_CLIENT_ID) must be
  authorised to request tokens for the target audience in the Auth0 Dashboard.
* Token Exchange must be permitted for the target API in the Auth0 tenant.

Usage
-----
    from app.services.token_exchange import get_monitoring_token

    monitoring_token = await get_monitoring_token(user_raw_token)
    # use monitoring_token as Bearer for monitoring API calls

For future calls to other APIs with a different audience, call
``exchange_token`` directly:

    from app.services.token_exchange import exchange_token

    other_token = await exchange_token(user_raw_token, audience="https://other-api/")
"""

from __future__ import annotations

import os

import httpx
from fastapi import HTTPException, status

_AUTH0_DOMAIN = os.environ["AUTH0_DOMAIN"]
_AUTH0_CLIENT_ID = os.environ["AUTH0_CLIENT_ID"]
_AUTH0_CLIENT_SECRET = os.environ["AUTH0_CLIENT_SECRET"]
_MONITORING_API_AUDIENCE = os.environ["MONITORING_API_AUDIENCE"]

_TOKEN_ENDPOINT = f"https://{_AUTH0_DOMAIN}/oauth/token"
_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"


async def exchange_token(user_token: str, audience: str) -> str:
    """Exchange a user access token for one scoped to ``audience``.

    This is the general-purpose exchange primitive. Prefer the named helpers
    below (e.g. ``get_monitoring_token``) for specific downstream APIs.

    Args:
        user_token: The raw Bearer token received from the frontend, already
            validated against the invoice automation API.
        audience: The API identifier (audience) of the target API.

    Returns:
        A new access token scoped to ``audience``, with the user's ``sub``
        preserved.

    Raises:
        HTTP 502: Auth0 rejected the exchange or was unreachable.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                _TOKEN_ENDPOINT,
                json={
                    "grant_type": _GRANT_TYPE,
                    "subject_token": user_token,
                    "subject_token_type": _TOKEN_TYPE,
                    "audience": audience,
                    "client_id": _AUTH0_CLIENT_ID,
                    "client_secret": _AUTH0_CLIENT_SECRET,
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach Auth0 token endpoint: {exc}",
        )

    if response.status_code != 200:
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        error_description = body.get("error_description") or body.get("error") or response.text
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Auth0 token exchange failed: {error_description}",
        )

    return response.json()["access_token"]


async def get_monitoring_token(user_token: str) -> str:
    """Exchange a user token for one scoped to the monitoring API.

    Convenience wrapper around ``exchange_token`` for the monitoring API
    audience configured via ``MONITORING_API_AUDIENCE`` in the environment.
    """
    return await exchange_token(user_token, audience=_MONITORING_API_AUDIENCE)
