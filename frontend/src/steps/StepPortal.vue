<script setup lang="ts">
import { computed, ref } from 'vue';
import { Button } from '@coneva-cev/storybook';
import { Badge } from '@coneva-cev/storybook/badge';
import { Spinner } from '@coneva-cev/storybook/spinner';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@coneva-cev/storybook/table';
import { useApi } from '../composables/useApi';
import type { BulkUploadResult, ProcessResponse } from '../types';

const props = defineProps<{ result: ProcessResponse }>();
const emit = defineEmits<{
  'update:uploaded': [boolean];
  'update:uploadResult': [BulkUploadResult | null];
}>();

const { apiFetch } = useApi();

// --- Download bundle -------------------------------------------------------
const downloading = ref(false);
const downloadError = ref<string | null>(null);

// The bundle endpoint requires an Auth0 bearer token, which a plain
// `<a href download>` cannot send. Fetch the zip with apiFetch, then
// trigger a download from the resulting blob.
async function downloadBundle() {
  if (downloading.value) return;
  downloading.value = true;
  downloadError.value = null;
  try {
    const res = await apiFetch(
      `/api/upload/batch/${props.result.batch_id}/bundle`,
    );
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'portal_bundle.zip';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    downloadError.value = e instanceof Error ? e.message : String(e);
  } finally {
    downloading.value = false;
  }
}

// --- Upload to Portal ------------------------------------------------------
const uploading = ref(false);
const uploadError = ref<string | null>(null);
const uploadResult = ref<BulkUploadResult | null>(null);
const uploaded = ref(false);

// By default only documents that matched a recipient in the validation step
// are uploaded. The user may opt to include unmatched documents too.
const includeUnmatched = ref(false);
const unmatchedCount = computed(
  () => props.result.summary.unmatched_documents ?? 0,
);
const matchedCount = computed(
  () => props.result.total - unmatchedCount.value,
);

function isError(status: string): boolean {
  return status.toUpperCase().startsWith('ERROR');
}

// Strip any uploaded-folder prefix from a filename for display.
function basename(path: string): string {
  return path.replace(/\\/g, '/').split('/').pop() ?? path;
}

// --- Document -> customer/MaLo ("tenant") mapping --------------------------
// The Portal is a single multi-tenant endpoint; it resolves each PDF to a
// tenant server-side from the MaLo inside the document. The app therefore has
// no real tenant id — the closest identifier is the recipient (customer) and
// its MaLo from the Excel mapping, which is what the Portal keys on.
interface DocInfo {
  customer: string | null;
  malo: string | null;
  matched: boolean;
}

const docInfoByFilename = computed<Record<string, DocInfo>>(() => {
  const map: Record<string, DocInfo> = {};
  for (const d of props.result.documents) {
    map[d.filename] = {
      customer: d.recipient?.unternehmen ?? d.fields.customer_name ?? null,
      malo: (d.fields.marktlokation as string | null) ?? null,
      matched: !!d.recipient?.matched,
    };
  }
  return map;
});

const UNMATCHED_KEY = '__unmatched__';

// A group of documents that resolve to the same customer ("tenant").
interface TenantGroup<TDoc> {
  key: string;
  customer: string | null; // null => unmatched (no tenant)
  malos: string[];
  docs: TDoc[];
}

function groupByTenant<TDoc extends { filename: string }>(
  docs: TDoc[],
): TenantGroup<TDoc>[] {
  const groups = new Map<string, TenantGroup<TDoc>>();
  for (const doc of docs) {
    const info = docInfoByFilename.value[doc.filename];
    const matched = info?.matched ?? false;
    const customer = info?.customer ?? null;
    const key = matched && customer ? customer : UNMATCHED_KEY;
    let g = groups.get(key);
    if (!g) {
      g = { key, customer: key === UNMATCHED_KEY ? null : customer, malos: [], docs: [] };
      groups.set(key, g);
    }
    if (info?.malo && !g.malos.includes(info.malo)) g.malos.push(info.malo);
    g.docs.push(doc);
  }
  return [...groups.values()];
}

