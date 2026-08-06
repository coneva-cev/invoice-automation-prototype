<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { Button } from '@coneva-cev/storybook';
import { Badge } from '@coneva-cev/storybook/badge';
import { Spinner } from '@coneva-cev/storybook/spinner';
import { useApi } from '../composables/useApi';
import type {
  BulkUploadResult,
  EmailDraft,
  ProcessResponse,
  SendMode,
  SendResultItem,
} from '../types';

const props = defineProps<{
  result: ProcessResponse;
  uploadResult?: BulkUploadResult | null;
}>();

const { apiFetch } = useApi();

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

// Default the selection to sendable drafts whose upload succeeded (or unknown
// when no upload result is present). Failed-upload drafts are left unchecked.
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

const chosenReadyCount = computed(
  () =>
    drafts.value.filter(
      (d) => d.status === 'READY' && chosenIds.value.has(d.draft_id),
    ).length,
);

function statusVariant(s: string) {
  if (s === 'READY') return 'default';
  if (s === 'SENT') return 'secondary';
  return 'destructive';
}

function uploadBadge(status: UploadStatus): {
  variant: 'secondary' | 'destructive';
  label: string;
} | null {
  if (status === 'ok') return { variant: 'secondary', label: 'Portal ✓' };
  if (status === 'failed') return { variant: 'destructive', label: 'Portal ✗' };
  return null;
}

// Style the mode banner by how "live" the send is.
const modeTone = computed(() => {
  const m = sendMode.value;
  if (!m) return '';
  if (m.delivers && m.backend === 'sendgrid')
    return 'border-destructive/50 bg-destructive/10 text-destructive';
  return 'border-amber-500/40 bg-amber-50 text-amber-800';
});
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
  sending.value = true;
  error.value = null;
  try {
    // Send only the user-selected drafts (defaults to upload-successful ones).
    const res = await apiFetch(`${base.value}/drafts/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft_ids: [...chosenIds.value] }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || `HTTP ${res.status}`);
    }
    const body = await res.json();
    sendResults.value = body.results as SendResultItem[];
    sendMode.value = (body.mode ?? null) as SendMode | null;
    // Refresh statuses.
    const listed = await apiFetch(`${base.value}/drafts`);
    if (listed.ok) drafts.value = (await listed.json()).drafts as EmailDraft[];
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    sending.value = false;
  }
}

// Load the active send mode up front so it's visible before sending.
async function loadMode() {
  try {
    const res = await apiFetch('/api/email/mode');
    if (res.ok) sendMode.value = (await res.json()) as SendMode;
  } catch {
    // non-fatal; banner just won't show
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

    <div class="flex flex-wrap items-center gap-2">
      <Badge variant="default">{{ readyCount }} ready</Badge>
      <Badge variant="secondary">{{ sentCount }} sent</Badge>
      <Badge variant="outline">{{ drafts.length }} drafts</Badge>
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
      <span
        v-if="sendMode"
        class="inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium"
        :class="modeTone"
        :title="`env: ${sendMode.app_env}, backend: ${sendMode.backend}`"
      >
        {{ sendMode.label }}
      </span>
      <Button :disabled="sending || chosenReadyCount === 0" @click="sendAll">
        <Spinner v-if="sending" class="mr-2 h-4 w-4" />
        {{ sending ? 'Sending…' : `Send ${chosenReadyCount} selected` }}
      </Button>
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
      <span v-if="sendResults.some((r) => !r.sent)" class="text-destructive">
        Some failed — see draft statuses.
      </span>
      <a
        v-if="sendMode && sendMode.backend === 'smtp'"
        href="http://localhost:8025"
        target="_blank"
        rel="noopener"
        class="ml-auto text-primary underline"
      >
        View captured emails in Mailpit ↗
      </a>
    </div>

    <!-- Active send mode: always shown so it's clear what will happen. -->
    <div
      v-if="sendMode"
      class="rounded-md border p-3 text-sm"
      :class="modeTone"
    >
      <span class="font-medium">Send mode:</span> {{ sendMode.label }}
      <span class="opacity-70">
        (env: {{ sendMode.app_env }}, backend: {{ sendMode.backend }})
      </span>
      <span v-if="sendMode.real_send_blocked" class="block text-xs mt-1">
        Real delivery was requested but blocked — set
        <code>EMAIL_ALLOW_REAL_SEND=true</code> to actually deliver.
      </span>
      <span v-else-if="!sendMode.delivers" class="block text-xs mt-1 opacity-80">
        No emails were delivered to real recipients in this mode.
      </span>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-sm text-muted-foreground">
      <Spinner class="h-4 w-4" /> Generating drafts…
    </div>

    <div v-else-if="drafts.length === 0" class="text-sm text-muted-foreground">
      No sendable drafts (no matched recipients).
    </div>

    <div v-else class="grid gap-4 md:grid-cols-[280px_1fr]">
      <!-- Draft list -->
      <ul class="space-y-1 rounded-md border p-2">
        <li v-for="d in drafts" :key="d.draft_id" class="flex items-start gap-2">
          <input
            type="checkbox"
            class="mt-2.5"
            :checked="chosenIds.has(d.draft_id)"
            :disabled="d.status !== 'READY'"
            :title="
              d.status !== 'READY'
                ? 'Only READY drafts can be sent'
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
                :title="
                  draftUploadStatus(d) === 'failed'
                    ? 'Failed Portal upload: ' + draftFailedFiles(d).join(', ')
                    : 'All documents uploaded to the Portal'
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

      <!-- Preview pane -->
      <div v-if="selected" class="space-y-3 rounded-md border p-4">
        <!-- Recipients / subject -->
        <div v-if="!editing" class="space-y-1 text-sm">
          <div><span class="text-muted-foreground">To:</span> {{ selected.to.join(', ') || '—' }}</div>
          <div><span class="text-muted-foreground">Cc:</span> {{ selected.cc.join(', ') || '—' }}</div>
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
        <div class="flex flex-wrap gap-1">
          <button
            v-for="a in selected.attachments"
            :key="a.doc_id"
            class="rounded-md border px-2 py-1 text-xs hover:bg-accent"
            @click="openAttachment(selected.draft_id, a.doc_id)"
          >
            📎 {{ a.filename }}
          </button>
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
