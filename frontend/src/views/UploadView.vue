<script setup lang="ts">
import { ref, computed } from 'vue';
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

interface Recipient {
  matched: boolean;
  to: string[];
  cc: string[];
  malos: string[];
  unternehmen: string | null;
  warnings: string[];
}
interface DocResult {
  filename: string;
  category: string;
  subtype: string | null;
  fields: Record<string, unknown> & {
    rechnungsnummer?: string | null;
    marktlokation?: string | null;
    customer_name?: string | null;
    amount_eur?: number | null;
  };
  warnings: string[];
  recipient?: Recipient;
}
interface EmailGroup {
  matched: boolean;
  unternehmen: string | null;
  to: string[];
  cc: string[];
  malos: string[];
  documents: string[];
  warnings: string[];
}
interface OrphanRecipient {
  unternehmen: string | null;
  kundennummer: string | null;
  malos: string[];
  to: string[];
  cc: string[];
}
interface ProcessResponse {
  total: number;
  summary: {
    categories: Record<string, number>;
    invoice_subtypes: Record<string, number>;
    needs_review: number;
    emails_to_send: number;
    unmatched_documents: number;
    recipients_without_pdf: number;
    mapping_entries: number;
  };
  emails: EmailGroup[];
  documents: DocResult[];
  orphan_recipients: OrphanRecipient[];
}

const pdfFiles = ref<File[]>([]);
const mappingFile = ref<File | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const result = ref<ProcessResponse | null>(null);
const tab = ref<'documents' | 'emails'>('documents');

// Case 1: PDFs that matched no recipient in the mapping.
const pdfsWithoutRecipient = computed(
  () => result.value?.documents.filter((d) => !d.recipient?.matched) ?? [],
);
// Case 2: mapping recipients that had no PDF in this batch.
const recipientsWithoutPdf = computed(
  () => result.value?.orphan_recipients ?? [],
);
const hasMismatches = computed(
  () =>
    pdfsWithoutRecipient.value.length > 0 ||
    recipientsWithoutPdf.value.length > 0,
);

function onPdfChange(e: Event) {
  const input = e.target as HTMLInputElement;
  pdfFiles.value = input.files ? Array.from(input.files) : [];
}
function onMappingChange(e: Event) {
  const input = e.target as HTMLInputElement;
  mappingFile.value = input.files?.[0] ?? null;
}

const canSubmit = computed(
  () => pdfFiles.value.length > 0 && !!mappingFile.value && !loading.value,
);

