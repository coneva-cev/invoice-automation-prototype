# Spec: Migrate Invoice Automation to a marimo notebook

- **Status:** Proposed (not yet implemented)
- **Owner:** _unassigned_
- **Audience:** dual-use — an implementing agent picks up the work from this
  document, and a human reviews it. Behavior is captured as testable
  requirements; source is referenced by `file:line` rather than embedded.
- **Scope:** Reimplement the current Vue 3 SPA + FastAPI invoice-automation tool
  as a **dedicated** marimo app (mode `run`) hosted on the existing dev
  Kubernetes / ArgoCD platform (`/Users/mahe/cev/argocd`).

---

## 1. Purpose

The invoice-automation tool turns billing PDFs into classified,
recipient-mapped documents, bundles them for the Coneva Portal (bulk upload via
the monitoring API), and sends per-customer emails. Today it is two independent
apps (`frontend/` Vue SPA + `backend/` FastAPI). This spec defines how to
re-deliver the same behavior as a single marimo notebook served as an app,
consolidating the stack and offloading authentication to the existing SSO proxy.

Pipeline (unchanged by this migration):

```
upload PDFs + mapping.xlsx
  → classify PDFs
  → resolve recipients from the mapping (MaLo-keyed)
  → validate / review (documents, matches, emails, mismatches)
  → bundle matched PDFs into a flat ZIP
  → Portal bulk-upload (monitoring API)
  → generate + review + send per-customer emails
```

Source modules (all framework-agnostic except the routers):
`backend/app/classification/`, `backend/app/mapping/`, `backend/app/bundling/`,
`backend/app/email/`, `backend/app/storage/`, `backend/app/services/`,
`backend/app/routers/`, `backend/app/dependencies/auth.py`.

---

## 2. Target architecture (decided)

A **dedicated marimo app**, *not* part of the existing per-user editable
notebook fleet.

| Aspect | Decision |
| --- | --- |
| Hosting | Own Helm release / Deployment on the **dev** cluster (separate from the `marimo-notebook` per-user ApplicationSet). |
| Image | **Custom image**, `FROM ghcr.io/marimo-team/marimo`, with WeasyPrint native libs + Python deps + the vendored core logic + the notebook baked in. Published to Harbor. |
| Mode | **`run`** (app UI; code cells not editable). |
| Route | Own Traefik route (e.g. `/ops/invoice-automation` or a dedicated host under `*.dev-conevacloud.com`). |
| AuthN/AuthZ | **SSO group-gate at the proxy** (oauth2-proxy + Auth0 OIDC + Traefik `forwardAuth` with `allowed_groups`). This replaces the app's `Invoice Automation Admin` Auth0 role gate. |
| Portal API auth | M2M **client_credentials** token (unchanged; `backend/app/services/token_exchange.py`). No per-user / on-behalf-of exchange (not enabled on the tenant, and not required). |
| Secrets | Own `ExternalSecret` → Azure Key Vault (`ClusterSecretStore kv-cev-dev-services`), scoped to this pod only. |
| Core logic | **Vendored** into the notebook repo and baked into the image. |

### Why dedicated (not the per-user notebooks)

The existing platform (`/Users/mahe/cev/argocd`) runs **per-user editable
notebooks**: `argocd/applications/marimo-notebook.yaml` is a matrix of ~21 named
users × dev cluster, each a Helm release (`marimo-notebook@0.5.0`, image
`1.2.0`) with its own PVC; `marimo-dispatch@0.1.1`
(`environments/dev/marimo-dispatch/values.yaml`) routes each SSO email to that
user's single backend. That model is wrong for this tool because invoice
automation is a **shared, privileged** workflow (M2M Portal upload + SendGrid)
run by non-tech colleagues via `/ops/`. It must not run inside every engineer's
edit-mode PVC with those credentials exposed. A dedicated `run`-mode app with
its own least-privilege secret and an SSO group-gate is the correct fit.

---

## 3. Functional requirements

