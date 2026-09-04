"""Tests for email draft generation, review, and (console) sending.

Validates the core promise: on a test run, each draft carries the RIGHT
recipients and the RIGHT attachments, split per document category, with a
rendered HTML body listing the attached files.
"""

from __future__ import annotations

from app.email import build_drafts
from app.email.sender import ConsoleSender, reset_sender

from .factories import (
    MappingRow,
    gutschrift_pdf,
    invoice_pdf,
    make_mapping_xlsx,
)


def _process(client, pdf_upload, mapping_upload, pdfs, rows):
    files = pdf_upload(pdfs)
    files.append(mapping_upload(make_mapping_xlsx(rows)))
    r = client.post("/api/upload/process", files=files)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# build_drafts (pure logic)
# --------------------------------------------------------------------------- #
def test_build_drafts_splits_by_category(client, pdf_upload, mapping_upload):
    """One customer with an invoice + a Gutschrift => two drafts (one each)."""
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "gut.pdf": gutschrift_pdf(malo="50000000001"),
        },
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    drafts = build_drafts(data)
    cats = sorted(d.category for d in drafts)
    assert cats == ["GUTSCHRIFT", "INVOICE"]
    for d in drafts:
        assert d.to == ["a@acme.example"]
        assert len(d.attachments) == 1


def test_build_drafts_right_files_per_recipient(
    client, pdf_upload, mapping_upload
):
    """Each draft's attachments must be exactly that customer's docs."""
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "acme1.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "acme2.pdf": invoice_pdf("FIXPRICE", malo="50000000002"),
            "erz.pdf": gutschrift_pdf(malo="50000000009"),
        },
        [
            MappingRow(
                ["50000000001", "50000000002"], "Acme GmbH", "a@acme.example"
            ),
            MappingRow(["50000000009"], "Erzeuger GmbH", "e@erz.example"),
        ],
    )
    drafts = build_drafts(data)
    by_to = {d.to[0]: d for d in drafts}

    assert set(by_to) == {"a@acme.example", "e@erz.example"}
    acme_files = {a.filename for a in by_to["a@acme.example"].attachments}
    assert acme_files == {"acme1.pdf", "acme2.pdf"}
    erz_files = {a.filename for a in by_to["e@erz.example"].attachments}
    assert erz_files == {"erz.pdf"}


def test_build_drafts_html_lists_attachments(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001")},
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    draft = build_drafts(data)[0]
    assert "inv.pdf" in draft.html
    assert draft.category == "INVOICE"


def test_build_drafts_skips_unmatched(client, pdf_upload, mapping_upload):
    """A PDF with no mapping entry yields no draft."""
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"orphan.pdf": invoice_pdf("TARIF_ONLY", malo="59999999999")},
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    assert build_drafts(data) == []


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def test_generate_and_list_drafts(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001")},
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    batch_id = data["batch_id"]

    r = client.post(f"/api/email/batch/{batch_id}/drafts")
    assert r.status_code == 200, r.text
    gen = r.json()
    assert gen["total"] == 1
    assert gen["ready"] == 1
    draft_id = gen["drafts"][0]["draft_id"]

    r = client.get(f"/api/email/batch/{batch_id}/drafts")
    assert r.status_code == 200
    assert r.json()["drafts"][0]["draft_id"] == draft_id


def test_preview_html_and_attachment(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001")},
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    batch_id = data["batch_id"]
    gen = client.post(f"/api/email/batch/{batch_id}/drafts").json()
    draft = gen["drafts"][0]
    draft_id = draft["draft_id"]
    doc_id = draft["attachments"][0]["doc_id"]

    r = client.get(f"/api/email/batch/{batch_id}/drafts/{draft_id}/preview")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "inv.pdf" in r.text

    r = client.get(
        f"/api/email/batch/{batch_id}/drafts/{draft_id}/attachment/{doc_id}"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_patch_recipients(client, pdf_upload, mapping_upload):
    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {"inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001")},
        [MappingRow(["50000000001"], "Acme GmbH", "a@acme.example")],
    )
    batch_id = data["batch_id"]
    gen = client.post(f"/api/email/batch/{batch_id}/drafts").json()
    draft_id = gen["drafts"][0]["draft_id"]

    r = client.patch(
        f"/api/email/batch/{batch_id}/drafts/{draft_id}",
        json={"to": ["new@acme.example"], "subject": "Custom subject"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["to"] == ["new@acme.example"]
    assert body["subject"] == "Custom subject"
    assert "Custom subject" in body["html"]


def test_send_via_console_backend(client, pdf_upload, mapping_upload, monkeypatch):
    # Force the console backend and capture what would be sent.
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "live")
    reset_sender()

    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "gut.pdf": gutschrift_pdf(malo="50000000002"),
        },
        [
            MappingRow(["50000000001"], "Acme GmbH", "a@acme.example"),
            MappingRow(["50000000002"], "Erz GmbH", "e@erz.example"),
        ],
    )
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "sendgrid_live"}},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sent"] == 2
    assert out["failed"] == 0
    assert all(res["status"] == "SENT" for res in out["results"])

    # Listing again reflects SENT status.
    listed = client.get(f"/api/email/batch/{batch_id}/drafts").json()
    assert all(d["status"] == "SENT" for d in listed["drafts"])
    reset_sender()


