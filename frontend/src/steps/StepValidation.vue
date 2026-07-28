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

const tab = ref<'documents' | 'emails'>('documents');

const pdfsWithoutRecipient = computed(
  () => props.result.documents.filter((d) => !d.recipient?.matched) ?? [],
);
const recipientsWithoutPdf = computed(
  () => props.result.orphan_recipients ?? [],
);
const hasMismatches = computed(
  () =>
    pdfsWithoutRecipient.value.length > 0 ||
    recipientsWithoutPdf.value.length > 0,
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
      <Badge variant="default">{{ result.summary.emails_to_send }} emails</Badge>
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

    <!-- Mismatches -->
    <div
      v-if="hasMismatches"
      class="rounded-lg border border-destructive/40 bg-destructive/5 p-4 space-y-4"
    >
      <h3 class="text-sm font-semibold text-destructive">
        Mismatches to resolve
      </h3>

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
              <TableCell class="text-xs">{{ o.kundennummer ?? '—' }}</TableCell>
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
            <span v-if="d.recipient?.matched">
              {{ d.recipient.to.join(', ') }}
            </span>
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
  </div>
</template>
