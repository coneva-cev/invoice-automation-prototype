"""PDF bundling package.

Produces a single flat ZIP of all PDFs for the Portal bulk-upload API
(pipeline step 4). This is an internal artifact consumed by the next step,
not a user-facing download.
"""

from .zipper import BundleFile, BundleResult, build_pdf_bundle

__all__ = ["BundleFile", "BundleResult", "build_pdf_bundle"]
