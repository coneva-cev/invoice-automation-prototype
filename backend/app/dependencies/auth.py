"""Auth0 JWT verification for FastAPI.

Validates the incoming Bearer token against Auth0 and enforces that the token
carries the required Auth0 **role** in its namespaced roles claim (e.g.
``coneva/roles``). Gating on the role — rather than the API ``permissions``
claim — matches the frontend (``useAuthz``) and avoids needing a custom Auth0
Action to copy permissions into the token.

The role that gates the whole application is configured in **one place** — the
``REQUIRED_ROLE`` environment variable (see ``app/.env``), with the claim name
in ``ROLES_CLAIM`` — and is enforced everywhere via the ``require_admin``
dependency. Routes never hardcode the role name.

Usage
-----
from app.dependencies.auth import require_admin

@router.post("/excel/parse")
async def parse_excel(
    file: UploadFile = File(...),
    _: dict = Depends(require_admin),
):
    ...

For additional, finer-grained permissions in the future (e.g. "read-only"),
use the generic ``require_permission("read-only")`` factory.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

_AUTH0_DOMAIN = os.environ["AUTH0_DOMAIN"]
_AUTH0_AUDIENCE = os.environ["AUTH0_AUDIENCE"]
_ISSUER = f"https://{_AUTH0_DOMAIN}/"
_JWKS_URI = f"https://{_AUTH0_DOMAIN}/.well-known/jwks.json"
_ALGORITHMS = ["RS256"]

_bearer = HTTPBearer(auto_error=True)

# Single source of truth for the permission required to use the application.
# Configured centrally via the REQUIRED_PERMISSION env var (app/.env) so the
# permission name is never scattered across route definitions.
REQUIRED_PERMISSION = os.environ.get("REQUIRED_PERMISSION", "admin")

# The app gates on an Auth0 **role** (surfaced in a namespaced ID/access-token
# claim) rather than the API ``permissions`` claim, matching the frontend
# (see ``frontend/src/composables/useAuthz.ts``). This avoids requiring a custom
# Auth0 Action to copy ``permissions`` into the token. Both the role name and
# the claim are configurable so nothing is hardcoded across routes.
REQUIRED_ROLE = os.environ.get("REQUIRED_ROLE", "Invoice Automation Admin")
ROLES_CLAIM = os.environ.get("ROLES_CLAIM", "coneva/roles")


# ---------------------------------------------------------------------------
# JWKS fetching with a simple in-process cache
# ---------------------------------------------------------------------------

_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    """Fetch the JWKS from Auth0, cached for the lifetime of the process."""
    global _jwks_cache
    if _jwks_cache is None:
        response = httpx.get(_JWKS_URI, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
    return _jwks_cache


def _get_rsa_key(token: str) -> dict | None:
    """Extract the matching RSA public key from the JWKS for the given token.

    Returns ``None`` when no key matches (triggers a JWKS refresh + retry).
    """
    header = jwt.get_unverified_header(token)
    for key in _get_jwks().get("keys", []):
        if key.get("kid") == header.get("kid"):
            return {k: key[k] for k in ("kty", "kid", "use", "n", "e") if k in key}
    return None


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT, refreshing the JWKS once on key-id miss."""
    global _jwks_cache

    rsa_key = _get_rsa_key(token)
    if rsa_key is None:
        # Key not found in cache — Auth0 may have rotated keys; force refresh
        _jwks_cache = None
        rsa_key = _get_rsa_key(token)

    if rsa_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to find matching signing key.",
        )

    try:
        return jwt.decode(
            token,
            rsa_key,
            algorithms=_ALGORITHMS,
            audience=_AUTH0_AUDIENCE,
            issuer=_ISSUER,
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_verified_payload(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
) -> dict:
    """Verify the Bearer token and return its decoded payload.

    This is the single verification entry point. Tests can override this one
    dependency (``app.dependency_overrides[get_verified_payload] = ...``) to
    bypass real Auth0 verification, and every ``require_permission(...)``
    dependency picks up the override automatically.
    """
    return _decode_token(credentials.credentials)


def require_permission(permission: str):
    """Return a FastAPI dependency that enforces the given Auth0 permission.

    The dependency resolves to the decoded JWT payload so callers can inspect
    claims (e.g. ``sub``) if needed.

    Raises:
        HTTP 401 — token missing, malformed, expired, or signature invalid.
        HTTP 403 — token valid but the required permission is absent.
    """

    def _dependency(
        payload: Annotated[dict, Depends(get_verified_payload)],
    ) -> dict:
        permissions: list[str] = payload.get("permissions", [])
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required.",
            )

        return payload

    return _dependency


def require_admin(
    payload: Annotated[dict, Depends(get_verified_payload)],
) -> dict:
    """FastAPI dependency enforcing the application's required role.

    This is the single guard used by every protected route. It gates on the
    Auth0 **role** carried in the ``ROLES_CLAIM`` claim (configured centrally
    via ``REQUIRED_ROLE``), matching the frontend's authorization check so a
    single Auth0 role grants access to both. Routes depend on ``require_admin``
    and never name the role themselves.

    Raises:
        HTTP 401 — token missing, malformed, expired, or signature invalid.
        HTTP 403 — token valid but the required role is absent.
    """
    claim = payload.get(ROLES_CLAIM)
    roles: list[str] = claim if isinstance(claim, list) else []
    if REQUIRED_ROLE not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{REQUIRED_ROLE}' required.",
        )
    return payload


def get_raw_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
) -> str:
    """Return the raw Bearer token string from the Authorization header.

    Use this in routes that need to forward or exchange the user's token for
    a downstream API call (e.g. via ``token_exchange.get_monitoring_token``).
    Combine with ``require_admin`` to ensure the token is validated first:

        @router.post("/some-endpoint")
        async def handler(
            _: dict = Depends(require_admin),
            raw_token: str = Depends(get_raw_token),
        ):
            monitoring_token = await get_monitoring_token(raw_token)
            ...
    """
    return credentials.credentials
