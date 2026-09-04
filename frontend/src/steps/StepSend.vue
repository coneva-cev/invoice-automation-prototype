<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useAuth0 } from '@auth0/auth0-vue';
import { Button } from '@coneva-cev/storybook';
import { Badge } from '@coneva-cev/storybook/badge';
import { Spinner } from '@coneva-cev/storybook/spinner';
import { useApi } from '../composables/useApi';
import type {
  BulkUploadResult,
  EmailDraft,
  ProcessResponse,
  SendDestinationKind,
  SendMode,
  SendResultItem,
} from '../types';
import type { SendResultMode } from '../types';
const props = defineProps<{
  result: ProcessResponse;
  uploadResult?: BulkUploadResult | null;
}>();

const { apiFetch } = useApi();
const { user } = useAuth0();

const drafts = ref<EmailDraft[]>([]);
const selectedId = ref<string | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

// Draft ids the user has chosen to send. Defaults (on draft load) to only
// drafts whose documents all uploaded to the Portal successfully.
const chosenIds = ref<Set<string>>(new Set());

const previewHtml = ref<string>('');
const previewLoading = ref(false);

const sending = ref(false);
const sendResults = ref<SendResultItem[] | null>(null);
const sendMode = ref<SendMode | null>(null);
const sendResultMode = ref<SendResultMode | null>(null);
// Set true after the first click of "Send" for a destination that reaches real
// customers; the second click confirms. Reset whenever inputs change.
const confirmRealSend = ref(false);

// --- Send destination (chosen per send; gated by the env app mode) ---------
const destinationKind = ref<SendDestinationKind | null>(null);
const replaceTo = ref('');
// True once the user has typed in the replacement field, so a (re)load of the
// mode never clobbers their edit.
const replaceToEdited = ref(false);

const appMode = computed(() => sendMode.value?.app_mode ?? null);
const testMode = computed(() => appMode.value === 'test');
const destinations = computed(() => sendMode.value?.destinations ?? []);
const allowedDomains = computed(() => sendMode.value?.test_allowed_domains ?? []);

// A test-mode destination replaces recipients and thus needs the address.
const needsReplaceTo = computed(() => testMode.value);

// Mirrors the server-side domain guardrail: exactly one '@', non-empty local
// part, and the domain is in the allowed list.
function isAllowedDomain(addr: string): boolean {
  const a = (addr || '').trim().toLowerCase();
  if (a.split('@').length !== 2 || a.startsWith('@')) return false;
  const domain = a.split('@')[1];
  return allowedDomains.value.map((d) => d.toLowerCase()).includes(domain);
}

const replaceToValid = computed(
  () => !needsReplaceTo.value || isAllowedDomain(replaceTo.value),
);

const DEST_LABELS: Record<SendDestinationKind, string> = {
  mailpit: 'Mailpit (local catcher — nothing leaves)',
  sendgrid_sandbox: 'SendGrid sandbox (validate only — no delivery)',
  sendgrid_coneva: 'SendGrid → coneva address (real delivery, test)',
  sendgrid_live: 'SendGrid live → real customers',
};

// A chosen destination reaches real customers only for sendgrid_live.
const reachesRealCustomers = computed(
  () => destinationKind.value === 'sendgrid_live',
);

const base = computed(() => `/api/email/batch/${props.result.batch_id}`);

const selected = computed(
  () => drafts.value.find((d) => d.draft_id === selectedId.value) ?? null,
);
const readyCount = computed(
  () => drafts.value.filter((d) => d.status === 'READY').length,
);
const sentCount = computed(
  () => drafts.value.filter((d) => d.status === 'SENT').length,
);

// --- Portal upload status per draft ---------------------------------------
// A draft's upload is "OK" only when every one of its attached documents
// uploaded to the Portal successfully. When no upload result is available
// (e.g. the Portal step was skipped), status is "unknown".
type UploadStatus = 'ok' | 'failed' | 'unknown';

