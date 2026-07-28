<script setup lang="ts">
import { computed } from 'vue';
import { Button } from '@coneva-cev/storybook';
import { Badge } from '@coneva-cev/storybook/badge';
import type { ProcessResponse } from '../types';

const props = defineProps<{ result: ProcessResponse }>();

const bundleUrl = computed(
  () => `/api/upload/batch/${props.result.batch_id}/bundle`,
);
const sendableEmails = computed(
  () => props.result.emails.filter((e) => e.matched).length,
);
const blockedEmails = computed(
  () => props.result.emails.filter((e) => !e.matched).length,
);
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">3. Portal upload &amp; email send</h2>
      <p class="text-muted-foreground text-sm">
        Download the flat PDF bundle for the Portal, then send per-customer
        emails. Email sending (SendGrid) is not wired up yet.
      </p>
    </div>

    <div class="flex flex-wrap gap-2">
      <Badge variant="default">{{ sendableEmails }} ready to send</Badge>
      <Badge :variant="blockedEmails ? 'destructive' : 'outline'">
        {{ blockedEmails }} blocked (unmatched)
      </Badge>
      <Badge variant="outline">{{ result.total }} PDFs in batch</Badge>
    </div>

    <section class="space-y-3 rounded-lg border p-4">
      <h3 class="text-sm font-semibold">Portal bundle</h3>
      <p class="text-xs text-muted-foreground">
        A single ZIP of all classified PDFs, ready for bulk upload to the
        Portal.
      </p>
      <a :href="bundleUrl" download>
        <Button variant="outline">Download PDF bundle (.zip)</Button>
      </a>
    </section>

    <section class="space-y-3 rounded-lg border p-4">
      <h3 class="text-sm font-semibold">Send emails</h3>
      <p class="text-xs text-muted-foreground">
        One email per customer, bundling all their documents. Not implemented
        yet — this is a placeholder for the SendGrid integration.
      </p>
      <Button disabled>Send {{ sendableEmails }} emails (coming soon)</Button>
    </section>
  </div>
</template>
