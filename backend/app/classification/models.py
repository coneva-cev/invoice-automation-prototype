"""Domain model for classified PDF documents.

These objects are the stable contract consumed by later pipeline steps
(validation, portal upload, email dispatch). The validation step branches on
``category`` + ``subtype``, so keep those enums stable.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    """Top-level document category (mutually exclusive)."""

    INVOICE = "INVOICE"  # "Verbrauchsabrechnung für Ihre Stromlieferung"
    GUTSCHRIFT = "GUTSCHRIFT"  # "Gutschrift gemäß Vertrag zur Stromvermarktung"
    UNKNOWN = "UNKNOWN"  # matched no known category marker


class InvoiceSubtype(str, Enum):
    """Invoice subtype, derived from the energy line items.

    Maps 1:1 to the Flex Excel dataset sheets:
      TARIF_ONLY        -> Datensatz_Standard      ("EPEX SPOT Preis")
      OPTIMIZATION_ONLY -> Datensatz_Opti_ohne_PS  ("coneva Flex Preis", no PS)
      COMBINED          -> Datensatz_ProfitShare   ("coneva Flex Preis" + PS)
      FIXPRICE          -> Datensatz_Fixpreis      ("coneva Fix Preis")
    """

    TARIF_ONLY = "TARIF_ONLY"
    OPTIMIZATION_ONLY = "OPTIMIZATION_ONLY"
    COMBINED = "COMBINED"
    FIXPRICE = "FIXPRICE"
    UNKNOWN = "UNKNOWN"  # invoice category but no recognized energy line item


class DocumentFields(BaseModel):
    """Fields extracted from the PDF header for downstream use.

    All optional: extraction is best-effort and must not fail classification.
    """

    rechnungsnummer: str | None = None
    rechnungsdatum: str | None = None
    leistungszeitraum: str | None = None
    kundennummer: str | None = None
    marktlokation: str | None = None
    netzbetreiber: str | None = None
    # invoice uses "Verbrauchsstelle", Gutschrift uses "Standort der Anlage"
    location: str | None = None
    customer_name: str | None = None
    amount_eur: float | None = None  # Rechnungsbetrag / Gutschrift total


class ClassifiedDocument(BaseModel):
    """Internal object created for each uploaded PDF."""

    filename: str
    category: Category
    subtype: InvoiceSubtype | None = None  # only meaningful for INVOICE
    fields: DocumentFields = Field(default_factory=DocumentFields)
    # Non-fatal issues surfaced for review (e.g. UNKNOWN, missing fields).
    warnings: list[str] = Field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return (
            self.category is Category.UNKNOWN
            or self.subtype is InvoiceSubtype.UNKNOWN
            or bool(self.warnings)
        )