function draftUploadStatus(draft: EmailDraft): UploadStatus {
  const res = props.uploadResult;
  if (!res) return 'unknown';
  if (draft.attachments.length === 0) return 'unknown';
  const allOk = draft.attachments.every((a) => {
    const status = res[a.filename];
    return typeof status === 'string' && !status.toUpperCase().startsWith('ERROR');
  });
  return allOk ? 'ok' : 'failed';
}

// Per-attachment Portal upload status, for the visual check on the chips.
// Keys of the upload result are the filenames as sent to the Portal, which
// match a draft attachment's `filename`. If a filename isn't present in the
// result (e.g. a bundle rename or the Portal step was skipped), we report
// "unknown" rather than a false "ok".
function attachmentUploadStatus(filename: string): UploadStatus {
  const res = props.uploadResult;
  if (!res) return 'unknown';
  const status = res[filename];
  if (typeof status !== 'string') return 'unknown';
  return status.toUpperCase().startsWith('ERROR') ? 'failed' : 'ok';
}

// The Portal error text for a failed attachment (for the chip tooltip).
function attachmentUploadError(filename: string): string {
  const res = props.uploadResult;
  const status = res?.[filename];
  return typeof status === 'string' ? status : '';
}

// Which failed-upload document(s) block a draft, for the tooltip/inline note.
function draftFailedFiles(draft: EmailDraft): string[] {
  const res = props.uploadResult;
  if (!res) return [];
  return draft.attachments
    .filter((a) => {
      const status = res[a.filename];
      return (
        typeof status === 'string' && status.toUpperCase().startsWith('ERROR')
      );
    })
    .map((a) => a.filename);
}

const hasUploadResult = computed(() => !!props.uploadResult);
const uploadFailedCount = computed(
  () => drafts.value.filter((d) => draftUploadStatus(d) === 'failed').length,
);

// Attachment-level Portal upload summary for the currently selected draft.
// Drives the confirmation line shown above the attachment chips.
const selectedAttachmentSummary = computed<{
  tone: 'ok' | 'failed' | 'unknown';
  total: number;
  ok: number;
  failed: number;
} | null>(() => {
  const draft = selected.value;
  if (!draft || draft.attachments.length === 0) return null;
  let ok = 0;
  let failed = 0;
  let unknown = 0;
  for (const a of draft.attachments) {
    const s = attachmentUploadStatus(a.filename);
    if (s === 'ok') ok += 1;
    else if (s === 'failed') failed += 1;
    else unknown += 1;
  }
  const total = draft.attachments.length;
  let tone: 'ok' | 'failed' | 'unknown';
  if (failed > 0) tone = 'failed';
  else if (unknown > 0) tone = 'unknown';
  else tone = 'ok';
  return { tone, total, ok, failed };
});

// A draft can be (re)sent when it has a recipient: READY, or SENT (resend).
function isSelectable(d: EmailDraft): boolean {
  return d.status === 'READY' || d.status === 'SENT';
}

// Default the selection to sendable drafts whose upload succeeded (or unknown
// when no upload result is present). Failed-upload drafts are left unchecked.
// Only READY drafts are auto-selected, so a reload never re-sends a SENT draft.
function resetSelection() {
  const next = new Set<string>();
  for (const d of drafts.value) {
    if (d.status !== 'READY') continue;
    if (draftUploadStatus(d) !== 'failed') next.add(d.draft_id);
  }
  chosenIds.value = next;
}

function toggleChosen(draftId: string) {
  const next = new Set(chosenIds.value);
  if (next.has(draftId)) next.delete(draftId);
  else next.add(draftId);
  chosenIds.value = next;
}

// Select all READY drafts (explicit user action; includes Portal-failed ones).
function selectAll() {
  chosenIds.value = new Set(
    drafts.value.filter((d) => d.status === 'READY').map((d) => d.draft_id),
  );
}

function selectNone() {
  chosenIds.value = new Set();
}

const selectableCount = computed(
  () => drafts.value.filter(isSelectable).length,
);

// Selected drafts that will actually be sent (READY or SENT/resend).
const chosenReadyCount = computed(
  () =>
    drafts.value.filter(
      (d) => isSelectable(d) && chosenIds.value.has(d.draft_id),
    ).length,
);

