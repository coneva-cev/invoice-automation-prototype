#!/usr/bin/env bash
# Idempotent local-dev bootstrap for the Invoice Automation prototype.
#
#   scripts/setup.sh   (or: make setup)
#
# Safe to re-run. Creates the backend virtualenv, installs backend + frontend
# dependencies, and scaffolds local env files from the committed templates.
# Real secrets are never written by this script — you fill them in afterwards.
set -euo pipefail

# Resolve repo root regardless of where the script is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- pretty output ---------------------------------------------------------
bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

# --- preflight checks ------------------------------------------------------
bold "Checking prerequisites"

# Resolve a Python 3.13 interpreter. Probe from inside backend/ so asdf's
# directory-scoped pin (backend/.tool-versions) applies; the generic shim may
# error with "No version set" when invoked from the repo root.
PYTHON=""
for cand in python3.13 python3; do
  if (cd backend && "$cand" --version >/dev/null 2>&1); then
    PYTHON="$cand"
    break
  fi
done
[[ -n "$PYTHON" ]] || die "Python 3.13 not found. Install it (e.g. 'cd backend && asdf install')."
PY_VERSION="$(cd backend && "$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
if [[ "$PY_VERSION" != "3.13" ]]; then
  warn "$PYTHON is $PY_VERSION; this project targets 3.13 (see backend/.tool-versions)."
else
  ok "$PYTHON $PY_VERSION"
fi

command -v node >/dev/null 2>&1 || die "node not found. Install Node 22 (see frontend/.nvmrc / .tool-versions)."
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [[ "$NODE_MAJOR" != "22" ]]; then
  warn "node is v$(node -v | sed 's/^v//'); this project targets Node 22."
else
  ok "node $(node -v)"
fi

command -v npm >/dev/null 2>&1 || die "npm not found."
ok "npm $(npm -v)"

command -v docker >/dev/null 2>&1 || warn "docker not found — only needed for Mailpit (email step)."

if [[ -z "${GITHUB_PACKAGES_TOKEN:-}" ]]; then
  warn "GITHUB_PACKAGES_TOKEN is not set. The frontend depends on @coneva-cev/storybook"
  warn "from GitHub Packages; 'npm install' will fail without it. Export a token with"
  warn "read:packages scope and re-run:  export GITHUB_PACKAGES_TOKEN=<token>"
else
  ok "GITHUB_PACKAGES_TOKEN is set"
fi

# --- backend: virtualenv + deps -------------------------------------------
bold "Backend (Python)"
if [[ ! -d backend/.venv ]]; then
  # Create the venv from inside backend/ so asdf's pin selects Python 3.13.
  (cd backend && "$PYTHON" -m venv .venv)
  ok "created backend/.venv"
else
  ok "backend/.venv already exists"
fi
backend/.venv/bin/python -m pip install --quiet --upgrade pip
backend/.venv/bin/pip install --quiet -r backend/requirements-dev.txt
ok "installed backend dependencies (requirements-dev.txt)"

# --- env scaffolding -------------------------------------------------------
bold "Environment files"
if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
  warn "created backend/.env from template — fill in real secrets before running"
else
  ok "backend/.env already exists (left untouched)"
fi
if [[ ! -f frontend/.env.local ]]; then
  cp frontend/.env.example frontend/.env.local
  warn "created frontend/.env.local from template — set VITE_AUTH0_CLIENT_ID"
else
  ok "frontend/.env.local already exists (left untouched)"
fi

# --- frontend: deps --------------------------------------------------------
bold "Frontend (Node)"
if [[ -n "${GITHUB_PACKAGES_TOKEN:-}" ]]; then
  (cd frontend && npm install --no-fund --no-audit)
  ok "installed frontend dependencies"
else
  warn "skipped 'npm install' (GITHUB_PACKAGES_TOKEN not set). Run 'make setup' again"
  warn "once the token is exported, or:  cd frontend && npm install"
fi

# --- done ------------------------------------------------------------------
bold "Setup complete"
cat <<'EOF'

Next steps:
  1. Fill in secrets:
       backend/.env            (AUTH0_*, MONITORING_API_*, email)
       frontend/.env.local     (VITE_AUTH0_CLIENT_ID)
  2. Start the services (separate terminals):
       make backend            # FastAPI on http://localhost:8001
       make frontend           # Vite on   http://localhost:5173
       make mailpit            # optional: mail catcher UI on :8025
  3. Open http://localhost:5173

See README.md for details.
EOF
