<script setup lang="ts">
import { computed, ref } from 'vue';
import { Button } from '@coneva-cev/storybook';
import { Spinner } from '@coneva-cev/storybook/spinner';
import StepUpload from '../steps/StepUpload.vue';
import StepValidation from '../steps/StepValidation.vue';
import StepSend from '../steps/StepSend.vue';
import type { ProcessResponse, StepId } from '../types';

const STEPS: { id: StepId; label: string }[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'validation', label: 'Validation' },
  { id: 'send', label: 'Send' },
];

const step = ref<StepId>('upload');
const stepIndex = computed(() => STEPS.findIndex((s) => s.id === step.value));

const pdfFiles = ref<File[]>([]);
const mappingFile = ref<File | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const result = ref<ProcessResponse | null>(null);

const canProcess = computed(
  () => pdfFiles.value.length > 0 && !!mappingFile.value && !loading.value,
);

async function process(): Promise<boolean> {
  if (!canProcess.value) return false;
  loading.value = true;
  error.value = null;
  try {
    const fd = new FormData();
    for (const f of pdfFiles.value) fd.append('files', f);
    fd.append('mapping_file', mappingFile.value as File);
    const res = await fetch('/api/upload/process', {
      method: 'POST',
      body: fd,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${res.status}`);
    }
    result.value = (await res.json()) as ProcessResponse;
    return true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    return false;
  } finally {
    loading.value = false;
  }
}

// Re-run processing if the inputs changed since the last result.
async function goNext() {
  if (step.value === 'upload') {
    const ok = await process();
    if (ok) step.value = 'validation';
  } else if (step.value === 'validation') {
    step.value = 'send';
  }
}

function goBack() {
  const idx = stepIndex.value;
  if (idx > 0) step.value = STEPS[idx - 1].id;
}

const nextLabel = computed(() => {
  if (step.value === 'upload') return 'Continue to validation';
  if (step.value === 'validation') return 'Continue to send';
  return '';
});
const showNext = computed(() => step.value !== 'send');
const nextDisabled = computed(() => {
  if (step.value === 'upload') return !canProcess.value;
  return false;
});
</script>

<template>
  <div class="space-y-8">
    <header class="space-y-1">
      <h1 class="text-2xl font-semibold tracking-tight">Invoice Automation</h1>
      <p class="text-muted-foreground text-sm">
        Upload PDFs, validate the recipient mapping, then bundle for the Portal
        and send emails.
      </p>
    </header>

    <!-- Stepper -->
    <ol class="flex items-center gap-2 text-sm">
      <li
        v-for="(s, i) in STEPS"
        :key="s.id"
        class="flex items-center gap-2"
      >
        <span
          class="flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium"
          :class="
            i <= stepIndex
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-muted-foreground'
          "
        >
          {{ i + 1 }}
        </span>
        <span
          :class="
            i === stepIndex
              ? 'font-medium text-foreground'
              : 'text-muted-foreground'
          "
        >
          {{ s.label }}
        </span>
        <span
          v-if="i < STEPS.length - 1"
          class="mx-2 h-px w-8 bg-border"
          aria-hidden="true"
        />
      </li>
    </ol>

    <!-- Active step -->
    <StepUpload
      v-if="step === 'upload'"
      v-model:pdf-files="pdfFiles"
      v-model:mapping-file="mappingFile"
    />
    <StepValidation
      v-else-if="step === 'validation' && result"
      :result="result"
    />
    <StepSend v-else-if="step === 'send' && result" :result="result" />

    <!-- Navigation -->
    <div class="flex items-center gap-3 border-t pt-4">
      <Button
        v-if="stepIndex > 0"
        variant="outline"
        :disabled="loading"
        @click="goBack"
      >
        Back
      </Button>
      <Button v-if="showNext" :disabled="nextDisabled" @click="goNext">
        <Spinner v-if="loading" class="mr-2 h-4 w-4" />
        {{ loading ? 'Processing…' : nextLabel }}
      </Button>
      <span v-if="error" class="text-sm text-destructive">{{ error }}</span>
    </div>
  </div>
</template>