def test_send_only_selected_drafts(client, pdf_upload, mapping_upload, monkeypatch):
    """With draft_ids provided, only those drafts are sent; others untouched."""
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "live")
    reset_sender()

    data = _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "gut.pdf": gutschrift_pdf(malo="50000000002"),
        },
        [
            MappingRow(["50000000001"], "Acme GmbH", "a@acme.example"),
            MappingRow(["50000000002"], "Erz GmbH", "e@erz.example"),
        ],
    )
    batch_id = data["batch_id"]
    gen = client.post(f"/api/email/batch/{batch_id}/drafts").json()
    assert gen["total"] == 2
    chosen = gen["drafts"][0]["draft_id"]

    # Send only the chosen draft.
    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"draft_ids": [chosen], "destination": {"kind": "sendgrid_live"}},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sent"] == 1
    assert len(out["results"]) == 1
    assert out["results"][0]["draft_id"] == chosen

    # The other draft remains unsent (READY); only the chosen one is SENT.
    listed = client.get(f"/api/email/batch/{batch_id}/drafts").json()
    by_id = {d["draft_id"]: d["status"] for d in listed["drafts"]}
    assert by_id[chosen] == "SENT"
    assert sum(1 for s in by_id.values() if s == "SENT") == 1
    assert sum(1 for s in by_id.values() if s == "READY") == 1
    reset_sender()


def test_resend_requires_explicit_selection(
    client, pdf_upload, mapping_upload, monkeypatch
):
    """A SENT draft is skipped on a blanket send but re-sent when selected."""
    from app.email.sender import get_sender

    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "live")
    reset_sender()

    data = _process_two(client, pdf_upload, mapping_upload)
    batch_id = data["batch_id"]
    gen = client.post(f"/api/email/batch/{batch_id}/drafts").json()
    one = gen["drafts"][0]["draft_id"]

    # First send the chosen draft.
    r1 = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"draft_ids": [one], "destination": {"kind": "sendgrid_live"}},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["sent"] == 1
    first_count = len(get_sender().sent)

    # Blanket send (no draft_ids) must NOT re-send the already-sent draft.
    r2 = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "sendgrid_live"}},
    )
    assert r2.status_code == 200, r2.text
    already = [x for x in r2.json()["results"] if x["draft_id"] == one]
    assert already and already[0]["detail"] == "Already sent."
    # The other (READY) draft did get sent, but not the SENT one.
    assert len(get_sender().sent) == first_count + 1

    # Explicitly selecting the SENT draft re-sends it.
    before = len(get_sender().sent)
    r3 = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"draft_ids": [one], "destination": {"kind": "sendgrid_live"}},
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["sent"] == 1
    assert len(get_sender().sent) == before + 1  # actually re-sent
    reset_sender()


def test_console_sender_attaches_real_bytes():
    """The console sender records the exact attachment bytes."""
    from app.email.models import EmailAttachment, OutboundEmail

    sender = ConsoleSender(sender_from="x@y.z")
    email = OutboundEmail(
        draft_id="d1",
        to=["a@b.c"],
        cc=[],
        subject="s",
        html="<p>hi</p>",
        attachments=[EmailAttachment(filename="f.pdf", content=b"%PDF-1.4 test")],
    )
    res = sender.send(email)
    assert res.sent
    assert sender.sent[0].attachments[0].content == b"%PDF-1.4 test"


def _process_two(client, pdf_upload, mapping_upload):
    return _process(
        client,
        pdf_upload,
        mapping_upload,
        {
            "inv.pdf": invoice_pdf("TARIF_ONLY", malo="50000000001"),
            "gut.pdf": gutschrift_pdf(malo="50000000002"),
        },
        [
            MappingRow(["50000000001"], "Acme GmbH", "a@acme.example"),
            MappingRow(["50000000002"], "Erz GmbH", "e@erz.example"),
        ],
    )


