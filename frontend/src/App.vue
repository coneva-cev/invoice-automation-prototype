<script setup lang="ts">
import { ref, onMounted } from 'vue';
import UploadView from './views/UploadView.vue';

const backendStatus = ref<'checking' | 'online' | 'offline'>('checking');

async function checkBackend() {
  backendStatus.value = 'checking';
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    backendStatus.value = data?.status === 'ok' ? 'online' : 'offline';
  } catch {
    backendStatus.value = 'offline';
  }
}

onMounted(checkBackend);
</script>

<template>
  <main class="min-h-screen bg-background text-foreground">
    <header class="border-b">
      <div
        class="mx-auto flex max-w-5xl items-center justify-between px-6 py-4"
      >
        <span class="font-semibold">Invoice Automation</span>
        <div class="flex items-center gap-2 text-xs">
          <span
            class="inline-block h-2 w-2 rounded-full"
            :class="{
              'bg-yellow-400': backendStatus === 'checking',
              'bg-green-500': backendStatus === 'online',
              'bg-red-500': backendStatus === 'offline',
            }"
          />
          <span class="text-muted-foreground">
            API {{ backendStatus }}
          </span>
        </div>
      </div>
    </header>

    <div class="mx-auto max-w-5xl px-6 py-10">
      <UploadView />
    </div>
  </main>
</template>
