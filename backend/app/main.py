"""FastAPI entrypoint for the Invoice Automation prototype backend.

Provides stub endpoints for:
  - Excel upload/parsing (pandas + openpyxl)
  - PDF invoice generation (WeasyPrint + Jinja2)
  - PDF upload, classification and recipient mapping (upload pipeline)
  - Document bulk upload to the monitoring API (token exchange)

These are intentionally minimal placeholders. Wire in real logic once the
Excel format and invoice template are finalized.
"""

from __future__ import annotations

from pathlib import Path

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load config before any module that reads os.environ. Order (later wins for
# already-set keys only where override=True): per-environment defaults from
# .env.<APP_ENV>, then secret overrides from .env. Real secrets live in the
# gitignored .env; the .env.<env> files hold non-secret defaults.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_app_env = os.environ.get("APP_ENV", "local").strip().lower()
load_dotenv(_BACKEND_DIR / f".env.{_app_env}")  # non-secret env defaults
load_dotenv(_BACKEND_DIR / ".env", override=True)  # secrets + local overrides

from .routers import documents, email, excel, pdf, upload

app = FastAPI(
    title="Invoice Automation API",
    version="0.1.0",
    description="Prototype backend: Excel parsing + PDF generation.",
)

# Allow the Vite dev server to call the API directly (in addition to the
# Vite proxy). Adjust origins for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}


app.include_router(excel.router, prefix="/api")
app.include_router(pdf.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(email.router, prefix="/api")