Behavior-level acceptance criteria. Each maps to existing, tested logic; the
migration must preserve it. Rules are summarized; see the referenced source for
exact detail.

### FR-1 Classification — `backend/app/classification/classifier.py`

- Category by mutually exclusive text markers:
  `Gutschrift gemäß Vertrag zur Stromvermarktung` → GUTSCHRIFT;
  `Verbrauchsabrechnung für Ihre Stromlieferung` → INVOICE; else UNKNOWN.
- Invoice subtype precedence (energy line items):
  `coneva Fix Preis` → FIXPRICE;
  `coneva Flex Preis` + `coneva Profit Share` → COMBINED;
  `coneva Flex Preis` alone → OPTIMIZATION_ONLY;
  `EPEX SPOT Preis` → TARIF_ONLY; else UNKNOWN.
- Field extraction: `Rechnungsnummer`, `Rechnungsdatum`, `Leistungszeitraum`,
  `Kundennummer`, `Marktlokation`, `Netzbetreiber`, location
  (`Verbrauchsstelle`/`Standort der Anlage`), customer name (first non-empty line
  after the `coneva GmbH | … München` sender line), amount (German `6.693,67` →
  `6693.67`, from `Rechnungsbetrag`/`Gutschrift … EUR`).
- Warnings for: unknown category, invoice with UNKNOWN subtype, missing
  Rechnungsnummer. Non-PDF or unreadable PDF → UNKNOWN document, **never crash**.
- Known-count regression (realdata): 29 invoices / 49 Gutschriften; invoice
  subtypes 23 / 3 / 2 / 1.

### FR-2 Recipient mapping — `backend/app/mapping/mapper.py`

- Parse the `Mapping` sheet (fallback: first sheet) into a `{MaLo:
  RecipientMapping}` index. Header match is case/space-insensitive
  (`MaLo`, `Kundennummer`, `Unternehmen`, `Primary Email`, `CC Email (extern)`,
  `CEO Email`). A `MaLo` column is required (else `ValueError`).
- MaLo normalization: strip whitespace, drop trailing `.0`; a cell may hold
  several MaLos split on `, ; \n`. One row = one customer (with all its MaLos);
  first-writer-wins if a MaLo appears twice.
- `resolve_recipient(document, mapping)` → matched/unmatched by the document's
  MaLo, with warnings (no MaLo; no mapping entry; no primary email).

### FR-3 Process result / grouping — `backend/app/routers/upload.py` (`/upload/process`)

- Produce the canonical `ProcessResponse` (see `frontend/src/types.ts:45`):
  `batch_id`, `total`, `summary` (categories, invoice_subtypes, needs_review,
  emails_to_send, unmatched_documents, recipients_without_pdf, mapping_entries),
  `emails[]` (one group per matched customer bundling all their docs/MaLos;
  unmatched docs each stand alone), `documents[]` (each with a `recipient`
  block), `orphan_recipients[]` (mapping entries with no PDF in this batch).
- Persist uploaded PDF bytes + the result so later stages need no re-upload.

### FR-4 Bundling — `backend/app/bundling/zipper.py`

- Flat ZIP (all PDFs at root). Skip empty content, force `.pdf` extension,
  de-collide duplicate names deterministically as `name (n).pdf`, preserve order.

### FR-5 Portal bulk-upload — `backend/app/routers/documents.py`

- `PUT {MONITORING_API_BASE_URL}/v2/documents-bulk-upload?sendEmailNotification=false`.
- Headers: `Authorization: Bearer <M2M token>`,
  `authorization-scope: <MONITORING_API_BULK_UPLOAD_SCOPE>`,
  `X-Requested-With: Python`.
- `sendEmailNotification` is **hardcoded false** (this app sends its own mail;
  the Portal must not send duplicates).
- By default upload only **matched** documents; `include_unmatched=true` uploads
  all. The Portal returns a per-file map `{filename: "OK" | "ERROR: …"}`, passed
  through verbatim so the UI can show a results table and offer retry.
- Errors: 404 (unknown/empty batch), 502 (token/transport failure), 4xx/5xx
  forwarded from the Portal.

