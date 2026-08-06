<script setup lang="ts">
import { computed, ref } from 'vue';
import { Button } from '@coneva-cev/storybook';
import { Spinner } from '@coneva-cev/storybook/spinner';
import StepUpload from '../steps/StepUpload.vue';
import StepValidation from '../steps/StepValidation.vue';
import StepPortal from '../steps/StepPortal.vue';
import StepSend from '../steps/StepSend.vue';
import { useApi } from '../composables/useApi';
import type { BulkUploadResult, ProcessResponse, StepId } from '../types';

const { apiFetch } = useApi();

const STEPS: { id: StepId; label: string }[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'validation', label: 'Validation' },
  { id: 'portal', label: 'Upload to Portal' },
  { id: 'send', label: 'Send emails' },
];

const step = ref<StepId>('upload');
const stepIndex = computed(() => STEPS.findIndex((s) => s.id === step.value));

const pdfFiles = ref<File[]>([]);
const mappingFile = ref<File | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const result = ref<ProcessResponse | null>(null);

// Whether the batch was successfully uploaded to the Portal (set by StepPortal).
// Gate leaving the portal step for email sending on an explicit confirmation
// when the upload has not succeeded.
const portalUploaded = ref(false);
const confirmSkipUpload = ref(false);
// Per-file Portal upload result (filename -> "OK" | "ERROR: ..."), used by the
// send step to default-select only successfully-uploaded documents.
const portalUploadResult = ref<BulkUploadResult | null>(null);

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
    const res = await apiFetch('/api/upload/process', {
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
    step.value = 'portal';
  } else if (step.value === 'portal') {
    // Require an explicit confirmation before sending emails if the Portal
    // upload has not succeeded.
    if (!portalUploaded.value && !confirmSkipUpload.value) {
      confirmSkipUpload.value = true;
      return;
    }
    confirmSkipUpload.value = false;
    step.value = 'send';
  }
}

function goBack() {
  confirmSkipUpload.value = false;
  const idx = stepIndex.value;
  if (idx > 0) step.value = STEPS[idx - 1].id;
}

// A step is reachable once a result exists (steps after upload need it).
// You can always go to steps at or before the current one; forward jumps
// require a result to be present.
function canVisit(i: number): boolean {
  if (i === 0) return true;
  if (!result.value) return false;
  return true;
}

function goToStep(i: number) {
  if (!canVisit(i)) return;
  confirmSkipUpload.value = false;
  step.value = STEPS[i].id;
}

const nextLabel = computed(() => {
  if (step.value === 'upload') return 'Continue to validation';
  if (step.value === 'validation') return 'Continue to Portal upload';
  if (step.value === 'portal') return 'Continue to send emails';
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

    <!-- Stepper (clickable breadcrumb) -->
    <ol class="flex items-center gap-2 text-sm">
      <li
        v-for="(s, i) in STEPS"
        :key="s.id"
        class="flex items-center gap-2"
      >
        <button
          type="button"
          class="flex items-center gap-2"
          :class="
            canVisit(i)
              ? 'cursor-pointer'
              : 'cursor-not-allowed opacity-60'
          "
          :disabled="!canVisit(i)"
          @click="goToStep(i)"
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
        </button>
        <span
          v-if="i < STEPS.length - 1"
          class="mx-2 h-px w-8 bg-border"
          aria-hidden="true"
        />
      </li>
    </ol>

    <!-- Navigation (on top) -->
    <div class="flex items-center gap-3 border-b pb-4">
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

      <!-- Confirm proceeding to email send without a successful Portal upload -->
      <span
        v-if="confirmSkipUpload && step === 'portal'"
        class="text-sm text-destructive"
      >
        The bundle was not uploaded to the Portal. Continue to sending emails
        anyway? Press “Continue to send emails” again to confirm.
      </span>
    </div>

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
    <StepPortal
      v-else-if="step === 'portal' && result"
      :result="result"
      @update:uploaded="
        (v: boolean) => {
          portalUploaded = v;
          if (v) confirmSkipUpload = false;
        }
      "
      @update:upload-result="(v) => (portalUploadResult = v)"
    />
    <StepSend
      v-else-if="step === 'send' && result"
      :result="result"
      :upload-result="portalUploadResult"
    />
  </div>
</template>