// --- Plan (before upload): which documents go to which customer/tenant -----
// Mirrors what the backend will send: matched documents by default, plus the
// unmatched ones only when the user opted to include them.
const plannedGroups = computed<TenantGroup<{ filename: string }>[]>(() => {
  const docs = props.result.documents
    .filter((d) => includeUnmatched.value || d.recipient?.matched)
    .map((d) => ({ filename: d.filename }));
  const groups = groupByTenant(docs);
  // Named customers first (alphabetical), the "unmatched" bucket last.
  return groups.sort((a, b) => {
    if (a.customer === null) return 1;
    if (b.customer === null) return -1;
    return a.customer.localeCompare(b.customer);
  });
});

// Rows enriched from the process result, joined on PDF filename, error-first.
interface ResultRow {
  filename: string;
  status: string;
  error: boolean;
}

const rows = computed<ResultRow[]>(() => {
  if (!uploadResult.value) return [];
  const list: ResultRow[] = Object.entries(uploadResult.value).map(
    ([filename, status]) => ({
      filename,
      status,
      error: isError(status),
    }),
  );
  // Error-first, then alphabetical by filename for stable ordering.
  return list.sort((a, b) => {
    if (a.error !== b.error) return a.error ? -1 : 1;
    return a.filename.localeCompare(b.filename);
  });
});

// --- Results (after upload): grouped by customer/tenant with per-doc status -
const resultGroups = computed<TenantGroup<ResultRow>[]>(() => {
  if (!uploadResult.value) return [];
  const groups = groupByTenant(rows.value);
  // Sort docs within a group error-first, then by filename.
  for (const g of groups) {
    g.docs.sort((a, b) => {
      if (a.error !== b.error) return a.error ? -1 : 1;
      return a.filename.localeCompare(b.filename);
    });
  }
  // Groups with any error first, then unmatched-last, then alphabetical.
  return groups.sort((a, b) => {
    const aErr = a.docs.some((d) => d.error);
    const bErr = b.docs.some((d) => d.error);
    if (aErr !== bErr) return aErr ? -1 : 1;
    if (a.customer === null) return 1;
    if (b.customer === null) return -1;
    return (a.customer ?? '').localeCompare(b.customer ?? '');
  });
});

function groupOkCount(g: TenantGroup<ResultRow>): number {
  return g.docs.filter((d) => !d.error).length;
}
function groupErrorCount(g: TenantGroup<ResultRow>): number {
  return g.docs.filter((d) => d.error).length;
}
function groupLabel(g: TenantGroup<{ filename: string }>): string {
  return g.customer ?? 'Unmatched — no tenant';
}

const okCount = computed(() => rows.value.filter((r) => !r.error).length);
const errorCount = computed(() => rows.value.filter((r) => r.error).length);

// A response was received (regardless of per-file outcome).
const hasResult = computed(() => uploadResult.value !== null);
// Partial: the request succeeded but some files errored.
const partial = computed(() => hasResult.value && errorCount.value > 0);

async function uploadToPortal() {
  if (uploading.value) return;
  uploading.value = true;
  uploadError.value = null;
  try {
    const res = await apiFetch(
      `/api/documents/batch/${props.result.batch_id}/bulk-upload` +
        `?include_unmatched=${includeUnmatched.value}`,
      { method: 'POST' },
    );
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const reason =
        (detail && (detail.detail || detail.error)) || `HTTP ${res.status}`;
      // 5xx are transient (retry likely helps); 4xx are usually permanent.
      const hint =
        res.status >= 500
          ? ' The Portal service may be temporarily unavailable — you can retry.'
          : '';
      throw new Error(`Upload failed (${res.status}): ${reason}.${hint}`);
    }
    uploadResult.value = (await res.json()) as BulkUploadResult;
    // "Fully uploaded" only when every file succeeded. Any per-file ERROR means
    // the upload was partial, so the send step still requires confirmation.
    const fullySucceeded = errorCount.value === 0;
    uploaded.value = fullySucceeded;
    emit('update:uploaded', fullySucceeded);
    emit('update:uploadResult', uploadResult.value);
  } catch (e) {
    uploadError.value = e instanceof Error ? e.message : String(e);
    uploaded.value = false;
    emit('update:uploaded', false);
  } finally {
    uploading.value = false;
  }
}

