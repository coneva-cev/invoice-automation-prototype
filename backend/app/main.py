"""FastAPI entrypoint for the Invoice Automation prototype backend.

Provides stub endpoints for:
  - Excel upload/parsing (pandas + openpyxl)
  - PDF invoice generation (WeasyPrint + Jinja2)

These are intentionally minimal placeholders. Wire in real logic once the
Excel format and invoice template are finalized.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load Auth0 config from app/.env before any module that reads os.environ
load_dotenv(Path(__file__).resolve().parent / ".env")

from .routers import excel, pdf

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
