# Invoice Automation

A prototype for turning billing PDFs into classified, recipient-mapped documents:
it classifies uploaded PDFs, resolves recipients from a mapping spreadsheet,
bundles them for the Coneva Portal (bulk upload via the monitoring API), and
sends per-customer emails.

- **`frontend/`** — Vue 3 SPA (Vite, TypeScript, Tailwind v4, Auth0).
- **`backend/`** — Python FastAPI service (classification, mapping, bundling,
  Portal upload, email). PDF generation via WeasyPrint.

The two apps are independent and run as separate processes. Auth is handled by
Auth0; only users with the `Invoice Automation Admin` role may use the app.

> Target platform: **macOS on Apple Silicon**. Other platforms are not supported
> for local dev (WeasyPrint native libs and `DYLD_FALLBACK_LIBRARY_PATH` assume
> Homebrew on `/opt/homebrew`).

---

## Prerequisites

Install these once:

- **Homebrew** — https://brew.sh
- **asdf** — version manager (`brew install asdf`). Pins are in
  `backend/.tool-versions` (Python 3.13.5) and `frontend/.tool-versions`
  (Node 22). `frontend/.nvmrc` is provided for nvm users.
- **Python 3.13** and **Node 22** — e.g. via asdf:
  ```bash
  asdf plugin add python && asdf plugin add nodejs
  (cd backend && asdf install)      # Python 3.13.5
  (cd frontend && asdf install)     # Node 22.12.0
  ```
- **Docker** — only for Mailpit (the local mail catcher used by the email step).
- **WeasyPrint native libraries**:
  ```bash
  brew install pango cairo gdk-pixbuf libffi
  ```
- **GitHub Packages token** — the frontend depends on the private
  `@coneva-cev/storybook` package. Create a GitHub personal access token with
  the `read:packages` scope and export it (add to your shell profile so it
  persists):
  ```bash
  export GITHUB_PACKAGES_TOKEN=<token>
  ```
  `frontend/.npmrc` reads this variable; the token is never written to the repo.

---

## Quick start

```bash
# 1. One-time bootstrap: venv, dependencies, .env scaffolding
make setup

# 2. Fill in secrets (files created by setup from the .env.example templates):
#      backend/.env         -> AUTH0_*, MONITORING_API_*, email settings
#      frontend/.env.local  -> VITE_AUTH0_CLIENT_ID

# 3. Start the services (each in its own terminal):
make backend      # FastAPI  -> http://localhost:8001
make frontend     # Vite     -> http://localhost:5173
make mailpit      # optional -> Mailpit UI http://localhost:8025

# 4. Open the app
open http://localhost:5173
```

`make` (no target) lists all available commands.

The Vite dev server proxies `/api/*` to `http://localhost:8001`
(see `frontend/vite.config.ts`).

---

## Make targets

| Target             | Description                                             |
| ------------------ | ------------------------------------------------------- |
| `make setup`       | Bootstrap local dev (venv, deps, `.env` scaffolding)    |
| `make backend`     | Run the FastAPI backend on `:8001`                      |
| `make frontend`    | Run the Vite dev server on `:5173`                      |
| `make mailpit`     | Start Mailpit (SMTP `:1025`, UI `:8025`)                |
| `make mailpit-down`| Stop and remove Mailpit                                 |
| `make test`        | Backend tests (synthetic only — what CI runs)           |
| `make test-all`    | Backend tests incl. realdata/integration                |
| `make check`       | Frontend typecheck (`vue-tsc`)                          |
| `make build`       | Frontend production build                               |
| `make stop`        | Stop backend + frontend dev processes                   |

---

## Environment variables

The `.env.example` files are the source of truth — every variable is documented
there. `setup` copies them to the real (gitignored) files:

| App      | Real file (gitignored) | Template                 |
| -------- | ---------------------- | ------------------------ |
| backend  | `backend/.env`         | `backend/.env.example`   |
| frontend | `frontend/.env.local`  | `frontend/.env.example`  |

**Backend** (`backend/.env`) — key variables:

- `APP_ENV` — `local` (SMTP/Mailpit), `staging`, or `production`. Selects the
  email transport defaults; non-secret per-env defaults live in
  `backend/.env.<APP_ENV>`.
- `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` — Auth0 tenant and API identifier.
- `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` — **secret**; the backend's
  machine-to-machine app, used for token exchange to the monitoring API.
- `REQUIRED_ROLE`, `ROLES_CLAIM` — role that gates the app and the token claim
  that carries it (defaults: `Invoice Automation Admin`, `coneva/roles`).
- `MONITORING_API_*` — Portal/monitoring API audience, base URL, and bulk-upload
  scope.
- Email: `EMAIL_FROM`, `SMTP_*` (local), `SENDGRID_*` (staging/production).

**Frontend** (`frontend/.env.local`):

- `VITE_AUTH0_DOMAIN`, `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE`
- `VITE_REQUIRED_ROLE`, `VITE_ROLES_CLAIM` — must match the backend's role gate.

Never commit real secrets. `.env` and `.env.local` are gitignored; only the
`*.env.example` (and non-secret `backend/.env.staging` / `.env.production`)
templates are tracked.

---

## Auth0

Access requires an Auth0 user with the **`Invoice Automation Admin`** role.
Both frontend and backend gate on this role (surfaced in the `coneva/roles`
token claim). The backend additionally exchanges the user's token for one
scoped to the monitoring API when uploading to the Portal.

The SPA runs on `localhost`, for which Auth0 always shows the consent screen —
this is expected in local dev and disappears on non-localhost origins.

---

## Testing

```bash
make test        # synthetic unit + API tests (what CI runs)
make test-all    # + realdata (needs backend/samples/) + integration (needs Mailpit)
```

- Synthetic tests need no real data or WeasyPrint — `tests/factories.py` builds
  minimal PDFs and mapping spreadsheets.
- Integration tests (email) require Mailpit: `make mailpit` first.
- Realdata tests auto-skip unless the gitignored `backend/samples/` set exists.

Frontend: `make check` (typecheck) and `make build`.

---

## Gotchas

- **Port 8001, not 8000.** Port 8000 is taken by another Docker container on
  this machine; the backend deliberately uses **8001**. Don't change it back.
- **`make backend` / `backend/run.sh` is mandatory** — it sets
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` so WeasyPrint's native libs
  resolve. Running `uvicorn` directly crashes on the WeasyPrint import.
- **`@coneva-cev/storybook` is a prerelease** on GitHub Packages (only the
  `develop` dist-tag exists). `npm install @coneva-cev/storybook` (bare) fails
  with `ETARGET`; the pinned version in `package.json` handles this.
- **`storybook/`** (if present) is a vendored read-only clone of the upstream
  library, not part of this app's build.

## Stopping everything

```bash
make stop                 # backend + frontend
make mailpit-down         # Mailpit container
```
