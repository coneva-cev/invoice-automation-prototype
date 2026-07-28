#!/usr/bin/env bash
# Start the FastAPI backend with WeasyPrint's native libraries discoverable.
set -euo pipefail

cd "$(dirname "$0")"

# WeasyPrint (pango/cairo/gdk-pixbuf) is installed via Homebrew on macOS.
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

# Load backend secrets (Auth0 / Monitoring API config) if present. The backend
# reads these via os.environ; keep .env gitignored (never commit secrets).
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

exec .venv/bin/uvicorn app.main:app --reload --port 8001
