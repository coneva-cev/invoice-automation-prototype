# Spec: Persist wizard state across page reload

- **Status:** Proposed (not yet implemented)
- **Owner:** _unassigned_
- **Scope:** Frontend only (no backend changes)
- **Related files:** `frontend/src/views/UploadView.vue`, `frontend/src/steps/*.vue`, `frontend/src/types.ts`

## 1. Problem

The upload wizard (`UploadView.vue`) holds all state in in-memory `ref`s. Reloading
the page (F5, accidental refresh, browser restore) resets everything and the user
starts over from the Upload step — even though the batch already exists server-side
under its `batch_id` and the backend has persisted the process result and drafts.

## 2. Goal

After a reload, restore the wizard to where the user was, without re-uploading the
PDFs/mapping, using a **frontend-only** solution.

### Non-goals

- Deep-linkable / shareable URLs (would need routing + a backend GET endpoint).
- Surviving the 24h server-side batch TTL (see Limitations).
- Persisting the raw uploaded `File` objects (unserializable and unnecessary).

## 3. Background / constraints

- A full batch of PDFs can be up to ~15 MB, **but** that is the PDF payload, which
  stays server-side. It is **never** persisted in the browser.
- The `ProcessResponse` that drives every downstream step is **metadata only**
  (classification fields, recipient mapping, filenames, per-email groups). Estimated
  size: ~1–2 KB per document; a few hundred KB for large batches — comfortably within
  the ~5 MB `sessionStorage`/`localStorage` quota.
- The backend already persists `result.json` and `drafts.json` per batch in
  `BatchStore` with a **24h TTL** (`backend/app/storage/batch_store.py`).
- There is currently **no** public `GET` endpoint to fetch a persisted result by
  `batch_id` (only internal `load_result`). Not needed for this frontend-only spec.

## 4. State inventory (`UploadView.vue`)

| State | Persist? | Reason |
| --- | --- | --- |
| `step` | ✅ | Restore the current wizard step |
| `result` (`ProcessResponse`) | ✅ | Drives validation/portal/send; contains `batch_id` |
| `portalUploaded` (bool) | ✅ | Gates the send-step confirmation |
| `portalUploadResult` (filename → status) | ✅ | Send step default-selects successful uploads |
| `pdfFiles` (`File[]`) | ❌ | Unserializable; only needed for the initial `/process` |
| `mappingFile` (`File`) | ❌ | Same as above |
| `confirmSkipUpload` | ❌ | Transient UI state |
| `loading`, `error` | ❌ | Transient |

## 5. Design

### 5.1 Storage

- Use **`sessionStorage`** (survives reload; auto-clears on tab close). This avoids
  stale batches lingering across days and pointing at a server batch that has expired.
- Single key, e.g. `invoice-automation:wizard-state`.
- Serialized snapshot shape:

  ```ts
  interface PersistedWizardState {
    version: 1;                 // bump to invalidate old snapshots on shape change
    step: StepId;
    result: ProcessResponse;
    portalUploaded: boolean;
    portalUploadResult: BulkUploadResult | null;
  }
  ```

### 5.2 Persist

- After the relevant state changes, write the snapshot:
  `watch([step, result, portalUploaded, portalUploadResult], persist, { deep: true })`
  (or persist at explicit transition points to reduce writes).
- Wrap `setItem` in `try/catch`; on quota errors (unlikely) skip persistence silently
  — the session still works, only reload-restore is lost.
- Only persist when `result` is non-null (nothing to restore before the first process).

### 5.3 Restore (on mount)

1. Read + `JSON.parse` the snapshot inside `try/catch`.
2. Validate `version` and basic shape; on mismatch/parse failure, ignore and start fresh
   (clear the key).
3. If valid, restore `result`, `step`, `portalUploaded`, `portalUploadResult`.
4. `pdfFiles` / `mappingFile` stay empty — fine, since `/process` already ran.

### 5.4 Upload-step behaviour after restore

- The wizard lands on the saved step (e.g. Validation) with full data.
- If the user navigates **back** to the Upload step, the file inputs are empty. Picking
  new files + processing starts a **new** batch and should reset/overwrite the snapshot.

### 5.5 Reset / clear

- Provide an explicit **"Start over"** control that clears the snapshot and resets the
  wizard to the Upload step.
- Auto-clear (overwrite) the snapshot when a **new** `/process` succeeds so a fresh
  batch never inherits stale portal/send state.

## 6. Edge cases

- **Corrupt / old-version snapshot** → ignore, clear key, start fresh.
- **Quota exceeded** → `try/catch` around `setItem`; skip persistence, keep working.
- **Server-side batch expired (24h TTL)** → the restored `result` still renders, but a
  later server call (generate drafts / bundle / bulk-upload) may `404`. Acceptable for
  now (see Limitations). Steps should surface the resulting error as they already do.

## 7. Limitations / future work

- Does not detect a server-expired batch on restore. A future enhancement (out of scope
  here) could add `GET /api/upload/batch/{batch_id}/result`; on restore, verify the
  batch still exists and, if not, clear state and inform the user. That upgrades this to
  the "Option B" backend-assisted approach.
- Not deep-linkable. If shareable/bookmarkable state is later desired, move `batch_id` +
  step into the route (Vue Router) — this supersedes `sessionStorage`.

## 8. Acceptance criteria

- [ ] After processing a batch and advancing to any step, **reloading the page** keeps
      the same step and data (validation tables, portal result, send selections derived
      from `portalUploadResult`).
- [ ] Raw PDFs/mapping are **not** stored in the browser; `sessionStorage` payload stays
      in the low-hundreds-of-KB range for typical batches.
- [ ] A corrupt or version-mismatched snapshot never crashes the app; it falls back to a
      clean Upload step.
- [ ] Starting a new batch (new `/process`) clears prior persisted portal/send state.
- [ ] An explicit **"Start over"** control clears the snapshot and returns to Upload.
- [ ] Closing the tab clears the state (because `sessionStorage`).

## 9. Test plan

- **Unit (frontend):** serialize → `sessionStorage` → restore round-trip yields the same
  `step`/`result`/`portalUploaded`/`portalUploadResult`.
- **Manual:** process a batch, reach Send, reload → lands on Send with data intact;
  reload on Validation → intact; corrupt the storage value → clean restart; "Start over"
  → Upload step, storage cleared; new batch → old portal/send state gone.

## 10. Rough effort

Small — a single composable (e.g. `useWizardPersistence`) or an inline block in
`UploadView.vue`: ~40–60 lines plus a "Start over" button. No backend changes.
