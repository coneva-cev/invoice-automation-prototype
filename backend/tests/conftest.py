"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load Auth0 config from app/.env before importing any app module that reads
# os.environ at import time (mirrors what app.main does at runtime). Falls back
# to safe defaults so the suite runs even without a populated .env (e.g. in CI).
_ENV_FILE = Path(__file__).resolve().parent.parent / "app" / ".env"
load_dotenv(_ENV_FILE)
os.environ.setdefault("AUTH0_DOMAIN", "test.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://invoice-automation/api")
os.environ.setdefault("AUTH0_CLIENT_ID", "test-client-id")
os.environ.setdefault("AUTH0_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("MONITORING_API_AUDIENCE", "https://monitoring.conevaconnect.com/api")
os.environ.setdefault("MONITORING_API_BASE_URL", "https://portal.dev-conevacloud.com")
os.environ.setdefault("MONITORING_API_BULK_UPLOAD_SCOPE", "9")

from app.dependencies.auth import get_verified_payload
from app.main import app

_SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(scope="session")
def client() -> TestClient:
    # Bypass real Auth0 verification: pretend every request carries a valid
    # token with the required admin role. Endpoint auth wiring is exercised
    # separately; these tests focus on business logic.
    from app.dependencies.auth import REQUIRED_ROLE, ROLES_CLAIM

    app.dependency_overrides[get_verified_payload] = lambda: {
        "sub": "test|user",
        ROLES_CLAIM: [REQUIRED_ROLE],
    }
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def pdf_upload():
    """Build a list of ('files', (name, bytes, ct)) tuples for multipart."""

    def _build(named_bytes: dict[str, bytes]) -> list[tuple]:
        return [
            ("files", (name, data, "application/pdf"))
            for name, data in named_bytes.items()
        ]

    return _build


@pytest.fixture
def mapping_upload():
    """Build the ('mapping_file', ...) multipart tuple."""

    def _build(data: bytes, name: str = "mapping.xlsx") -> tuple:
        return (
            "mapping_file",
            (
                name,
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )

    return _build


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return _SAMPLES


def has_samples() -> bool:
    return _SAMPLES.exists() and any(_SAMPLES.rglob("*.pdf"))
