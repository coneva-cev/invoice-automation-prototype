#!/usr/bin/env bash
# Start the FastAPI backend with WeasyPrint's native libraries discoverable.
set -euo pipefail

cd "$(dirname "$0")"

# WeasyPrint (pango/cairo/gdk-pixbuf) is installed via Homebrew on macOS.
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

exec .venv/bin/uvicorn app.main:app --reload --port 8001