### FR-6 Email drafts — `backend/app/email/build.py`, `backend/app/routers/email.py`

- One draft per **(matched customer, document category)**; unmatched groups
  produce no draft. Category order: INVOICE, GUTSCHRIFT, then others.
- Draft = subject + fixed HTML body (rendered per category), attachments by
  `doc_id`, status READY (has TO) / BLOCKED (no TO), warnings.
- Support: list drafts, HTML preview, inline PDF attachment preview, and PATCH
  recipients/subject (body re-rendered; sendability recomputed).

### FR-7 Email send — `backend/app/email/sender.py`, `backend/app/email/config.py`

- Pluggable backends `console` | `smtp` | `sendgrid`, selected by `APP_ENV`
  defaults (local→smtp, staging→sendgrid+sandbox, production→sendgrid) with
  explicit env overrides.
- **Fail-closed guardrail:** real delivery (sendgrid, sandbox off) requires the
  second opt-in `EMAIL_ALLOW_REAL_SEND=true`; otherwise forced back to sandbox.
  No single variable flip can cause a live blast. **This guardrail must be
  preserved.**
- Send accepts an optional `draft_ids` subset (default: only drafts whose
  documents uploaded to the Portal successfully). Returns per-draft results plus
  the explicit active send mode.

### FR-8 Monitoring token — `backend/app/services/token_exchange.py`

- OAuth2 client_credentials for `MONITORING_API_AUDIENCE` using
  `AUTH0_CLIENT_ID`/`AUTH0_CLIENT_SECRET`; in-process cache with 60s expiry skew.
  **Ports verbatim** (only the error-surfacing changes — see §6).

### FR-9 Batch storage / state — `backend/app/storage/batch_store.py`

- Per-batch on-disk store: PDF bytes, `index.json`, `result.json`,
  `drafts.json`. Path-traversal guard on `batch_id`. 24h TTL sweep of abandoned
  batches. Lifecycle: create on upload → read by later stages → delete on
  completion.

---

## 4. Non-functional & security requirements

- **AuthZ boundary is the SSO proxy.** The app's `require_admin` role gate
  (`backend/app/dependencies/auth.py`) and all Auth0 JWT verification are
  **removed**; access is enforced by a Traefik `forwardAuth` middleware with an
  Auth0 **group** allowlist (model: `environments/dev/akhq/middleware.yaml`,
  `?allowed_groups=…`). The notebook trusts that only authorized users reach it.
- **Least privilege.** Portal/SendGrid credentials live only on this dedicated
  pod's secret — never in the per-user notebook PVCs.
- **`mode=run`.** No editable code cells; users run the workflow, they don't edit
  it.
- **Email fail-closed guardrail** (FR-7) preserved end-to-end.
- **Linux runtime** removes the macOS-only `DYLD_FALLBACK_LIBRARY_PATH`
  workaround; WeasyPrint native libs are installed via `apt` in the image.
- **State isolation.** A single shared app instance must not leak batches between
  concurrent users (batches are keyed by opaque `batch_id`; see §11 risk on
  concurrency).

---

## 5. Requirements the migration must NOT regress

- Classifier known-counts (FR-1) and subtype precedence.
- ProcessResponse schema (FR-3) — it is the canonical data contract.
- `sendEmailNotification=false` on Portal upload (FR-5).
- Matched-only upload default with `include_unmatched` opt-in (FR-5).
- Email real-send guardrail (FR-7).

---

## 6. Migration design (notebook)

**Delete:** entire `frontend/`; `backend/app/main.py`; all of
`backend/app/routers/`; `backend/app/dependencies/auth.py`. The frontend-only
reload-persistence spec (`specs/persist-wizard-state-on-reload.md`) becomes
unnecessary — marimo cell state persists across reload for free.

