"""Models for MaLo-based recipient mapping."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecipientMapping(BaseModel):
    """One mapping row = one customer (per category).

    A customer may own several MaLos; they are all listed here so their
    documents can be sent together in a single email.
    """

    malos: list[str] = Field(default_factory=list)
    kundennummer: str | None = None
    unternehmen: str | None = None
    kategorie: str | None = None  # INVOICE / GUTSCHRIFT (informational)
    primary_email: str | None = None
    cc_email: str | None = None  # "CC Email (extern)"
    ceo_email: str | None = None

    @property
    def to_addresses(self) -> list[str]:
        return [self.primary_email] if self.primary_email else []

    @property
    def cc_addresses(self) -> list[str]:
        return [e for e in (self.cc_email, self.ceo_email) if e]


class ResolvedRecipient(BaseModel):
    """Result of resolving a classified document against the mapping.

    ``malos`` is the full MaLo list of the matched customer (not just the
    document's own MaLo), so callers can group documents per email.
    """

    malo: str | None = None  # the document's own MaLo
    malos: list[str] = Field(default_factory=list)  # all MaLos of the customer
    matched: bool = False
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    unternehmen: str | None = None
    warnings: list[str] = Field(default_factory=list)