function statusVariant(s: string) {
  if (s === 'READY') return 'default';
  if (s === 'SENT') return 'secondary';
  return 'destructive';
}

function uploadBadge(status: UploadStatus): {
  variant: 'secondary' | 'destructive' | 'outline';
  label: string;
} | null {
  if (status === 'ok') return { variant: 'secondary', label: 'Portal ✓' };
  if (status === 'failed') return { variant: 'destructive', label: 'Portal ✗' };
  // Not uploaded / Portal step skipped — make it explicit rather than blank.
  return { variant: 'outline', label: 'Portal ?' };
}

// Tone of the destination selector / result: red only for real-customer sends.
const modeTone = computed(() =>
  reachesRealCustomers.value
    ? 'border-destructive/50 bg-destructive/10 text-destructive'
    : 'border-amber-500/40 bg-amber-50 text-amber-800',
);
function categoryVariant(c: string) {
  if (c === 'INVOICE') return 'default';
  if (c === 'GUTSCHRIFT') return 'secondary';
  return 'destructive';
}

async function generate() {
  loading.value = true;
  error.value = null;
  sendResults.value = null;
  try {
    const res = await apiFetch(`${base.value}/drafts`, { method: 'POST' });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || `HTTP ${res.status}`);
    }
    drafts.value = (await res.json()).drafts as EmailDraft[];
    selectedId.value = drafts.value[0]?.draft_id ?? null;
    resetSelection();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

// Fetch the rendered HTML via apiFetch (an <iframe src> can't send the
// Authorization header) and inject it with srcdoc.
async function loadPreview(draftId: string) {
  previewLoading.value = true;
  previewHtml.value = '';
  try {
    const res = await apiFetch(`${base.value}/drafts/${draftId}/preview`);
    previewHtml.value = res.ok ? await res.text() : '';
  } finally {
    previewLoading.value = false;
  }
}

watch(selectedId, (id) => {
  if (id) loadPreview(id);
});

async function openAttachment(draftId: string, docId: string) {
  const res = await apiFetch(
    `${base.value}/drafts/${draftId}/attachment/${docId}`,
  );
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, '_blank');
  // Revoke a bit later so the new tab has time to load it.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// Inline recipient/subject editing.
const editing = ref(false);
const editTo = ref('');
const editCc = ref('');
const editSubject = ref('');

function startEdit() {
  if (!selected.value) return;
  editTo.value = selected.value.to.join(', ');
  editCc.value = selected.value.cc.join(', ');
  editSubject.value = selected.value.subject;
  editing.value = true;
}
function splitAddrs(v: string): string[] {
  return v
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}
async function saveEdit() {
  if (!selected.value) return;
  const draftId = selected.value.draft_id;
  const res = await apiFetch(`${base.value}/drafts/${draftId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      to: splitAddrs(editTo.value),
      cc: splitAddrs(editCc.value),
      subject: editSubject.value,
    }),
  });
  if (res.ok) {
    const updated = (await res.json()) as EmailDraft;
    const i = drafts.value.findIndex((d) => d.draft_id === draftId);
    if (i >= 0) drafts.value[i] = updated;
    editing.value = false;
    loadPreview(draftId);
  }
}

async function sendAll() {
  // Guardrail: cannot send a test-mode destination without a valid coneva
  // replacement address (server also enforces this, fail-closed).
  if (needsReplaceTo.value && !replaceToValid.value) {
    error.value = `Enter a valid ${allowedDomains.value.join(' / ')} replacement address.`;
    return;
  }
  if (!destinationKind.value) {
    error.value = 'Select a send destination.';
    return;
  }
  // Business-critical guard: real-customer destination requires confirmation.
  if (reachesRealCustomers.value && !confirmRealSend.value) {
    confirmRealSend.value = true;
    return;
  }
  confirmRealSend.value = false;
  sending.value = true;
  error.value = null;
  try {
    const res = await apiFetch(`${base.value}/drafts/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        draft_ids: [...chosenIds.value],
        destination: {
          kind: destinationKind.value,
          replace_to: needsReplaceTo.value ? replaceTo.value.trim() : null,
        },
      }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || `HTTP ${res.status}`);
    }
    const body = await res.json();
    sendResults.value = body.results as SendResultItem[];
    sendResultMode.value = body.mode ?? null;
    // Refresh statuses.
    const listed = await apiFetch(`${base.value}/drafts`);
    if (listed.ok) drafts.value = (await listed.json()).drafts as EmailDraft[];
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    sending.value = false;
  }
}

