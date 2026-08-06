# AGENTS.md

Invoice Automation prototype: Vue 3 SPA (`frontend/`) + Python FastAPI backend (`backend/`) that classifies billing PDFs, maps recipients, bundles for the Coneva Portal, and sends emails. Git repo. No monorepo tooling — the two apps are independent, run separately.

Human onboarding lives in `README.md`. This file captures agent-relevant gotchas.

## Run locally

```bash
make setup                # one-time: venv, deps, .env scaffolding (scripts/setup.sh)
make backend              # terminal 1 — uvicorn on :8001 (wraps backend/run.sh)
make frontend             # terminal 2 — vite on :5173
make mailpit              # optional — mail catcher for the email step (:8025 UI)
```

`backend/run.sh` is still the real entrypoint (and is mandatory — see below); `make backend` just wraps it. The frontend needs `GITHUB_PACKAGES_TOKEN` exported for `npm install`.

Open http://localhost:5173. Vite proxies `/api/*` → `http://localhost:8001` (see `frontend/vite.config.ts`).

Stop: `make stop` (backend + frontend), `make mailpit-down` (Mailpit).

## Gotchas that will bite you

- **Port 8000 is taken** by a Docker container (`backend-app-1`). This app deliberately uses **8001**. Do not "fix" it back to 8000.
- **`backend/run.sh` is mandatory**: WeasyPrint needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (Homebrew pango/cairo/gdk-pixbuf on Apple Silicon). Running `uvicorn` directly will crash on the weasyprint import. The pdf router imports weasyprint lazily so the rest of the app still boots without the libs.
- **`@coneva-cev/storybook` is a prerelease on GitHub Packages.** Only the `develop` dist-tag exists (e.g. `1.0.0-develop.10`); there is **no stable release**. `npm install @coneva-cev/storybook` (which resolves `@latest`/`@*`) fails with `ETARGET`. Install with `@coneva-cev/storybook@develop`. Switch to `^1.0.0` only once a `main` release is published.
- **npm auth via env var**: `frontend/.npmrc` points `@coneva-cev` at `https://npm.pkg.github.com` and reads `${GITHUB_PACKAGES_TOKEN}`. Any `npm install` in `frontend/` needs that env var exported. The token is never written to a repo file — keep it that way.
- **`storybook/` is a vendored clone** of the upstream Coneva library (has its own `opencode.json`, node_modules, Storybook build). It is a read-only reference, NOT part of this app's build or deploy. Don't edit it to change app behavior; the app consumes the published package in `frontend/node_modules/@coneva-cev/storybook`.

## Frontend notes

- Vue 3.5 + Vite 7 + TypeScript ~5.9 + Tailwind **v4** (`@tailwindcss/vite`, no `tailwind.config.js`). Versions are intentionally pinned below the upstream library's Vite 8/TS 6 for stability — don't bump blindly.
- `src/main.css` order matters: `@import 'tailwindcss'` then `@import '@coneva-cev/storybook/theme.css'`, plus `@source '../node_modules/@coneva-cev/storybook/dist'` so Tailwind scans the library's classes. Dropping the `@source` line breaks component styling.
- Import components from the package: `Button` from `@coneva-cev/storybook`; card parts from the subpath `@coneva-cev/storybook/card` (`Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, ...).
- `@vue/tsconfig@0.9` has **no `tsconfig.node.json`**; `tsconfig.node.json` extends `@vue/tsconfig/tsconfig.json` instead. Don't reintroduce the missing extend.
- Typecheck/build: `npm run check` (`vue-tsc --build`) and `npm run build`.

## Backend notes

- Entrypoint `backend/app/main.py` (`app.main:app`): CORS for `http://localhost:5173`, routers mounted under `/api`.
- Env loading: `run.sh` sources `.env.<APP_ENV>` (non-secret per-env defaults, `APP_ENV=local` by default) then the gitignored `.env` (secrets/overrides). Auth0 + monitoring vars are **required** or the app fails to import.
- Routers: `app/routers/excel.py` (`POST /api/excel/parse`), `app/routers/pdf.py` (`POST /api/pdf/invoice`, Jinja2 + WeasyPrint), `app/routers/upload.py` (classify/process + batch bundle/store), `app/routers/documents.py` (Portal bulk-upload via monitoring-API token exchange), `app/routers/email.py` (draft + send). PDF template: `app/templates/invoice.html`.
- Auth: `app/dependencies/auth.py` verifies Auth0 JWTs and gates every protected route on the `Invoice Automation Admin` role (`require_admin`); `app/services/token_exchange.py` swaps the user token for a monitoring-API-scoped one (RFC 8693). Config is centralized via env (`REQUIRED_ROLE`, `ROLES_CLAIM`).
- Core logic: `app/classification/` (rule-based PDF category + invoice subtype via text markers, using `pypdf`) and `app/mapping/` (MaLo-keyed recipient resolution from an xlsx; one email per customer bundling all their MaLos). `app/bundling/` (flat zip) and `app/storage/` (per-batch PDF store).
- Uses a local `.venv` (`backend/.venv`). Deps pinned in `backend/requirements.txt`. API docs at `/docs`.

## Testing (backend)

- Run: `make test` / `./backend/test.sh --no-real` (synthetic only, what CI runs) or `make test-all` / `./backend/test.sh` (all). Integration (email) tests need Mailpit up (`make mailpit`). Deps: `backend/requirements-dev.txt` (`pytest`, `httpx`). Config: `backend/pytest.ini`.
- Tests do **not** need real data or WeasyPrint: `tests/factories.py` hand-builds minimal text-extractable PDFs (no reportlab/weasyprint) and mapping xlsx with the same markers the classifier keys on. Keep committed tests free of real customer data.
- `tests/test_realdata.py` is marked `@pytest.mark.realdata` and auto-skips unless the gitignored `backend/samples/` set is present; it pins the known counts (29 invoices / 49 Gutschriften; subtypes 23/3/2/1; 67 emails).
- Scope note: these are unit + backend API tests only. `test_endpoints.py` uses FastAPI `TestClient` (in-process ASGI — no real socket, no Vite proxy, no browser). True integration (boot `uvicorn` via `run.sh` + real HTTP), full-stack (through the `:5173`→`:8001` proxy), and E2E (browser) are **not yet written**.
