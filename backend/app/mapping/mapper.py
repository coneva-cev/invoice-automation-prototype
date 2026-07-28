"""Load the MaLo-keyed recipient mapping and resolve documents against it."""

from __future__ import annotations

import io
import re

from ..classification.models import ClassifiedDocument
from .models import RecipientMapping, ResolvedRecipient

_SHEET = "Mapping"

# Header label -> RecipientMapping field. Matching is case/space-insensitive.
# The 'MaLo' cell may hold several MaLos for one customer (see _split_malos).
_COLUMN_MAP = {
    "malo": "malos",
    "kundennummer": "kundennummer",
    "unternehmen": "unternehmen",
    "primary email": "primary_email",
    "cc email (extern)": "cc_email",
    "ceo email": "ceo_email",
}


def _norm_header(value: object) -> str:
    return str(value or "").strip().lower()


def _norm_malo(value: object) -> str:
    """MaLos are 11-digit ids; normalize away float/whitespace artifacts."""
    s = str(value or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _split_malos(value: object) -> list[str]:
    """A cell may hold several MaLos separated by comma/semicolon/newline."""
    raw = str(value or "")
    parts = re.split(r"[,;\n]+", raw)
    return [m for m in (_norm_malo(p) for p in parts) if m]


def load_mapping(xlsx_bytes: bytes) -> dict[str, RecipientMapping]:
    """Parse the mapping xlsx into a {MaLo: RecipientMapping} index.

    One row = one customer (with a list of MaLos). The returned dict maps
    *each* MaLo of that customer to the shared RecipientMapping, so a lookup
    by any single MaLo yields the whole customer (all MaLos, one email).

    Raises ValueError if the expected sheet/columns are missing.
    """
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=True, read_only=True)
    ws = wb[_SHEET] if _SHEET in wb.sheetnames else wb.worksheets[0]

    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        wb.close()
        raise ValueError("Mapping sheet is empty.")

    # Map column index -> model field
    idx_to_field: dict[int, str] = {}
    for i, cell in enumerate(header):
        field = _COLUMN_MAP.get(_norm_header(cell))
        if field:
            idx_to_field[i] = field

    if "malos" not in idx_to_field.values():
        wb.close()
        raise ValueError("Mapping file must have a 'MaLo' column.")

    index: dict[str, RecipientMapping] = {}
    for row in rows:
        data: dict[str, object] = {}
        for i, field in idx_to_field.items():
            if i < len(row):
                data[field] = row[i]

        malos = _split_malos(data.get("malos"))
        if not malos:
            continue

        text_fields = {
            k: (str(v).strip() if v not in (None, "") else None)
            for k, v in data.items()
            if k != "malos"
        }
        entry = RecipientMapping(malos=malos, **text_fields)

        for malo in malos:
            # First writer wins if the same MaLo is listed under two customers.
            index.setdefault(malo, entry)

    wb.close()
    return index


def resolve_recipient(
    document: ClassifiedDocument,
    mapping: dict[str, RecipientMapping],
) -> ResolvedRecipient:
    """Resolve a classified document to recipients via its MaLo (1:1)."""
    malo = _norm_malo(document.fields.marktlokation)
    if not malo:
        return ResolvedRecipient(
            matched=False,
            warnings=["Document has no MaLo; cannot map to a recipient."],
        )

    entry = mapping.get(malo)
    if entry is None:
        return ResolvedRecipient(
            malo=malo,
            matched=False,
            warnings=[f"No mapping entry for MaLo {malo}."],
        )

    warnings: list[str] = []
    if not entry.to_addresses:
        warnings.append(f"MaLo {malo} has no primary email in the mapping.")

    return ResolvedRecipient(
        malo=malo,
        malos=entry.malos,
        matched=True,
        to=entry.to_addresses,
        cc=entry.cc_addresses,
        unternehmen=entry.unternehmen,
        warnings=warnings,
    )
