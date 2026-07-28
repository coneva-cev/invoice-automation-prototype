"""Pluggable email transport, selected by the ``EMAIL_BACKEND`` env var.

Backends
--------
* ``console`` (default) — local emulation. Records what *would* be sent and
  optionally writes ``.eml`` files to ``EMAIL_OUTBOX_DIR``. Never delivers.
* ``sendgrid`` — real delivery via SendGrid (see :mod:`.sendgrid_backend`).

All backends implement :class:`EmailSender.send`, so the API layer is
transport-agnostic.
"""

from __future__ import annotations

import os
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from .config import resolve_email_config
from .models import DraftStatus, OutboundEmail, SendResult


class EmailSender(Protocol):
    def send(self, email: OutboundEmail) -> SendResult: ...


def _build_eml(email: OutboundEmail, sender_from: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender_from
    msg["To"] = ", ".join(email.to)
    if email.cc:
        msg["Cc"] = ", ".join(email.cc)
    msg["Subject"] = email.subject
    msg.set_content("This email requires an HTML-capable client.")
    msg.add_alternative(email.html, subtype="html")
    for att in email.attachments:
        maintype, _, subtype = att.content_type.partition("/")
        msg.add_attachment(
            att.content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att.filename,
        )
    return bytes(msg)


class ConsoleSender:
    """Local emulation: never delivers. Optionally dumps .eml files."""

    def __init__(self, sender_from: str, outbox_dir: str | None = None):
        self.sender_from = sender_from
        self.outbox_dir = Path(outbox_dir) if outbox_dir else None
        self.sent: list[OutboundEmail] = []  # in-memory record for inspection

    def send(self, email: OutboundEmail) -> SendResult:
        self.sent.append(email)
        if self.outbox_dir:
            self.outbox_dir.mkdir(parents=True, exist_ok=True)
            eml = _build_eml(email, self.sender_from)
            (self.outbox_dir / f"{email.draft_id}.eml").write_bytes(eml)
        detail = (
            f"[console] would send to {', '.join(email.to)}"
            f" ({len(email.attachments)} attachment(s))"
        )
        return SendResult(
            draft_id=email.draft_id,
            sent=True,
            status=DraftStatus.SENT,
            detail=detail,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_sender: EmailSender | None = None


def _make_sender() -> EmailSender:
    # APP_ENV picks the backend/sandbox defaults; explicit vars override.
    cfg = resolve_email_config()
    sender_from = os.environ.get("EMAIL_FROM", "coneva <noreply@coneva.com>")

    if cfg.backend == "sendgrid":
        from .sendgrid_backend import SendGridSender

        return SendGridSender(
            api_key=os.environ["SENDGRID_API_KEY"],
            sender_from=sender_from,
            sandbox=cfg.sandbox,
        )
    if cfg.backend == "smtp":
        from .smtp_backend import SmtpSender

        return SmtpSender(
            host=os.environ.get("SMTP_HOST", "localhost"),
            port=int(os.environ.get("SMTP_PORT", "1025")),
            sender_from=sender_from,
            username=os.environ.get("SMTP_USERNAME") or None,
            password=os.environ.get("SMTP_PASSWORD") or None,
            use_starttls=os.environ.get("SMTP_STARTTLS", "false").lower() == "true",
        )
    # default: console
    return ConsoleSender(
        sender_from=sender_from,
        outbox_dir=os.environ.get("EMAIL_OUTBOX_DIR"),
    )


def get_sender() -> EmailSender:
    global _sender
    if _sender is None:
        _sender = _make_sender()
    return _sender


def reset_sender() -> None:
    """Clear the cached sender (used by tests that swap env/backends)."""
    global _sender
    _sender = None
