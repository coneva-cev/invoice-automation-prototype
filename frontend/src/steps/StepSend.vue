<script setup lang="ts">
import { computed } from 'vue';
import { Button } from '@coneva-cev/storybook';
import { Badge } from '@coneva-cev/storybook/badge';
import type { ProcessResponse } from '../types';

const props = defineProps<{ result: ProcessResponse }>();

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
      <h2 class="text-lg font-semibold">4. Send emails</h2>
      <p class="text-muted-foreground text-sm">
        Send one email per customer, bundling all their documents. Email
        sending (SendGrid) is not wired up yet.
      </p>
    </div>

    <div class="flex flex-wrap gap-2">
      <Badge variant="default">{{ sendableEmails }} ready to send</Badge>
      <Badge :variant="blockedEmails ? 'destructive' : 'outline'">
        {{ blockedEmails }} blocked (unmatched)
      </Badge>
    </div>

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
