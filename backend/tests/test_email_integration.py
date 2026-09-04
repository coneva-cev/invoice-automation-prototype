"""Integration test: send emails through a real SMTP transport into Mailpit.

Exercises the full send path (draft build -> attachment resolution -> MIME
assembly -> SMTP transmission) and asserts, via Mailpit's REST API, that the
right recipient received the right subject and the right PDF attachment.

Run it:
    docker compose -f docker-compose.mailpit.yml up -d
    ./backend/test.sh -m integration        # or: pytest -m integration

Auto-skips when Mailpit is not reachable, so normal/CI runs stay green.
"""

from __future__ import annotations

import httpx
import pytest

from app.email.sender import reset_sender

from .factories import MappingRow, invoice_pdf, make_mapping_xlsx

MAILPIT_API = "http://localhost:8025"
SMTP_HOST = "localhost"
SMTP_PORT = "1025"


def _mailpit_up() -> bool:
    try:
        r = httpx.get(f"{MAILPIT_API}/api/v1/info", timeout=2)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _mailpit_up(), reason="Mailpit not reachable on :8025"),
]


@pytest.fixture
def _clean_mailpit():
    # Clear before, force the SMTP backend at Mailpit, restore after.
    httpx.delete(f"{MAILPIT_API}/api/v1/messages", timeout=5)
    yield
    reset_sender()


def _process(client, pdf_upload, mapping_upload, pdfs, rows):
    files = pdf_upload(pdfs)
    files.append(mapping_upload(make_mapping_xlsx(rows)))
    r = client.post("/api/upload/process", files=files)
    assert r.status_code == 200, r.text
    return r.json()


def test_send_lands_in_mailpit_with_attachment(
    client, pdf_upload, mapping_upload, monkeypatch, _clean_mailpit
):
    monkeypatch.setenv("EMAIL_MODE", "test")
    monkeypatch.setenv("SMTP_HOST", SMTP_HOST)
    monkeypatch.setenv("SMTP_PORT", SMTP_PORT)
    monkeypatch.setenv("EMAIL_FROM", "coneva <noreply@coneva.test>")
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)
    reset_sender()

    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"acme_invoice.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001")},
        [MappingRow(["50000000001"], "Acme GmbH", "billing@acme.example")],
    )
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    # Test-mode Mailpit destination: recipient is replaced with a coneva address.
    resp = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "mailpit", "replace_to": "tester@coneva.com"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sent"] == 1

    # Query Mailpit for the captured message.
    messages = httpx.get(f"{MAILPIT_API}/api/v1/messages", timeout=5).json()
    assert messages["total"] >= 1
    msg_summary = messages["messages"][0]

    # Recipient was replaced with the coneva test address (not the real one).
    to_addrs = [t["Address"] for t in msg_summary["To"]]
    assert "tester@coneva.com" in to_addrs
    assert "billing@acme.example" not in to_addrs
    assert "Verbrauchsabrechnung" in msg_summary["Subject"]

    # Fetch full message to check the attachment.
    msg_id = msg_summary["ID"]
    full = httpx.get(f"{MAILPIT_API}/api/v1/message/{msg_id}", timeout=5).json()
    attachment_names = [a["FileName"] for a in full.get("Attachments", [])]
    assert "acme_invoice.pdf" in attachment_names
