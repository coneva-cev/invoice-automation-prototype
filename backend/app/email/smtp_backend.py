"""SMTP email delivery — used for integration testing against a mail catcher.

Points at a plain SMTP server (e.g. Mailpit / MailHog running locally) so the
full send path is exercised — MIME assembly, recipients, PDF attachments — but
messages land in the catcher's inbox instead of a real mailbox.

Enable with:
    EMAIL_BACKEND=smtp
    EMAIL_FROM="coneva <noreply@coneva.com>"
    SMTP_HOST=localhost      # default
    SMTP_PORT=1025           # default (Mailpit/MailHog SMTP port)
    SMTP_USERNAME=...        # optional
    SMTP_PASSWORD=...        # optional
    SMTP_STARTTLS=false      # optional
"""

from __future__ import annotations

import smtplib

from .models import DraftStatus, OutboundEmail, SendResult


class SmtpSender:
    def __init__(
        self,
        host: str,
        port: int,
        sender_from: str,
        username: str | None = None,
        password: str | None = None,
        use_starttls: bool = False,
    ):
        self.host = host
        self.port = port
        self.sender_from = sender_from
        self.username = username
        self.password = password
        self.use_starttls = use_starttls

    def send(self, email: OutboundEmail) -> SendResult:
        # Reuse the MIME builder from the console sender.
        from .sender import _build_eml

        message = _build_eml(email, self.sender_from)
        recipients = list(email.to) + list(email.cc)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                if self.use_starttls:
                    smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password or "")
                # sendmail wants the envelope-from address only.
                from email.utils import parseaddr

                _, from_addr = parseaddr(self.sender_from)
                smtp.sendmail(from_addr, recipients, message)
        except (smtplib.SMTPException, OSError) as exc:
            return SendResult(
                draft_id=email.draft_id,
                sent=False,
                status=DraftStatus.FAILED,
                detail=f"SMTP error: {exc}",
            )
        return SendResult(
            draft_id=email.draft_id,
            sent=True,
            status=DraftStatus.SENT,
            detail=f"Sent via SMTP {self.host}:{self.port}.",
        )