**Vendor (port ~verbatim) into the notebook repo and bake into the image:**
`classification/`, `mapping/`, `bundling/`, `email/`, `storage/`,
`services/token_exchange.py`. The only code change: replace the two
`HTTPException`-based error paths (`token_exchange.py`, and the Portal call in
`documents.py`) with plain exceptions surfaced in the UI via `mo.stop` /
`mo.callout(kind="danger")`.

**Rewrite the 4 Vue steps as marimo cells**, following the proven pattern in
`/Users/mahe/cev/marimo-notebooks/ops/upload-master-data.py`
(setup cell with all imports; `mo.stop` + `mo.ui.run_button` gating; per-PID temp
dir under `__marimo__/{pid}/`). Cell outline:

1. **Setup** — imports, per-PID temp dir, `BatchStore` init.
2. **Upload** — `mo.ui.file(filetypes=[".pdf"], multiple=True)` + a single
   `.xlsx` mapping file input.
3. **Process** (`mo.stop` until both present) — classify + map + build the
   `ProcessResponse`; persist via `BatchStore` (FR-1/2/3).
4. **Validation** — `mo.ui.tabs` for Documents / Matches / Emails / Mismatches
   using `mo.ui.table`.
5. **Portal upload** (`mo.ui.run_button`) — build ZIP (FR-4), PUT via `httpx`
   with the M2M token (FR-5/8); render per-file results; `include_unmatched`
   checkbox.
6. **Email** — generate drafts (FR-6), select subset (default upload-successful),
   guardrailed send (FR-7); show per-draft results + active send mode.

**Dependencies to bake into the image:** `weasyprint`, `pypdf`, `openpyxl`,
`jinja2`, `pydantic`, `python-dotenv`, `httpx` (plus marimo).
Native libs (Debian/apt): `libpango-1.0-0`, `libpangocairo-1.0-0`,
`libgdk-pixbuf-2.0-0`, `libcairo2`, `libffi-dev`.

---

## 7. Deployment delta (end-to-end)

References the ArgoCD repo `/Users/mahe/cev/argocd`. **Dev environment only**
(the marimo platform exists only in `dev`).

