"""Tests for the Portal bulk-upload proxy (POST /api/documents/batch/{id}/bulk-upload).

External calls are mocked: the Auth0 token exchange (``get_monitoring_token``)
and the monitoring API HTTP PUT. A real batch is seeded via /api/upload/process
so the server-side zip build path is exercised.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.dependencies.auth import get_verified_payload
from app.main import app
from fastapi.testclient import TestClient

from .factories import MappingRow, gutschrift_pdf, invoice_pdf, make_mapping_xlsx

# The bulk-upload route additionally depends on get_raw_token (real HTTPBearer),
# so requests must carry an Authorization header. The token value is irrelevant
# because verification (get_verified_payload) is overridden in the fixture.
_AUTH = {"Authorization": "Bearer test-token"}


def _seed_batch(client, pdf_upload, mapping_upload) -> tuple[str, list[str]]:
    """Create a batch via /api/upload/process; return (batch_id, filenames)."""
    pdfs = {
        "a.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
        "b.pdf": gutschrift_pdf(malo="50000000002"),
    }
    files = pdf_upload(pdfs)
    files.append(
        mapping_upload(
            make_mapping_xlsx(
                [
                    MappingRow(["50000000001"], "Acme GmbH", "a@acme.example"),
                    MappingRow(["50000000002"], "Erz GmbH", "e@erz.example"),
                ]
            )
        )
    )
    r = client.post("/api/upload/process", files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    return data["batch_id"], list(pdfs.keys())


class _FakeResponse:
    """Minimal stand-in for httpx.Response for the monitoring PUT."""

    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.content = json.dumps(body).encode()
        self.headers = {"content-type": "application/json"}


def _patch_monitoring(monkeypatch, *, response=None, raise_exc=None):
    """Patch token exchange + the monitoring PUT used by the documents router."""

    async def _fake_token():
        return "fake-monitoring-token"

    monkeypatch.setattr(
        "app.routers.documents.get_monitoring_token", _fake_token
    )

    captured: dict = {}

    async def _fake_put(self, url, **kwargs):  # noqa: ANN001
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["files"] = kwargs.get("files", {})
        if raise_exc is not None:
            raise raise_exc
        return response

    monkeypatch.setattr(httpx.AsyncClient, "put", _fake_put)
    return captured


# --------------------------------------------------------------------------- #
# Happy path + pass-through
# --------------------------------------------------------------------------- #
def test_bulk_upload_happy_path(client, pdf_upload, mapping_upload, monkeypatch):
    batch_id, _ = _seed_batch(client, pdf_upload, mapping_upload)
    body = {"a.pdf": "OK", "b.pdf": "OK"}
    captured = _patch_monitoring(
        monkeypatch, response=_FakeResponse(200, body)
    )

    r = client.post(f"/api/documents/batch/{batch_id}/bulk-upload", headers=_AUTH)

    assert r.status_code == 200
    assert r.json() == body
    # Sent as a single zip, email notification disabled, correct scope header.
    assert "sendEmailNotification=false" in captured["url"]
    assert captured["headers"]["authorization-scope"]  # set from env
    assert "file" in captured["files"]


def test_bulk_upload_partial_errors_passthrough(
    client, pdf_upload, mapping_upload, monkeypatch
):
    batch_id, _ = _seed_batch(client, pdf_upload, mapping_upload)
    body = {
        "a.pdf": "OK",
        "b.pdf": "ERROR: No tenant found with malo: 50000000002",
    }
    _patch_monitoring(monkeypatch, response=_FakeResponse(200, body))

    r = client.post(f"/api/documents/batch/{batch_id}/bulk-upload", headers=_AUTH)

    assert r.status_code == 200
    assert r.json()["b.pdf"].startswith("ERROR")


# --------------------------------------------------------------------------- #
# Error forwarding (4xx / 5xx / network) + 404
# --------------------------------------------------------------------------- #
def test_bulk_upload_forwards_4xx(client, pdf_upload, mapping_upload, monkeypatch):
    batch_id, _ = _seed_batch(client, pdf_upload, mapping_upload)
    _patch_monitoring(
        monkeypatch, response=_FakeResponse(400, {"error": "bad request"})
    )

    r = client.post(f"/api/documents/batch/{batch_id}/bulk-upload", headers=_AUTH)

    assert r.status_code == 400
    assert r.json()["error"] == "bad request"


def test_bulk_upload_forwards_5xx(client, pdf_upload, mapping_upload, monkeypatch):
    batch_id, _ = _seed_batch(client, pdf_upload, mapping_upload)
    _patch_monitoring(
        monkeypatch, response=_FakeResponse(503, {"error": "unavailable"})
    )

    r = client.post(f"/api/documents/batch/{batch_id}/bulk-upload", headers=_AUTH)

    assert r.status_code == 503


def test_bulk_upload_network_error_is_502(
    client, pdf_upload, mapping_upload, monkeypatch
):
    batch_id, _ = _seed_batch(client, pdf_upload, mapping_upload)
    _patch_monitoring(
        monkeypatch, raise_exc=httpx.ConnectError("boom")
    )

    r = client.post(f"/api/documents/batch/{batch_id}/bulk-upload", headers=_AUTH)

    assert r.status_code == 502


def test_bulk_upload_unknown_batch_404(client, monkeypatch):
    _patch_monitoring(monkeypatch, response=_FakeResponse(200, {}))
    r = client.post("/api/documents/batch/deadbeef/bulk-upload", headers=_AUTH)
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Validation filtering: only matched documents are uploaded by default
# --------------------------------------------------------------------------- #
def _seed_mixed_batch(client, pdf_upload, mapping_upload) -> str:
    """Seed a batch with one matched and one unmatched (no mapping) document."""
    pdfs = {
        "matched.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
        "orphan.pdf": invoice_pdf("TARIF_ONLY", malo="59999999999"),
    }
    files = pdf_upload(pdfs)
    files.append(
        mapping_upload(
            make_mapping_xlsx(
                [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")]
            )
        )
    )
    r = client.post("/api/upload/process", files=files)
    assert r.status_code == 200, r.text
    return r.json()["batch_id"]


def _zip_names(captured) -> set[str]:
    import io
    import zipfile

    _, content, _ = captured["files"]["file"]
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return set(zf.namelist())


def test_bulk_upload_excludes_unmatched_by_default(
    client, pdf_upload, mapping_upload, monkeypatch
):
    batch_id = _seed_mixed_batch(client, pdf_upload, mapping_upload)
    captured = _patch_monitoring(
        monkeypatch, response=_FakeResponse(200, {"matched.pdf": "OK"})
    )

    r = client.post(f"/api/documents/batch/{batch_id}/bulk-upload", headers=_AUTH)

    assert r.status_code == 200
    # Only the validated (matched) document is in the uploaded zip.
    assert _zip_names(captured) == {"matched.pdf"}


def test_bulk_upload_includes_unmatched_when_requested(
    client, pdf_upload, mapping_upload, monkeypatch
):
    batch_id = _seed_mixed_batch(client, pdf_upload, mapping_upload)
    captured = _patch_monitoring(
        monkeypatch,
        response=_FakeResponse(200, {"matched.pdf": "OK", "orphan.pdf": "OK"}),
    )

    r = client.post(
        f"/api/documents/batch/{batch_id}/bulk-upload?include_unmatched=true",
        headers=_AUTH,
    )

    assert r.status_code == 200
    assert _zip_names(captured) == {"matched.pdf", "orphan.pdf"}


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def test_bulk_upload_requires_admin():
    # Temporarily replace the admin override with a non-admin payload, then
    # restore it so the shared session client fixture keeps working.
    previous = app.dependency_overrides.get(get_verified_payload)
    app.dependency_overrides[get_verified_payload] = lambda: {
        "sub": "test|non-admin",
        "coneva/roles": ["Some Other Role"],
    }
    try:
        with TestClient(app) as no_admin:
            r = no_admin.post(
                "/api/documents/batch/whatever/bulk-upload", headers=_AUTH
            )
    finally:
        if previous is not None:
            app.dependency_overrides[get_verified_payload] = previous
        else:
            app.dependency_overrides.pop(get_verified_payload, None)
    assert r.status_code == 403
