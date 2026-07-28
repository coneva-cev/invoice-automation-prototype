"""Tests for the central admin guard (require_admin).

The default ``client`` fixture overrides verification to inject an admin
payload, so these tests build their own clients to exercise the real guard
behaviour: missing token, and a valid token that lacks the required role.

The app gates on an Auth0 **role** (in the ``ROLES_CLAIM`` claim), matching the
frontend, rather than the API ``permissions`` claim.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies.auth import (
    REQUIRED_ROLE,
    ROLES_CLAIM,
    get_verified_payload,
)
from app.main import app


def test_required_role_default():
    """The centrally-configured role defaults to 'Invoice Automation Admin'."""
    assert REQUIRED_ROLE == "Invoice Automation Admin"


def test_protected_route_without_token_is_401():
    """No Authorization header -> HTTPBearer rejects with 401/403 before logic."""
    # Use a bare client with no dependency override.
    with TestClient(app) as bare:
        r = bare.post("/api/upload/classify")
    assert r.status_code in (401, 403)


def test_protected_route_without_role_is_403():
    """A valid token lacking the required role is forbidden."""
    app.dependency_overrides[get_verified_payload] = lambda: {
        "sub": "test|non-admin",
        ROLES_CLAIM: ["Some Other Role"],  # not the required role
    }
    try:
        with TestClient(app) as no_admin:
            r = no_admin.post("/api/upload/classify")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 403
    assert REQUIRED_ROLE in r.json()["detail"]


def test_protected_route_with_role_is_allowed():
    """A token carrying the required role passes the guard."""
    app.dependency_overrides[get_verified_payload] = lambda: {
        "sub": "test|admin",
        ROLES_CLAIM: [REQUIRED_ROLE],
    }
    try:
        with TestClient(app) as admin:
            # Empty file list -> guard passes, handler returns its own 4xx.
            r = admin.post("/api/upload/classify")
    finally:
        app.dependency_overrides.clear()
    # Not 401/403 proves we got past the auth guard.
    assert r.status_code not in (401, 403)
