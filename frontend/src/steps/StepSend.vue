<script setup lang="ts">
import { computed, ref } from 'vue';
import { Button } from '@coneva-cev/storybook';
import { Badge } from '@coneva-cev/storybook/badge';
import { Spinner } from '@coneva-cev/storybook/spinner';
import { useApi } from '../composables/useApi';
import type { ProcessResponse } from '../types';

const props = defineProps<{ result: ProcessResponse }>();

const { apiFetch } = useApi();

const downloading = ref(false);
const downloadError = ref<string | null>(null);

const sendableEmails = computed(
  () => props.result.emails.filter((e) => e.matched).length,
);
const blockedEmails = computed(
  () => props.result.emails.filter((e) => !e.matched).length,
);

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
      <div class="flex items-center gap-3">
        <Button variant="outline" :disabled="downloading" @click="downloadBundle">
          <Spinner v-if="downloading" class="mr-2 h-4 w-4" />
          {{ downloading ? 'Preparing…' : 'Download PDF bundle (.zip)' }}
        </Button>
        <span v-if="downloadError" class="text-sm text-destructive">
          {{ downloadError }}
        </span>
      </div>
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
