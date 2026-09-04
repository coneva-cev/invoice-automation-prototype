<script setup lang="ts">
import { computed, ref } from 'vue';
import { Badge } from '@coneva-cev/storybook/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@coneva-cev/storybook/table';
import type { ProcessResponse } from '../types';

const props = defineProps<{ result: ProcessResponse }>();

const pdfsWithoutRecipient = computed(
  () => props.result.documents.filter((d) => !d.recipient?.matched) ?? [],
);
const recipientsWithoutPdf = computed(
  () => props.result.orphan_recipients ?? [],
);
// Unmatched groups have no recipient — they belong in Mismatches, not here.
const matchedEmails = computed(() =>
  props.result.emails.filter((e) => e.matched),
);
const mismatchCount = computed(
  () => pdfsWithoutRecipient.value.length + recipientsWithoutPdf.value.length,
);
const hasMismatches = computed(() => mismatchCount.value > 0);

// Successful matches: customers from the Excel mapping that were paired with
// at least one uploaded PDF (i.e. document ↔ recipient matched).
const matches = computed(() => matchedEmails.value);
const hasMatches = computed(() => matches.value.length > 0);

// Default to the combined "All" view: matched groups first, then unmatched
// grouped by reason. The other tabs act as filters to refine the view.
const tab = ref<'all' | 'matches' | 'documents' | 'emails' | 'mismatches'>(
  'all',
);

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
// Strip any uploaded-folder prefix from a filename for display.
function basename(path: string): string {
  return path.replace(/\\/g, '/').split('/').pop() ?? path;
}
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">2. Validation — recipient mapping</h2>
      <p class="text-muted-foreground text-sm">
        Review classification and recipient mapping. Resolve mismatches before
        continuing to portal upload / email sending.
      </p>
    </div>

    <!-- Summary -->
    <div class="flex flex-wrap gap-2">
      <Badge variant="outline">{{ result.total }} documents</Badge>
      <Badge
        v-for="(count, cat) in result.summary.categories"
        :key="cat"
        variant="secondary"
      >
        {{ cat }}: {{ count }}
      </Badge>
      <Badge
        v-for="(count, st) in result.summary.invoice_subtypes"
        :key="st"
        variant="outline"
      >
        {{ st }}: {{ count }}
      </Badge>
      <Badge variant="secondary">{{ result.summary.emails_to_send }} emails</Badge>
      <Badge
        class="border-transparent bg-green-600 text-white"
      >
        matches: {{ matches.length }}
      </Badge>
      <Badge
        :variant="result.summary.unmatched_documents ? 'destructive' : 'outline'"
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
      <Badge :variant="result.summary.needs_review ? 'destructive' : 'outline'">
        review: {{ result.summary.needs_review }}
      </Badge>
    </div>

    <!-- Tabs (filters) -->
    <div class="flex gap-2 border-b">
      <button
        class="px-3 py-2 text-sm font-medium -mb-px border-b-2"
        :class="
          tab === 'all'
            ? 'border-primary text-foreground'
            : 'border-transparent text-muted-foreground'
        "
        @click="tab = 'all'"
      >
        All
      </button>
      <button
        v-if="hasMatches"
        class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium -mb-px border-b-2"
        :class="
          tab === 'matches'
            ? 'border-green-600 text-green-700 dark:text-green-500'
            : 'border-transparent text-green-700/70 dark:text-green-500/70'
        "
        @click="tab = 'matches'"
      >
        Matches
        <Badge
          class="text-[10px] border-transparent bg-green-600 text-white"
        >
          {{ matches.length }}
        </Badge>
      </button>
      <button
        v-if="hasMismatches"
        class="flex items-center gap-1.5 px-3 py-2 text-sm font-medium -mb-px border-b-2"
        :class="
          tab === 'mismatches'
            ? 'border-destructive text-destructive'
            : 'border-transparent text-destructive/70'
        "
        @click="tab = 'mismatches'"
      >
        Mismatches
        <Badge variant="destructive" class="text-[10px]">
          {{ mismatchCount }}
        </Badge>
      </button>
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
        Emails ({{ matchedEmails.length }})
      </button>
    </div>

    <!-- ================= Combined "All" view ================= -->
    <div v-if="tab === 'all'" class="space-y-6">
      <p
        v-if="!hasMatches && !hasMismatches"
        class="text-sm text-muted-foreground"
      >
        No results to show.
      </p>

      <!-- Matched group -->
      <div v-if="hasMatches" class="space-y-2">
        <div class="flex items-center gap-2">
          <span
            class="inline-block h-2.5 w-2.5 rounded-full bg-green-600"
            aria-hidden="true"
          />
          <h3 class="text-sm font-semibold text-green-700 dark:text-green-500">
            Matched ({{ matches.length }})
          </h3>
        </div>
        <p class="text-xs text-muted-foreground">
          Documents successfully matched to a recipient from the Excel mapping.
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Customer</TableHead>
              <TableHead>TO</TableHead>
              <TableHead>CC</TableHead>
              <TableHead>MaLos</TableHead>
              <TableHead>Documents</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow
              v-for="(e, i) in matches"
              :key="i"
              class="bg-green-500/10"
            >
              <TableCell class="font-medium">{{ e.unternehmen ?? '—' }}</TableCell>
              <TableCell class="text-xs">{{ e.to.join(', ') || '—' }}</TableCell>
              <TableCell class="text-xs">{{ e.cc.join(', ') || '—' }}</TableCell>
              <TableCell class="text-xs">{{ e.malos.join(', ') || '—' }}</TableCell>
              <TableCell class="text-xs">
                <div v-for="doc in e.documents" :key="doc">{{ doc }}</div>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>

      <!-- Unmatched group (sub-grouped by reason) -->
      <div v-if="hasMismatches" class="space-y-4">
        <div class="flex items-center gap-2">
          <span
            class="inline-block h-2.5 w-2.5 rounded-full bg-destructive"
            aria-hidden="true"
          />
          <h3 class="text-sm font-semibold text-destructive">
            Unmatched ({{ mismatchCount }})
          </h3>
        </div>

        <div v-if="pdfsWithoutRecipient.length" class="space-y-1">
          <p class="text-xs font-medium text-destructive">
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

        <div v-if="recipientsWithoutPdf.length" class="space-y-1">
          <p class="text-xs font-medium text-destructive">
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
                <TableCell class="text-xs">{{ o.kundennummer ?? '—' }}</TableCell>
                <TableCell class="text-xs">{{ o.malos.join(', ') }}</TableCell>
                <TableCell class="text-xs">{{ o.to.join(', ') || '—' }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </div>
    </div>

    <!-- Matches table (document ↔ Excel recipient matched) -->
    <div v-else-if="tab === 'matches'" class="space-y-2">
      <p class="text-xs font-medium text-green-700 dark:text-green-500">
        Documents successfully matched to a recipient from the Excel mapping
        ({{ matches.length }})
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Customer</TableHead>
            <TableHead>TO</TableHead>
            <TableHead>CC</TableHead>
            <TableHead>MaLos</TableHead>
            <TableHead>Documents</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="(e, i) in matches"
            :key="i"
            class="bg-green-500/10"
          >
            <TableCell class="font-medium">{{ e.unternehmen ?? '—' }}</TableCell>
            <TableCell class="text-xs">{{ e.to.join(', ') || '—' }}</TableCell>
            <TableCell class="text-xs">{{ e.cc.join(', ') || '—' }}</TableCell>
            <TableCell class="text-xs">{{ e.malos.join(', ') || '—' }}</TableCell>
            <TableCell class="text-xs">
              <div v-for="doc in e.documents" :key="doc">{{ doc }}</div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <!-- Documents table -->
    <Table v-else-if="tab === 'documents'">
      <TableHeader>
        <TableRow>
          <TableHead>File</TableHead>
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
          <TableCell class="text-xs">{{ basename(d.filename) }}</TableCell>
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
            <span v-if="d.recipient?.matched">
              {{ d.recipient.to.join(', ') }}
            </span>
            <Badge v-else variant="destructive">unmatched</Badge>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <!-- Emails table -->
    <Table v-else-if="tab === 'emails'">
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
        <TableRow v-for="(e, i) in matchedEmails" :key="i">
          <TableCell>{{ e.unternehmen ?? '—' }}</TableCell>
          <TableCell class="text-xs">{{ e.to.join(', ') || '—' }}</TableCell>
          <TableCell class="text-xs">{{ e.cc.join(', ') || '—' }}</TableCell>
          <TableCell class="text-right">{{ e.documents.length }}</TableCell>
          <TableCell class="text-xs">{{ e.malos.join(', ') || '—' }}</TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <!-- Mismatches tab -->
    <div v-else-if="tab === 'mismatches'" class="space-y-4">
      <div v-if="pdfsWithoutRecipient.length" class="space-y-1">
        <p class="text-xs font-medium text-destructive">
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

      <div v-if="recipientsWithoutPdf.length" class="space-y-1">
        <p class="text-xs font-medium text-destructive">
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
              <TableCell class="text-xs">{{ o.kundennummer ?? '—' }}</TableCell>
              <TableCell class="text-xs">{{ o.malos.join(', ') }}</TableCell>
              <TableCell class="text-xs">{{ o.to.join(', ') || '—' }}</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>
  </div>
</template>
