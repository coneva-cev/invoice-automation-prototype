"""Build a flat ZIP of PDF files for the Portal bulk-upload API.

Single zip, all PDFs at the root. Duplicate filenames are de-collided by
appending a numeric suffix so no file is silently dropped.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field


@dataclass
class BundleFile:
    """One file to place in the bundle."""

    filename: str
    content: bytes


@dataclass
class BundleResult:
    """Outcome of building a bundle."""

    content: bytes  # the zip bytes
    file_count: int
    names: list[str] = field(default_factory=list)  # final names inside the zip
    renamed: dict[str, str] = field(default_factory=dict)  # original -> final
    skipped: list[str] = field(default_factory=list)  # empty/invalid, not added


def _dedupe_name(name: str, used: set[str]) -> str:
    """Return a unique name, appending ' (n)' before the extension if needed."""
    if name not in used:
        return name
    stem, dot, ext = name.rpartition(".")
    base, suffix = (stem, "." + ext) if dot else (name, "")
    i = 1
    while True:
        candidate = f"{base} ({i}){suffix}"
        if candidate not in used:
            return candidate
        i += 1


def build_pdf_bundle(
    files: list[BundleFile],
    *,
    require_pdf_extension: bool = True,
) -> BundleResult:
    """Zip the given files flat (no directories).

    - Skips files with empty content.
    - De-collides duplicate names deterministically.
    - Preserves insertion order.
    """
    used: set[str] = set()
    names: list[str] = []
    renamed: dict[str, str] = {}
    skipped: list[str] = []

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if not f.content:
                skipped.append(f.filename)
                continue
            name = f.filename or "document.pdf"
            if require_pdf_extension and not name.lower().endswith(".pdf"):
                name = f"{name}.pdf"
            final = _dedupe_name(name, used)
            if final != name:
                renamed[f.filename] = final
            used.add(final)
            names.append(final)
            zf.writestr(final, f.content)

    return BundleResult(
        content=buf.getvalue(),
        file_count=len(names),
        names=names,
        renamed=renamed,
        skipped=skipped,
    )
