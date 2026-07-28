"""Tests for the central admin-permission guard (require_admin).

The default ``client`` fixture overrides verification to inject an admin
payload, so these tests build their own clients to exercise the real guard
behaviour: missing token, and a valid token that lacks the required permission.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies.auth import REQUIRED_PERMISSION, get_verified_payload
from app.main import app


def test_required_permission_is_admin():
    """The centrally-configured permission is 'admin' (from REQUIRED_PERMISSION)."""
    assert REQUIRED_PERMISSION == "admin"


def test_protected_route_without_token_is_401():
    """No Authorization header -> HTTPBearer rejects with 401/403 before logic."""
    # Use a bare client with no dependency override.
    with TestClient(app) as bare:
        r = bare.post("/api/upload/classify")
    assert r.status_code in (401, 403)


def test_protected_route_without_permission_is_403():
    """A valid token lacking the required permission is forbidden."""
    app.dependency_overrides[get_verified_payload] = lambda: {
        "sub": "test|non-admin",
        "permissions": ["read-only"],  # not 'admin'
    }
    try:
        with TestClient(app) as no_admin:
            r = no_admin.post("/api/upload/classify")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 403
    assert REQUIRED_PERMISSION in r.json()["detail"]


def test_protected_route_with_permission_is_allowed():
    """A token carrying the required permission passes the guard."""
    app.dependency_overrides[get_verified_payload] = lambda: {
        "sub": "test|admin",
        "permissions": ["admin"],
    }
    try:
        with TestClient(app) as admin:
            # Empty file list -> guard passes, handler returns its own 400.
            r = admin.post("/api/upload/classify")
    finally:
        app.dependency_overrides.clear()
    # 422 (missing files field) proves we got past the auth guard, not 401/403.
    assert r.status_code not in (401, 403)
