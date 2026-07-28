"""Email draft generation + sending (pipeline steps 4/5).

Generates one reviewable ``EmailDraft`` per (customer, document category) from
a processed batch, renders a fixed HTML body per category, and sends via a
pluggable backend selected by the ``EMAIL_BACKEND`` env var (``console`` for
local emulation, ``sendgrid`` for real delivery).
"""

from .build import build_drafts
from .models import (
    DraftAttachment,
    DraftPatch,
    DraftStatus,
    EmailAttachment,
    EmailDraft,
    OutboundEmail,
    SendResult,
)
from .sender import get_sender

__all__ = [
    "build_drafts",
    "get_sender",
    "DraftAttachment",
    "DraftPatch",
    "DraftStatus",
    "EmailAttachment",
    "EmailDraft",
    "OutboundEmail",
    "SendResult",
]