function uploadAgain() {
  uploaded.value = false;
  uploadResult.value = null;
  uploadError.value = null;
  emit('update:uploaded', false);
  emit('update:uploadResult', null);
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">3. Upload to Portal</h2>
      <p class="text-muted-foreground text-sm">
        Upload the bundle of all classified documents to the Portal. The Portal
        reports the result per document below.
      </p>
    </div>

    <div class="flex flex-wrap gap-2">
      <Badge variant="outline">{{ result.total }} PDFs in batch</Badge>
      <Badge variant="secondary">{{ matchedCount }} matched</Badge>
      <Badge :variant="unmatchedCount ? 'destructive' : 'outline'">
        {{ unmatchedCount }} unmatched
      </Badge>
    </div>

    <!-- Upload -->
    <section class="space-y-3 rounded-lg border p-4">
      <h3 class="text-sm font-semibold">Portal bulk upload</h3>
      <p class="text-xs text-muted-foreground">
        Uploads the validated (matched) documents to the Portal. Documents that
        failed the validation step are excluded by default.
      </p>

      <!-- Opt-in to also upload unmatched documents. -->
      <label
        v-if="unmatchedCount"
        class="flex items-center gap-2 text-xs text-muted-foreground"
      >
        <input
          type="checkbox"
          v-model="includeUnmatched"
          :disabled="uploading || uploaded || partial"
        />
        Also upload {{ unmatchedCount }} unmatched document(s) that failed
        validation
      </label>

      <div class="flex items-center gap-3">
        <Button
          v-if="!uploaded && !partial"
          :disabled="uploading"
          @click="uploadToPortal"
        >
          <Spinner v-if="uploading" class="mr-2 h-4 w-4" />
          {{ uploading ? 'Uploading…' : 'Upload to Portal' }}
        </Button>

        <!-- Fully succeeded -->
        <template v-else-if="uploaded">
          <span class="text-sm text-green-600 dark:text-green-500">
            ✓ Uploaded
          </span>
          <button
            type="button"
            class="text-sm underline text-muted-foreground hover:text-foreground"
            @click="uploadAgain"
          >
            Upload again
          </button>
        </template>

        <!-- Partial: request succeeded but some documents failed -->
        <template v-else-if="partial">
          <span class="text-sm text-destructive">
            ⚠ Uploaded with {{ errorCount }} error{{ errorCount === 1 ? '' : 's' }}
          </span>
          <Button
            variant="outline"
            size="sm"
            :disabled="uploading"
            @click="uploadToPortal"
          >
            <Spinner v-if="uploading" class="mr-2 h-4 w-4" />
            {{ uploading ? 'Uploading…' : 'Retry upload' }}
          </Button>
        </template>
      </div>

      <!-- Error + retry (transport/HTTP failure — no results at all) -->
      <div v-if="uploadError" class="flex items-center gap-3">
        <p class="text-sm text-destructive">{{ uploadError }}</p>
        <Button
          variant="outline"
          size="sm"
          :disabled="uploading"
          @click="uploadToPortal"
        >
          Retry
        </Button>
      </div>
    </section>

    <!-- Planned upload (before upload): documents grouped by customer/tenant -->
    <section v-if="!uploadResult" class="space-y-3">
      <div>
        <h3 class="text-sm font-semibold">
          Planned upload — documents by customer (tenant)
        </h3>
        <p class="text-xs text-muted-foreground">
          Grouped by the customer / MaLo the Portal resolves the tenant from.
          The Portal derives the actual tenant from each document's MaLo on
          upload.
        </p>
      </div>

      <p
        v-if="plannedGroups.length === 0"
        class="text-sm text-muted-foreground"
      >
        No documents to upload.
      </p>

      <Table v-else>
        <TableHeader>
          <TableRow>
            <TableHead>Customer</TableHead>
            <TableHead>Documents</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="g in plannedGroups"
            :key="g.key"
            :class="g.customer === null ? 'bg-destructive/5' : ''"
          >
            <TableCell class="align-top">
              <div
                class="text-sm font-medium"
                :class="g.customer === null ? 'text-destructive' : ''"
              >
                {{ groupLabel(g) }}
              </div>
              <div v-if="g.malos.length" class="mt-1 text-xs text-muted-foreground">
                MaLo: {{ g.malos.join(', ') }}
              </div>
              <div class="text-xs text-muted-foreground">
                {{ g.docs.length }} doc(s)
              </div>
            </TableCell>
            <TableCell class="text-xs">
              <div v-for="d in g.docs" :key="d.filename">
                {{ basename(d.filename) }}
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </section>

    <!-- Results (after upload): grouped by customer/tenant, errors highlighted -->
    <section v-if="uploadResult" class="space-y-3">
      <div class="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{{ rows.length }} documents</Badge>
        <Badge variant="secondary">{{ okCount }} OK</Badge>
        <Badge :variant="errorCount ? 'destructive' : 'outline'">
          {{ errorCount }} errors
        </Badge>
      </div>

      <p class="text-xs text-muted-foreground">
        Grouped by the customer / MaLo the Portal resolves the tenant from.
      </p>

      <div
        v-for="g in resultGroups"
        :key="g.key"
        class="space-y-1 rounded-md border"
      >
        <div
          class="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-3 py-2"
        >
          <span
            class="text-sm font-medium"
            :class="g.customer === null ? 'text-destructive' : ''"
          >
            {{ groupLabel(g) }}
          </span>
          <Badge v-if="g.malos.length" variant="outline" class="text-[10px]">
            MaLo: {{ g.malos.join(', ') }}
          </Badge>
          <Badge variant="secondary" class="text-[10px]">
            {{ groupOkCount(g) }} OK
          </Badge>
          <Badge
            v-if="groupErrorCount(g)"
            variant="destructive"
            class="text-[10px]"
          >
            {{ groupErrorCount(g) }} error(s)
          </Badge>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Status</TableHead>
              <TableHead>File</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow
              v-for="row in g.docs"
              :key="row.filename"
              :class="row.error ? 'bg-destructive/10' : ''"
            >
              <TableCell>
                <Badge :variant="row.error ? 'destructive' : 'secondary'">
                  {{ row.error ? 'ERROR' : 'OK' }}
                </Badge>
              </TableCell>
              <TableCell class="text-xs">
                {{ basename(row.filename) }}
                <div v-if="row.error" class="text-destructive">
                  {{ row.status }}
                </div>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </section>

    <!-- Download bundle (kept as an escape hatch / manual upload) -->
    <section class="space-y-3 rounded-lg border p-4">
      <h3 class="text-sm font-semibold">Download bundle</h3>
      <p class="text-xs text-muted-foreground">
        Optionally download the same ZIP for manual inspection or upload.
      </p>
      <div class="flex items-center gap-3">
        <Button
          variant="secondary"
          :disabled="downloading"
          @click="downloadBundle"
        >
          <Spinner v-if="downloading" class="mr-2 h-4 w-4" />
          {{ downloading ? 'Preparing…' : 'Download PDF bundle (.zip)' }}
        </Button>
        <span v-if="downloadError" class="text-sm text-destructive">
          {{ downloadError }}
        </span>
      </div>
    </section>
  </div>
</template>