def test_sendgrid_without_key_returns_clear_error(
    client, pdf_upload, mapping_upload, monkeypatch
):
    """Selecting a SendGrid destination with no API key => clean 400, not 500."""
    monkeypatch.setenv("EMAIL_MODE", "live")
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)  # exercise the real path
    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)
    reset_sender()

    data = _process_two(client, pdf_upload, mapping_upload)
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "sendgrid_sandbox"}},
    )
    assert r.status_code == 400, r.text
    assert "SENDGRID_API_KEY" in r.json()["detail"]
    reset_sender()


def test_test_mode_replaces_all_recipients(
    client, pdf_upload, mapping_upload, monkeypatch
):
    """In test mode, every email's To/Cc/Bcc is replaced with the test address."""
    from app.email.sender import get_sender

    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "test")
    monkeypatch.setenv("EMAIL_BCC", "billing@coneva.com")
    reset_sender()

    data = _process_two(client, pdf_upload, mapping_upload)
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "mailpit", "replace_to": "tester@coneva.com"}},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"]["app_mode"] == "test"
    assert out["mode"]["replaced_to"] == "tester@coneva.com"
    assert out["mode"]["delivers_real"] is False

    sent = get_sender().sent  # ConsoleSender records outbound emails
    assert sent, "no emails recorded"
    for msg in sent:
        assert msg.to == ["tester@coneva.com"]
        assert msg.cc == []
        assert msg.bcc == []  # billing BCC also removed in test mode
        # Neither the real recipient nor the billing BCC may appear anywhere.
        assert "acme.example" not in msg.to + msg.cc + msg.bcc
        assert "billing@coneva.com" not in msg.to + msg.cc + msg.bcc
        # Subject annotated with the intended recipient for verification.
        assert msg.subject.startswith("[TEST \u2192 ")
        assert "TEST MODE" in msg.html
    reset_sender()


def test_test_mode_rejects_non_coneva_and_sends_nothing(
    client, pdf_upload, mapping_upload, monkeypatch
):
    """A non-coneva replacement address is refused; nothing is sent (fail-closed)."""
    from app.email.sender import get_sender

    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "test")
    reset_sender()

    data = _process_two(client, pdf_upload, mapping_upload)
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "sendgrid_coneva", "replace_to": "me@gmail.com"}},
    )
    assert r.status_code == 400, r.text
    assert "must be an address in" in r.json()["detail"]
    assert get_sender().sent == []
    reset_sender()


def test_test_mode_fail_closed_without_replacement(
    client, pdf_upload, mapping_upload, monkeypatch
):
    """Test mode + no replacement address => send refused, nothing sent."""
    from app.email.sender import get_sender

    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "test")
    reset_sender()

    data = _process_two(client, pdf_upload, mapping_upload)
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "mailpit"}},
    )
    assert r.status_code == 400, r.text
    assert get_sender().sent == []
    reset_sender()


def test_test_mode_forbids_live_destination(
    client, pdf_upload, mapping_upload, monkeypatch
):
    """A test-mode instance can never select the live destination."""
    from app.email.sender import get_sender

    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "test")
    reset_sender()

    data = _process_two(client, pdf_upload, mapping_upload)
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "sendgrid_live"}},
    )
    assert r.status_code == 400, r.text
    assert get_sender().sent == []
    reset_sender()


def test_live_mode_keeps_real_recipients(
    client, pdf_upload, mapping_upload, monkeypatch
):
    """In live mode with the live destination, real recipients + BCC are kept."""
    from app.email.sender import get_sender

    monkeypatch.setenv("EMAIL_BACKEND", "console")
    monkeypatch.setenv("EMAIL_MODE", "live")
    monkeypatch.setenv("EMAIL_BCC", "billing@coneva.com")
    reset_sender()

    data = _process_two(client, pdf_upload, mapping_upload)
    batch_id = data["batch_id"]
    client.post(f"/api/email/batch/{batch_id}/drafts")

    r = client.post(
        f"/api/email/batch/{batch_id}/drafts/send",
        json={"destination": {"kind": "sendgrid_live"}},
    )
    assert r.status_code == 200, r.text
    mode = r.json()["mode"]
    assert mode["app_mode"] == "live"
    assert mode["delivers_real"] is True
    assert mode["replaced_to"] is None

    sent = get_sender().sent
    all_to = [addr for msg in sent for addr in msg.to]
    assert "a@acme.example" in all_to or "e@erz.example" in all_to
    for msg in sent:
        assert msg.bcc == ["billing@coneva.com"]
        assert not msg.subject.startswith("[TEST")
    reset_sender()
