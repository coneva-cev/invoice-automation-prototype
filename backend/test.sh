#!/usr/bin/env bash
# Run the backend test suite.
#   ./test.sh            -> all tests (real-data tests auto-skip if samples/ absent)
#   ./test.sh --no-real  -> synthetic tests only (what CI runs)
#   ./test.sh <pytest args...>
set -euo pipefail
cd "$(dirname "$0")"

# WeasyPrint native libs (harmless if unused; keeps app import consistent).
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

if [[ "${1:-}" == "--no-real" ]]; then
  shift
  exec .venv/bin/pytest -m "not realdata" "$@"
fi

exec .venv/bin/pytest "$@"
