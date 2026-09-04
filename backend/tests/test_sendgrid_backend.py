"""Unit tests for the SendGrid payload construction (reply-to, recipients)."""

from __future__ import annotations

from app.email.models import OutboundEmail
from app.email.sendgrid_backend import SendGridSender


def _email(**kw) -> OutboundEmail:
    base = dict(
        draft_id="d1",
        to=["cust@example.com"],
        cc=[],
        bcc=[],
        subject="s",
        html="<p>hi</p>",
    )
    base.update(kw)
    return OutboundEmail(**base)


def test_reply_to_added_when_configured():
    sender = SendGridSender(
        api_key="k",
        sender_from="coneva <noreply@coneva.com>",
        reply_to="service@conevasupport.com",
    )
    payload = sender._payload(_email())
    assert payload["reply_to"] == {"email": "service@conevasupport.com"}


def test_reply_to_omitted_when_not_configured():
    sender = SendGridSender(api_key="k", sender_from="coneva <noreply@coneva.com>")
    payload = sender._payload(_email())
    assert "reply_to" not in payload


def test_reply_to_parses_display_name_form():
    sender = SendGridSender(
        api_key="k",
        sender_from="coneva <noreply@coneva.com>",
        reply_to="coneva Support <service@conevasupport.com>",
    )
    payload = sender._payload(_email())
    assert payload["reply_to"] == {"email": "service@conevasupport.com"}


def test_recipients_and_bcc_in_personalization():
    sender = SendGridSender(api_key="k", sender_from="coneva <n@coneva.com>")
    payload = sender._payload(
        _email(to=["a@x.com"], cc=["c@x.com"], bcc=["billing@coneva.com"])
    )
    p = payload["personalizations"][0]
    assert p["to"] == [{"email": "a@x.com"}]
    assert p["cc"] == [{"email": "c@x.com"}]
    assert p["bcc"] == [{"email": "billing@coneva.com"}]
