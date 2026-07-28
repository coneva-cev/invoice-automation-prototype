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

// Default to the mismatches tab when there's something to resolve.
const tab = ref<'documents' | 'emails' | 'mismatches'>(
  hasMismatches.value ? 'mismatches' : 'documents',
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
        Emails ({{ matchedEmails.length }})
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
