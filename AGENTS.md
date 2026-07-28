# AGENTS.md

Invoice Automation prototype: Vue 3 SPA (`frontend/`) + Python FastAPI backend (`backend/`) that parses Excel and generates invoice PDFs. Not a git repo. No monorepo tooling — the two apps are independent, run separately.

## Run locally

```bash
# backend (terminal 1) — MUST use run.sh, not raw uvicorn
./backend/run.sh                       # uvicorn on :8001

# frontend (terminal 2)
cd frontend && GITHUB_PACKAGES_TOKEN=<token> npm run dev   # vite on :5173
```

Open http://localhost:5173. Vite proxies `/api/*` → `http://localhost:8001` (see `frontend/vite.config.ts`).

Stop: `pkill -f vite && pkill -f uvicorn`.

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
- Routers: `app/routers/excel.py` (`POST /api/excel/parse`, pandas/openpyxl), `app/routers/pdf.py` (`POST /api/pdf/invoice`, Jinja2 + WeasyPrint). PDF template: `app/templates/invoice.html`.
- Uses a local `.venv` (`backend/.venv`). Deps pinned in `backend/requirements.txt`. API docs at `/docs`.
