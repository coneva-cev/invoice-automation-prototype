"""Real email delivery via the SendGrid v3 Mail Send API.

Implemented with ``httpx`` (already a dependency) rather than the SendGrid SDK
to avoid an extra dependency and keep full control over the request body,
including sandbox mode (validate the request against the account without
delivering).

Enable by setting in the environment:
    EMAIL_BACKEND=sendgrid
    SENDGRID_API_KEY=SG.xxxxx
    EMAIL_FROM="coneva <noreply@coneva.com>"
    SENDGRID_SANDBOX=true    # optional: validate-only, never deliver
"""

from __future__ import annotations

import base64
from email.utils import parseaddr

import httpx

from .models import DraftStatus, OutboundEmail, SendResult

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"


class SendGridSender:
    def __init__(
        self,
        api_key: str,
        sender_from: str,
        sandbox: bool = False,
        reply_to: str | None = None,
    ):
        self.api_key = api_key
        self.sender_name, self.sender_email = parseaddr(sender_from)
        self.sandbox = sandbox
        # Address customers reply to (e.g. support inbox), if configured.
        _, self.reply_to_email = parseaddr(reply_to or "")

    def _payload(self, email: OutboundEmail) -> dict:
        personalization: dict = {"to": [{"email": e} for e in email.to]}
        if email.cc:
            personalization["cc"] = [{"email": e} for e in email.cc]
        if email.bcc:
            personalization["bcc"] = [{"email": e} for e in email.bcc]

        payload: dict = {
            "personalizations": [personalization],
            "from": {"email": self.sender_email, "name": self.sender_name or None},
            "subject": email.subject,
            "content": [{"type": "text/html", "value": email.html}],
        }
        if self.reply_to_email:
            payload["reply_to"] = {"email": self.reply_to_email}
        if email.attachments:
            payload["attachments"] = [
                {
                    "content": base64.b64encode(att.content).decode("ascii"),
                    "filename": att.filename,
                    "type": att.content_type,
                    "disposition": "attachment",
                }
                for att in email.attachments
            ]
        if self.sandbox:
            payload["mail_settings"] = {"sandbox_mode": {"enable": True}}
        return payload

    def send(self, email: OutboundEmail) -> SendResult:
        try:
            resp = httpx.post(
                _SENDGRID_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=self._payload(email),
                timeout=30,
            )
        except httpx.HTTPError as exc:
            return SendResult(
                draft_id=email.draft_id,
                sent=False,
                status=DraftStatus.FAILED,
                detail=f"Transport error: {exc}",
            )

        if resp.status_code in (200, 202):
            mode = " (sandbox)" if self.sandbox else ""
            return SendResult(
                draft_id=email.draft_id,
                sent=True,
                status=DraftStatus.SENT,
                detail=f"SendGrid accepted{mode} (HTTP {resp.status_code}).",
            )
        return SendResult(
            draft_id=email.draft_id,
            sent=False,
            status=DraftStatus.FAILED,
            detail=f"SendGrid error HTTP {resp.status_code}: {resp.text[:300]}",
        )
