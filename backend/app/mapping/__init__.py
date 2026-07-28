"""Recipient mapping package.

Maps a classified PDF to its email recipients via a MaLo-based Excel file
(exact lookup, no fuzzy matching). One row = one customer; the 'MaLo' cell
holds a list of that customer's MaLos (comma/semicolon separated) so all of
their documents go out in a single email.

Mapping file columns (sheet 'Mapping', header row 1):
  MaLo | Kundennummer | Unternehmen | Primary Email
       | CC Email (extern) | CEO Email

Sending rule: TO = Primary Email; CC = CC Email (extern) + CEO Email.
"""

from .models import RecipientMapping, ResolvedRecipient
from .mapper import load_mapping, resolve_recipient

__all__ = [
    "RecipientMapping",
    "ResolvedRecipient",
    "load_mapping",
    "resolve_recipient",
]