// Load the active email mode + destinations up front so the UI can render the
// destination selector and pre-fill the replacement address.
async function loadMode() {
  try {
    const res = await apiFetch('/api/email/mode');
    if (!res.ok) return;
    const m = (await res.json()) as SendMode;
    sendMode.value = m;
    // Default the destination selection.
    destinationKind.value = m.destinations[0] ?? null;
    // Pre-fill the replacement address (unless the user already edited it):
    // prefer the logged-in Auth0 user's email when it's in an allowed domain,
    // else the env default (EMAIL_TEST_RECIPIENTS).
    if (!replaceToEdited.value) {
      const authEmail = (user.value?.email as string | undefined) ?? '';
      if (authEmail && isAllowedDomain(authEmail)) {
        replaceTo.value = authEmail;
      } else if (m.test_default_recipient) {
        replaceTo.value = m.test_default_recipient;
      }
    }
  } catch {
    // non-fatal; the selector just won't show
  }
}

onMounted(() => {
  loadMode();
  generate();
});
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">4. Review &amp; send emails</h2>
      <p class="text-muted-foreground text-sm">
        Drafts are generated automatically — one per customer and document
        category. Review the body, recipients and attachments, then send.
      </p>
    </div>

    <!-- Global Test Mode banner: unmissable, safety-critical. -->
    <div
      v-if="testMode"
      class="rounded-md border-2 border-amber-500 bg-amber-50 p-4 text-amber-900"
    >
      <p class="text-sm font-semibold">
        ⚠ TEST MODE — no email will reach a real customer
      </p>
      <p class="mt-1 text-sm">
        Every email’s To, Cc and Bcc is replaced with the
        {{ allowedDomains.join(' / ') }} address below. The intended recipient
        is shown in the subject and a banner inside each email.
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <Badge variant="default">{{ readyCount }} ready</Badge>
      <Badge variant="secondary">{{ sentCount }} sent</Badge>
      <Badge variant="outline">{{ drafts.length }} drafts</Badge>
      <Badge
        v-if="testMode"
        variant="outline"
        class="border-amber-500 bg-amber-100 text-amber-800"
      >
        TEST MODE
      </Badge>
      <Badge
        v-else
        variant="outline"
        class="border-destructive/60 text-destructive"
      >
        LIVE MODE
      </Badge>
      <Badge
        v-if="!hasUploadResult"
        variant="outline"
        class="border-amber-300 bg-amber-50 text-amber-700"
      >
        No Portal upload done
      </Badge>
      <Badge
        v-if="hasUploadResult && uploadFailedCount"
        variant="destructive"
      >
        {{ uploadFailedCount }} with failed Portal upload
      </Badge>
      <Button
        variant="outline"
        class="ml-auto"
        :disabled="loading"
        @click="generate"
      >
        <Spinner v-if="loading" class="mr-2 h-4 w-4" />
        Regenerate
      </Button>
    </div>

    <!-- Send destination selector -->
    <div class="space-y-3 rounded-md border p-4" :class="modeTone">
      <p class="text-sm font-medium">Send destination</p>
      <div class="space-y-1">
        <label
          v-for="d in destinations"
          :key="d"
          class="flex items-center gap-2 text-sm"
        >
          <input
            type="radio"
            :value="d"
            :checked="destinationKind === d"
            @change="destinationKind = d"
          />
          {{ DEST_LABELS[d] }}
        </label>
      </div>

      <!-- Replacement address (test mode only) -->
      <label v-if="needsReplaceTo" class="block text-sm">
        <span class="text-xs text-muted-foreground">
          Replacement recipient (must be {{ allowedDomains.join(' / ') }})
        </span>
        <input
          v-model="replaceTo"
          class="mt-1 w-full rounded-md border px-2 py-1"
          :class="replaceToValid ? '' : 'border-destructive'"
          placeholder="you@coneva.com"
          @input="replaceToEdited = true"
        />
        <span v-if="!replaceToValid" class="text-xs text-destructive">
          Enter a valid {{ allowedDomains.join(' / ') }} address.
        </span>
      </label>

      <div class="flex items-center gap-3">
        <Button
          :disabled="
            sending || chosenReadyCount === 0 || (needsReplaceTo && !replaceToValid)
          "
          :variant="reachesRealCustomers ? 'destructive' : 'default'"
          @click="sendAll"
        >
          <Spinner v-if="sending" class="mr-2 h-4 w-4" />
          {{
            sending
              ? 'Sending…'
              : reachesRealCustomers
                ? `Send ${chosenReadyCount} to customers`
                : testMode
                  ? `Send ${chosenReadyCount} (TEST → ${replaceTo || '…'})`
                  : `Send ${chosenReadyCount} (sandbox)`
          }}
        </Button>
      </div>
    </div>

    <!-- Real-send confirmation: only for the live real-customer destination. -->
    <div
      v-if="confirmRealSend && reachesRealCustomers"
      class="rounded-md border-2 border-destructive bg-destructive/10 p-4 text-sm"
    >
      <p class="font-semibold text-destructive">
        Send {{ chosenReadyCount }} email(s) to real customers?
      </p>
      <p class="mt-1 text-destructive">
        These emails will be delivered to the actual recipients via SendGrid.
        This cannot be undone.
      </p>
      <div class="mt-3 flex gap-2">
        <Button variant="destructive" :disabled="sending" @click="sendAll">
          <Spinner v-if="sending" class="mr-2 h-4 w-4" />
          Yes, send to customers
        </Button>
        <Button variant="outline" @click="confirmRealSend = false">
          Cancel
        </Button>
      </div>
    </div>

    <!-- Explanation of the default selection when some uploads failed. -->
    <p
      v-if="hasUploadResult && uploadFailedCount"
      class="text-xs text-muted-foreground"
    >
      By default only emails whose documents uploaded to the Portal
      successfully are selected. Tick a draft marked
      <span class="font-medium text-destructive">Portal ✗</span> to send it
      anyway.
    </p>

    <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

    <div
      v-if="sendResults"
      class="flex flex-wrap items-center gap-3 rounded-md border bg-muted/30 p-3 text-sm"
    >
      <span>
        Sent {{ sendResults.filter((r) => r.sent).length }} /
        {{ sendResults.length }}.
      </span>
      <span v-if="sendResultMode" class="text-muted-foreground">
        via {{ sendResultMode.destination
        }}<template v-if="sendResultMode.replaced_to">
          → {{ sendResultMode.replaced_to }}</template
        >.
      </span>
      <span v-if="sendResults.some((r) => !r.sent)" class="text-destructive">
        Some failed — see draft statuses.
      </span>
      <a
        v-if="sendResultMode && sendResultMode.destination === 'mailpit'"
        href="http://localhost:8025"
        target="_blank"
        rel="noopener"
        class="ml-auto text-primary underline"
      >
        View captured emails in Mailpit ↗
      </a>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-sm text-muted-foreground">
      <Spinner class="h-4 w-4" /> Generating drafts…
    </div>

    <div v-else-if="drafts.length === 0" class="text-sm text-muted-foreground">
      No sendable drafts (no matched recipients).
    </div>

    <div v-else class="grid gap-4 md:grid-cols-[280px_1fr]">
      <!-- Draft list -->
      <div class="space-y-2">
        <div
          class="flex items-center justify-between px-1 text-xs text-muted-foreground"
        >
          <span>{{ chosenReadyCount }} of {{ selectableCount }} selected</span>
          <span class="flex gap-2">
            <button
              type="button"
              class="underline hover:text-foreground"
              @click="selectAll"
            >
              Select all
            </button>
            <button
              type="button"
              class="underline hover:text-foreground"
              @click="selectNone"
            >
              Select none
            </button>
          </span>
        </div>
        <ul class="space-y-1 rounded-md border p-2">
          <li v-for="d in drafts" :key="d.draft_id" class="flex items-start gap-2">
            <input
            type="checkbox"
            class="mt-2.5"
            :checked="chosenIds.has(d.draft_id)"
            :disabled="!isSelectable(d)"
            :title="
              !isSelectable(d)
                ? 'This draft has no recipient and cannot be sent'
                : d.status === 'SENT'
                  ? 'Re-send this already-sent email'
                  : 'Include this email when sending'
            "
            @change="toggleChosen(d.draft_id)"
          />
          <button
            class="min-w-0 flex-1 rounded-md p-2 text-left text-sm hover:bg-accent"
            :class="d.draft_id === selectedId ? 'bg-accent' : ''"
            @click="selectedId = d.draft_id"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="min-w-0 truncate font-medium">
                {{ d.unternehmen ?? '—' }}
              </span>
              <Badge :variant="statusVariant(d.status)" class="shrink-0 text-[10px]">
                {{ d.status }}
              </Badge>
            </div>
            <div class="mt-1 flex flex-wrap items-center gap-1">
              <Badge :variant="categoryVariant(d.category)" class="text-[10px]">
                {{ d.category }}
              </Badge>
              <Badge
                v-if="uploadBadge(draftUploadStatus(d))"
                :variant="uploadBadge(draftUploadStatus(d))!.variant"
                class="text-[10px]"
                :class="
                  draftUploadStatus(d) === 'unknown'
                    ? 'border-amber-300 bg-amber-50 text-amber-700'
                    : ''
                "
                :title="
                  draftUploadStatus(d) === 'failed'
                    ? 'Failed Portal upload: ' + draftFailedFiles(d).join(', ')
                    : draftUploadStatus(d) === 'ok'
                      ? 'All documents uploaded to the Portal'
                      : 'Not uploaded to the Portal (upload step skipped)'
                "
              >
                {{ uploadBadge(draftUploadStatus(d))!.label }}
              </Badge>
              <span class="text-xs text-muted-foreground">
                {{ d.attachments.length }} file(s)
              </span>
            </div>
          </button>
        </li>
      </ul>
      </div>

      <!-- Preview pane -->
      <div v-if="selected" class="space-y-3 rounded-md border p-4">
        <!-- Recipients / subject -->
        <div v-if="!editing" class="space-y-1 text-sm">
          <div>
            <span class="text-muted-foreground">To:</span>
            <span :class="testMode ? 'line-through text-muted-foreground' : ''">
              {{ selected.to.join(', ') || '—' }}
            </span>
            <span v-if="testMode" class="text-amber-700">
              → {{ replaceTo || '…' }} (test mode)
            </span>
          </div>
          <div>
            <span class="text-muted-foreground">Cc:</span>
            <span :class="testMode ? 'line-through text-muted-foreground' : ''">
              {{ selected.cc.join(', ') || '—' }}
            </span>
            <span v-if="testMode && selected.cc.length" class="text-amber-700">
              → (removed in test mode)
            </span>
          </div>
          <div v-if="!testMode && sendMode && sendMode.bcc.length">
            <span class="text-muted-foreground">Bcc:</span>
            {{ sendMode.bcc.join(', ') }}
            <span class="text-xs text-muted-foreground">(all emails)</span>
          </div>
          <div><span class="text-muted-foreground">Subject:</span> {{ selected.subject }}</div>
          <Button variant="outline" class="mt-1" @click="startEdit">Edit recipients / subject</Button>
        </div>
        <div v-else class="space-y-2 text-sm">
          <label class="block">
            <span class="text-xs text-muted-foreground">To (comma-separated)</span>
            <input v-model="editTo" class="mt-1 w-full rounded-md border px-2 py-1" />
          </label>
          <label class="block">
            <span class="text-xs text-muted-foreground">Cc</span>
            <input v-model="editCc" class="mt-1 w-full rounded-md border px-2 py-1" />
          </label>
          <label class="block">
            <span class="text-xs text-muted-foreground">Subject</span>
            <input v-model="editSubject" class="mt-1 w-full rounded-md border px-2 py-1" />
          </label>
          <div class="flex gap-2">
            <Button variant="secondary" @click="saveEdit">Save</Button>
            <Button variant="outline" @click="editing = false">Cancel</Button>
          </div>
        </div>

        <!-- Attachments -->
        <div class="space-y-2">
          <!-- Per-draft Portal upload confirmation: this is the final visual
               check that the documents being attached were uploaded OK. -->
          <p
            v-if="selectedAttachmentSummary"
            class="text-xs font-medium"
            :class="{
              'text-emerald-700': selectedAttachmentSummary.tone === 'ok',
              'text-destructive': selectedAttachmentSummary.tone === 'failed',
              'text-amber-700': selectedAttachmentSummary.tone === 'unknown',
            }"
          >
            <template v-if="selectedAttachmentSummary.tone === 'ok'">
              ✓ All {{ selectedAttachmentSummary.total }} attachment(s) uploaded
              to the Portal.
            </template>
            <template v-else-if="selectedAttachmentSummary.tone === 'failed'">
              ✗ {{ selectedAttachmentSummary.ok }}/{{
                selectedAttachmentSummary.total
              }}
              attachment(s) uploaded — {{ selectedAttachmentSummary.failed }}
              failed. Sending this email will attach document(s) that are not in
              the Portal.
            </template>
            <template v-else>
              ⚠ Portal upload not confirmed for these attachment(s) — the upload
              step was skipped. You cannot be sure these documents are in the
              Portal.
            </template>
          </p>

          <div class="flex flex-wrap gap-1">
            <button
              v-for="a in selected.attachments"
              :key="a.doc_id"
              class="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs hover:bg-accent"
              :class="{
                'border-emerald-300 bg-emerald-50':
                  attachmentUploadStatus(a.filename) === 'ok',
                'border-destructive/40 bg-destructive/10':
                  attachmentUploadStatus(a.filename) === 'failed',
                'border-amber-300 bg-amber-50':
                  attachmentUploadStatus(a.filename) === 'unknown',
              }"
              :title="
                attachmentUploadStatus(a.filename) === 'ok'
                  ? 'Uploaded to the Portal'
                  : attachmentUploadStatus(a.filename) === 'failed'
                    ? 'Portal upload failed: ' + attachmentUploadError(a.filename)
                    : 'Portal upload not confirmed (upload step skipped)'
              "
              @click="openAttachment(selected.draft_id, a.doc_id)"
            >
              <span
                aria-hidden="true"
                :class="{
                  'text-emerald-600':
                    attachmentUploadStatus(a.filename) === 'ok',
                  'text-destructive':
                    attachmentUploadStatus(a.filename) === 'failed',
                  'text-amber-600':
                    attachmentUploadStatus(a.filename) === 'unknown',
                }"
              >
                {{
                  attachmentUploadStatus(a.filename) === 'ok'
                    ? '✓'
                    : attachmentUploadStatus(a.filename) === 'failed'
                      ? '✗'
                      : '⚠'
                }}
              </span>
              <span>📎 {{ a.filename }}</span>
            </button>
          </div>
        </div>

        <!-- Warnings -->
        <p
          v-if="selected.warnings.length"
          class="text-xs text-destructive"
        >
          {{ selected.warnings.join('; ') }}
        </p>

        <!-- HTML body preview -->
        <div class="rounded-md border">
          <div class="border-b bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
            Email body preview
          </div>
          <div v-if="previewLoading" class="p-4">
            <Spinner class="h-4 w-4" />
          </div>
          <iframe
            v-else
            :srcdoc="previewHtml"
            class="h-[480px] w-full"
            sandbox=""
            title="Email preview"
          />
        </div>
      </div>
    </div>
  </div>
</template>