1. **Custom image** — `Dockerfile`: `FROM ghcr.io/marimo-team/marimo:<pinned>` →
   `apt-get install` the native libs above → `pip install` the Python deps →
   copy the vendored core + the notebook → default command runs
   `marimo run <notebook>.py` (host/port/base-url per the platform's convention).
   Publish to `harbor.conevacloud.com`.
2. **ArgoCD Application** — a **new** `Application` (not the per-user
   `marimo-notebook` matrix). Either render the Harbor `marimo-notebook` chart
   with `mode=run` + the custom image if the chart supports a standalone,
   non-per-user release, **or** a bespoke Deployment + Service + Traefik
   IngressRoute. *Choice depends on out-of-repo chart internals — see §11.*
3. **Routing** — Traefik route (className `traefik`, TLS
   `wildcard.dev-conevacloud.com-tls`) for the dedicated path/host; any
   `--base-url` needed for subpath serving.
4. **SSO group-gate** — a `forwardAuth` middleware restricting to an Auth0 group
   (pattern: `environments/dev/akhq/middleware.yaml`,
   `environments/dev/oauth2-proxy/middleware.yaml`). Decide the group name.
5. **Secrets** — a new `ExternalSecret` (pattern:
   `environments/dev/marimo-operator/external-secrets.yaml`) pulling from
   Key Vault via `ClusterSecretStore kv-cev-dev-services`, providing:
   `MONITORING_API_AUDIENCE`, `MONITORING_API_BASE_URL`,
   `MONITORING_API_BULK_UPLOAD_SCOPE`, `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`,
   `AUTH0_CLIENT_SECRET`, `APP_ENV`, `EMAIL_FROM`, `SENDGRID_*` / `SMTP_*`,
   `EMAIL_ALLOW_REAL_SEND`.

---

## 8. Config / environment inventory

| Var | Purpose |
| --- | --- |
| `MONITORING_API_AUDIENCE` | Auth0 audience for the M2M monitoring token |
| `MONITORING_API_BASE_URL` | Portal API base; bulk-upload URL is built from it |
| `MONITORING_API_BULK_UPLOAD_SCOPE` | Static `authorization-scope` header value |
| `AUTH0_DOMAIN` / `AUTH0_CLIENT_ID` / `AUTH0_CLIENT_SECRET` | M2M client_credentials |
| `APP_ENV` | Selects email backend defaults (local/staging/production) |
| `EMAIL_FROM`, `SMTP_*`, `SENDGRID_*` | Email transport |
| `EMAIL_ALLOW_REAL_SEND` | Second opt-in required for real delivery (fail-closed) |

> **Discrepancy to resolve during implementation:** the Portal bulk-upload URL is
> built from `MONITORING_API_BASE_URL` in `backend/app/routers/documents.py`, but
> `backend/app/.env.example` sets it **without** the `/api/topology` path segment
> that working configuration requires
> (`https://portal.dev-conevacloud.com/api/topology`). Confirm the correct value
> when wiring the Key Vault secret.

`AUTH0_AUDIENCE`, `REQUIRED_ROLE`, `ROLES_CLAIM` and the frontend `VITE_*` vars
are **dropped** (JWT verification and the role gate are removed).

---

## 9. Testing requirements

- **Keep** the module-level pytest suite (classification / mapping / bundling /
  email / documents), which uses `backend/tests/factories.py` (synthetic
  text-extractable PDFs + mapping xlsx; no WeasyPrint/real data). These test the
  vendored core directly and must stay green.
- **Drop** the FastAPI `TestClient` API-shape tests (no HTTP layer anymore);
  re-target their assertions at the ported functions where still meaningful.
- **Preserve** the realdata regression (`@pytest.mark.realdata`, auto-skipped):
  29/49, subtypes 23/3/2/1, 67 emails.
- **Optional:** a headless `marimo run` / export smoke check in CI.

---

## 10. Sequenced plan

**Milestone 0 — PoC vertical slice (de-risk the two biggest unknowns):**
build the custom WeasyPrint image; vendor the core; a notebook doing
upload → classify → validation table; served `mode=run` on dev behind the SSO
group-gate. Proves image build, `run`-mode serving, routing, and auth.

**Milestone 1 — Portal bulk-upload cell** (M2M token, matched-only default,
per-file results).

**Milestone 2 — Email drafts + guardrailed send** (subset send, mode reporting).

**Milestone 3 — Parity, tests, docs, cutover** (full validation tabs, port
tests, then decommission the Vue + FastAPI app).

---

## 11. Risks & open items

- **Out-of-repo unknowns to confirm before implementation** (live in Harbor /
  the notebook git repo, not in the two repos analyzed):
  - Harbor charts `marimo-notebook@0.5.0` and `marimo-dispatch@0.1.1` internals:
    image repo, whether `mode=run` + a custom image are supported for a
    standalone (non-per-user) release, the `/ops/` Ingress/route mechanics, any
    `--base-url` rewrite, resources/storage.
  - The custom notebook image `…:1.2.0` contents (Dockerfile / deps) and the
    private notebook git repo behind `marimo-git-creds`.
  - Which Auth0 group to gate on for the SSO `allowed_groups` middleware.
- **Heavy native deps** (WeasyPrint et al.) — mitigated by using a *dedicated*
  image, so the shared per-user notebook env is unaffected.
- **Concurrency / shared instance.** A single `run`-mode app serves multiple
  users; batches are isolated by opaque `batch_id`, but confirm marimo's session
  model doesn't cross-contaminate UI state between simultaneous users. If it
  does, revisit (per-user instance, or session-scoped state).
- **`MONITORING_API_BASE_URL`** path discrepancy (§8).

---

## 12. Out of scope

- Deep-linkable / shareable URLs and Vue-Router-style routing.
- Real per-user (on-behalf-of / RFC 8693) token exchange — not enabled on the
  tenant and not required; M2M client_credentials is accepted.
- Staging / production deployment (the marimo platform is dev-only today).
- Multi-user concurrency hardening beyond the check noted in §11.
