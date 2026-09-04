"""Domain models for the email-draft + send pipeline (steps 4/5).

An ``EmailDraft`` is the reviewable object generated from a processed batch:
one draft per (customer, document-category). Because email bodies are fixed
per category (INVOICE vs GUTSCHRIFT), a customer whose batch contains both an
invoice and a Gutschrift yields two drafts so each rendered body is
unambiguous.

Drafts carry attachments *by reference* (``doc_id``) — the PDF bytes already
live in the ``BatchStore``; they are only materialized at send time into an
``OutboundEmail``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DraftStatus(str, Enum):
    READY = "READY"  # matched recipient, sendable
    BLOCKED = "BLOCKED"  # no recipient / other reason it can't be sent
    SENT = "SENT"  # successfully sent
    FAILED = "FAILED"  # send attempted but failed


class DraftAttachment(BaseModel):
    """A PDF attachment, referenced by its stored id (bytes fetched lazily)."""

    doc_id: str
    filename: str
    category: str  # Category value of the document
    subtype: str | None = None


class EmailDraft(BaseModel):
    """A reviewable, per-category email for one customer.

    ``html`` is the rendered fixed-template body (regenerated on demand, never
    user-edited). Editable fields are ``to``, ``cc`` and ``subject`` only.
    """

    draft_id: str
    batch_id: str
    category: str  # INVOICE | GUTSCHRIFT | UNKNOWN — which fixed template
    unternehmen: str | None = None
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str = ""
    html: str = ""
    attachments: list[DraftAttachment] = Field(default_factory=list)
    status: DraftStatus = DraftStatus.READY
    warnings: list[str] = Field(default_factory=list)
    # send bookkeeping
    error: str | None = None


class DraftPatch(BaseModel):
    """User edits to a draft — recipients/subject only (body is fixed)."""

    to: list[str] | None = None
    cc: list[str] | None = None
    subject: str | None = None


class EmailAttachment(BaseModel):
    """A resolved attachment with real bytes, ready for the mail transport."""

    filename: str
    content: bytes
    content_type: str = "application/pdf"


class OutboundEmail(BaseModel):
    """A fully-resolved email handed to an ``EmailSender``."""

    draft_id: str
    to: list[str]
    cc: list[str]
    bcc: list[str] = Field(default_factory=list)
    subject: str
    html: str
    attachments: list[EmailAttachment] = Field(default_factory=list)


class SendResult(BaseModel):
    """Per-draft outcome of a send attempt."""

    draft_id: str
    sent: bool
    status: DraftStatus
    detail: str | None = None
