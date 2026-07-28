"""Fixed email-body rendering (one template per document category).

Bodies are fixed: the user never edits the HTML. Given a category and the
draft data, ``render_email`` returns the subject + rendered HTML. Selecting
the template by category is the only branching point.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..classification import Category

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

# category -> (template file, subject prefix)
_TEMPLATE_BY_CATEGORY: dict[str, tuple[str, str]] = {
    Category.INVOICE.value: ("invoice_email.html", "Ihre Verbrauchsabrechnung"),
    Category.GUTSCHRIFT.value: ("gutschrift_email.html", "Ihre Gutschrift"),
    # UNKNOWN falls back to the invoice template; flagged as a warning upstream.
    Category.UNKNOWN.value: ("invoice_email.html", "Ihre Dokumente"),
}


def subject_for(category: str, unternehmen: str | None) -> str:
    _, prefix = _TEMPLATE_BY_CATEGORY.get(
        category, _TEMPLATE_BY_CATEGORY[Category.UNKNOWN.value]
    )
    return f"{prefix} von coneva" if not unternehmen else f"{prefix} – {unternehmen}"


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
    )
    return final_subject, html
