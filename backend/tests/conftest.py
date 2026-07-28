"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

_SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


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
