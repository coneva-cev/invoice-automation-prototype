#!/usr/bin/env bash
# Start the FastAPI backend with WeasyPrint's native libraries discoverable.
set -euo pipefail

cd "$(dirname "$0")"

# WeasyPrint (pango/cairo/gdk-pixbuf) is installed via Homebrew on macOS.
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

# Load config into the environment. Per-environment (non-secret) defaults from
# .env.<APP_ENV> first, then secret overrides from the gitignored .env.
APP_ENV="${APP_ENV:-local}"
set -a
[[ -f ".env.${APP_ENV}" ]] && source ".env.${APP_ENV}"
[[ -f .env ]] && source .env
set +a

exec .venv/bin/uvicorn app.main:app --reload --port 8001
