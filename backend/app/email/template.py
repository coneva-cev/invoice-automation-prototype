"""Fixed email-body rendering (one template per document category).

Bodies are fixed: the user never edits the HTML. Given a category and the
draft data, ``render_email`` returns the subject + rendered HTML. Selecting
the template by category is the only branching point.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..classification import Category

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_LOGO_PATH = _TEMPLATES_DIR / "assets" / "coneva-logo.png"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    """Return the coneva logo as a base64 data URI for inline email embedding.

    Emails can't reliably load external images, so the logo is embedded. Cached
    for the process lifetime. Returns an empty string if the asset is missing
    (the template then simply omits the logo).
    """
    try:
        encoded = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{encoded}"


def _basename(path: str | None) -> str:
    """Strip any directory prefix from a filename.

    When a whole folder is uploaded, filenames arrive as e.g.
    ``test documents/Rechnung_...pdf``. Only the bare file name should appear
    in the email body. Handles both ``/`` and ``\\`` separators.
    """
    if not path:
        return ""
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


_env.filters["basename"] = _basename

# Template key for the "SMA Spot powered by coneva" customer group. This is
# routed by customer group, not document category, so it is registered under a
# dedicated string key (not a Category value). Draft generation that targets
# this group passes this key as ``category`` to ``render_email``. The routing
# that selects it (customer-group detection + combined invoice/Gutschrift
# grouping) is added separately.
SMA_SPOT_TEMPLATE_KEY = "SMA_SPOT"

# category (or template key) -> (template file, subject prefix)
_TEMPLATE_BY_CATEGORY: dict[str, tuple[str, str]] = {
    Category.INVOICE.value: ("invoice_email.html", "Ihre Verbrauchsabrechnung"),
    Category.GUTSCHRIFT.value: ("gutschrift_email.html", "Ihre Gutschrift"),
    # UNKNOWN falls back to the invoice template; flagged as a warning upstream.
    Category.UNKNOWN.value: ("invoice_email.html", "Ihre Dokumente"),
    SMA_SPOT_TEMPLATE_KEY: (
        "sma_spot_email.html",
        "SMA Spot powered by coneva | Dokumente",
    ),
}

# Template keys whose subject prefix is already a complete subject line and
# must not get the generic " von coneva" suffix.
_STANDALONE_SUBJECT_KEYS = {SMA_SPOT_TEMPLATE_KEY}


def subject_for(category: str, unternehmen: str | None) -> str:
    _, prefix = _TEMPLATE_BY_CATEGORY.get(
        category, _TEMPLATE_BY_CATEGORY[Category.UNKNOWN.value]
    )
    # Subject is generic — the company name is intentionally not included.
    if category in _STANDALONE_SUBJECT_KEYS:
        return prefix
    return f"{prefix} von coneva"


def render_email(
    *,
    category: str,
    unternehmen: str | None,
    documents: list[dict],
    malos: list[str],
    subject: str | None = None,
) -> tuple[str, str]:
    """Render a fixed email body for a category.

    Args:
        category: INVOICE / GUTSCHRIFT / UNKNOWN — selects the template.
        unternehmen: customer name for the greeting (optional).
        documents: list of ``{"filename": ...}`` dicts listed in the body.
        malos: MaLo strings shown for reference.
        subject: explicit subject override (user-edited); otherwise derived.

    Returns:
        ``(subject, html)``
    """
    tpl_name, _ = _TEMPLATE_BY_CATEGORY.get(
        category, _TEMPLATE_BY_CATEGORY[Category.UNKNOWN.value]
    )
    final_subject = subject or subject_for(category, unternehmen)
    template = _env.get_template(tpl_name)
    html = template.render(
        subject=final_subject,
        unternehmen=unternehmen,
        documents=documents,
        malos=malos,
        logo_data_uri=_logo_data_uri(),
    )
    return final_subject, html
