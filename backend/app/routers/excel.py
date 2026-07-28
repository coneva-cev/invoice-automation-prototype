"""Excel upload + parsing endpoints.

STUB: currently reads any uploaded .xlsx into a DataFrame and echoes back
column names + a preview. Replace the parsing logic with the real invoice
mapping once the Excel format/instructions are provided.
"""

from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.dependencies.auth import require_admin

router = APIRouter(tags=["excel"])

ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel",  # .xls
}


@router.post("/excel/parse")
async def parse_excel(
    file: UploadFile = File(...),
    _: dict = Depends(require_admin),
) -> dict:
    """Parse an uploaded Excel file and return a preview.

    Returns sheet names, column headers and the first few rows so the
    frontend can display what was detected before mapping to invoices.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES and not (
        file.filename or ""
    ).lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type or file.filename}",
        )

    raw = await file.read()
    try:
        # sheet_name=None -> dict of {sheet: DataFrame}
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
    except Exception as exc:  # noqa: BLE001 - surface parse errors to client
        raise HTTPException(status_code=422, detail=f"Failed to parse Excel: {exc}")

    result = {}
    for name, df in sheets.items():
        result[name] = {
            "columns": [str(c) for c in df.columns],
            "row_count": int(len(df)),
            "preview": df.head(10).fillna("").astype(str).to_dict(orient="records"),
        }

    return {"filename": file.filename, "sheets": result}
