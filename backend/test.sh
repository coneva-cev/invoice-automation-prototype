#!/usr/bin/env bash
# Run the backend test suite.
#   ./test.sh               -> all tests (realdata/integration auto-skip if unavailable)
#   ./test.sh --no-real     -> synthetic only, no realdata/integration (what CI runs)
#   ./test.sh -m integration-> integration only (needs Mailpit up on :1025/:8025)
#   ./test.sh <pytest args...>
#
# Mailpit for integration tests:
#   docker compose -f ../docker-compose.mailpit.yml up -d
set -euo pipefail
cd "$(dirname "$0")"

# WeasyPrint native libs (harmless if unused; keeps app import consistent).
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"

if [[ "${1:-}" == "--no-real" ]]; then
  shift
  exec .venv/bin/pytest -m "not realdata and not integration" "$@"
fi

exec .venv/bin/pytest "$@"