async function submit() {
  if (!canSubmit.value) return;
  loading.value = true;
  error.value = null;
  result.value = null;
  try {
    const fd = new FormData();
    for (const f of pdfFiles.value) fd.append('files', f);
    fd.append('mapping_file', mappingFile.value as File);
    const res = await fetch('/api/upload/process', { method: 'POST', body: fd });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }
    result.value = (await res.json()) as ProcessResponse;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function categoryVariant(cat: string) {
  if (cat === 'INVOICE') return 'default';
  if (cat === 'GUTSCHRIFT') return 'secondary';
  return 'destructive';
}
function money(v: unknown) {
  return typeof v === 'number'
    ? v.toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €'
    : '—';
}
</script>

<template>
  <div class="space-y-8">
    <header class="space-y-1">
      <h1 class="text-2xl font-semibold tracking-tight">
        Upload &amp; Mapping
      </h1>
      <p class="text-muted-foreground text-sm">
        Upload invoice / Gutschrift PDFs and the recipient mapping file. Each
        PDF is classified and matched to its email recipients by MaLo.
      </p>
    </header>

    <!-- Upload form -->
    <section class="grid gap-6 sm:grid-cols-2">
      <div class="space-y-2">
        <label class="text-sm font-medium">PDF invoices / Gutschriften</label>
        <input
          type="file"
          accept="application/pdf"
          multiple
          class="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:bg-primary/90"
          @change="onPdfChange"
        />
        <p class="text-xs text-muted-foreground">
          {{ pdfFiles.length }} file(s) selected
        </p>
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">Recipient mapping (.xlsx)</label>
        <input
          type="file"
          accept=".xlsx"
          class="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground hover:file:bg-primary/90"
          @change="onMappingChange"
        />
        <p class="text-xs text-muted-foreground">
          {{ mappingFile ? mappingFile.name : 'none selected' }}
        </p>
      </div>
    </section>

    <div class="flex items-center gap-3">
      <Button :disabled="!canSubmit" @click="submit">
        <Spinner v-if="loading" class="mr-2 h-4 w-4" />
        {{ loading ? 'Processing…' : 'Classify & Map' }}
      </Button>
      <span v-if="error" class="text-sm text-destructive">{{ error }}</span>
    </div>

    <!-- Results -->
    <section v-if="result" class="space-y-6">
      <!-- Summary -->
      <div class="flex flex-wrap gap-2">
        <Badge variant="outline">{{ result.total }} documents</Badge>
        <Badge
          v-for="(count, cat) in result.summary.categories"
          :key="cat"
          :variant="categoryVariant(String(cat))"
        >
          {{ cat }}: {{ count }}
        </Badge>
        <Badge
          v-for="(count, st) in result.summary.invoice_subtypes"
          :key="st"
          variant="secondary"
        >
          {{ st }}: {{ count }}
        </Badge>
        <Badge variant="default">
          {{ result.summary.emails_to_send }} emails
        </Badge>
        <Badge
          :variant="
            result.summary.unmatched_documents ? 'destructive' : 'outline'
          "
        >
          PDFs without recipient: {{ result.summary.unmatched_documents }}
        </Badge>
        <Badge
          :variant="
            result.summary.recipients_without_pdf ? 'destructive' : 'outline'
          "
        >
          recipients without PDF: {{ result.summary.recipients_without_pdf }}
        </Badge>
        <Badge
          :variant="result.summary.needs_review ? 'destructive' : 'outline'"
        >
          review: {{ result.summary.needs_review }}
        </Badge>
      </div>

      <!-- Mismatches -->
      <div
        v-if="hasMismatches"
        class="rounded-lg border border-destructive/40 bg-destructive/5 p-4 space-y-4"
      >
        <h2 class="text-sm font-semibold text-destructive">
          Mismatches to resolve
        </h2>

        <!-- Case 1: PDF without recipient -->
        <div v-if="pdfsWithoutRecipient.length" class="space-y-1">
          <p class="text-xs font-medium">
            PDFs without a mapped recipient ({{ pdfsWithoutRecipient.length }})
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>MaLo</TableHead>
                <TableHead>Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="d in pdfsWithoutRecipient" :key="d.filename">
                <TableCell class="text-xs">{{ d.filename }}</TableCell>
                <TableCell>{{ d.fields.customer_name ?? '—' }}</TableCell>
                <TableCell class="text-xs">
                  {{ d.fields.marktlokation ?? '—' }}
                </TableCell>
                <TableCell class="text-xs text-muted-foreground">
                  {{ d.recipient?.warnings.join('; ') || 'No mapping entry' }}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <!-- Case 2: recipient without PDF -->
        <div v-if="recipientsWithoutPdf.length" class="space-y-1">
          <p class="text-xs font-medium">
            Recipients without a PDF ({{ recipientsWithoutPdf.length }})
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer</TableHead>
                <TableHead>Kundennr.</TableHead>
                <TableHead>MaLos</TableHead>
                <TableHead>Email</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="(o, i) in recipientsWithoutPdf" :key="i">
                <TableCell>{{ o.unternehmen ?? '—' }}</TableCell>
                <TableCell class="text-xs">
                  {{ o.kundennummer ?? '—' }}
                </TableCell>
                <TableCell class="text-xs">{{ o.malos.join(', ') }}</TableCell>
                <TableCell class="text-xs">{{ o.to.join(', ') || '—' }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex gap-2 border-b">
        <button
          class="px-3 py-2 text-sm font-medium -mb-px border-b-2"
          :class="
            tab === 'documents'
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground'
          "
          @click="tab = 'documents'"
        >
          Documents ({{ result.documents.length }})
        </button>
        <button
          class="px-3 py-2 text-sm font-medium -mb-px border-b-2"
          :class="
            tab === 'emails'
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground'
          "
          @click="tab = 'emails'"
        >
          Emails ({{ result.emails.length }})
        </button>
      </div>

      <!-- Documents table -->
      <Table v-if="tab === 'documents'">
        <TableHeader>
          <TableRow>
            <TableHead>Category</TableHead>
            <TableHead>Subtype</TableHead>
            <TableHead>Rechnungsnr.</TableHead>
            <TableHead>Customer</TableHead>
            <TableHead>MaLo</TableHead>
            <TableHead class="text-right">Amount</TableHead>
            <TableHead>Recipient (TO)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="d in result.documents" :key="d.filename">
            <TableCell>
              <Badge :variant="categoryVariant(d.category)">
                {{ d.category }}
              </Badge>
            </TableCell>
            <TableCell class="text-xs">{{ d.subtype ?? '—' }}</TableCell>
            <TableCell>{{ d.fields.rechnungsnummer ?? '—' }}</TableCell>
            <TableCell>{{ d.fields.customer_name ?? '—' }}</TableCell>
            <TableCell class="text-xs">
              {{ d.fields.marktlokation ?? '—' }}
            </TableCell>
            <TableCell class="text-right">
              {{ money(d.fields.amount_eur) }}
            </TableCell>
            <TableCell class="text-xs">
              <span v-if="d.recipient?.matched">{{
                d.recipient.to.join(', ')
              }}</span>
              <Badge v-else variant="destructive">unmatched</Badge>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <!-- Emails table -->
      <Table v-else>
        <TableHeader>
          <TableRow>
            <TableHead>Customer</TableHead>
            <TableHead>TO</TableHead>
            <TableHead>CC</TableHead>
            <TableHead class="text-right"># Docs</TableHead>
            <TableHead>MaLos</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="(e, i) in result.emails" :key="i">
            <TableCell>
              {{ e.unternehmen ?? '—' }}
              <Badge v-if="!e.matched" variant="destructive" class="ml-1">
                unmatched
              </Badge>
            </TableCell>
            <TableCell class="text-xs">{{ e.to.join(', ') || '—' }}</TableCell>
            <TableCell class="text-xs">{{ e.cc.join(', ') || '—' }}</TableCell>
            <TableCell class="text-right">{{ e.documents.length }}</TableCell>
            <TableCell class="text-xs">{{ e.malos.join(', ') || '—' }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </section>
  </div>
</template>
