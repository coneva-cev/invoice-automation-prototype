<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Button } from '@coneva-cev/storybook';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@coneva-cev/storybook/card';

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
    <div class="mx-auto max-w-4xl px-6 py-16 space-y-10">
      <!-- Hero -->
      <header class="space-y-3 text-center">
        <h1 class="text-4xl font-semibold tracking-tight">Invoice Automation</h1>
        <p class="text-muted-foreground text-base max-w-xl mx-auto">
          Prototype for turning Excel spreadsheets into generated invoice PDFs,
          built on the Coneva Vue component library.
        </p>
      </header>

      <!-- Workflow cards -->
      <section class="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle class="text-base">1. Upload Excel</CardTitle>
            <CardDescription>
              Import your spreadsheet and preview the detected data.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <span class="text-xs text-muted-foreground">Coming soon</span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle class="text-base">2. Review &amp; Map</CardTitle>
            <CardDescription>
              Map columns to invoice fields and validate the entries.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <span class="text-xs text-muted-foreground">Coming soon</span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle class="text-base">3. Generate PDFs</CardTitle>
            <CardDescription>
              Produce invoice PDFs on the server and download them.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <span class="text-xs text-muted-foreground">Coming soon</span>
          </CardContent>
        </Card>
      </section>

      <!-- Status / actions -->
      <section class="flex flex-col items-center gap-4">
        <div class="flex items-center gap-2 text-sm">
          <span
            class="inline-block h-2.5 w-2.5 rounded-full"
            :class="{
              'bg-yellow-400': backendStatus === 'checking',
              'bg-green-500': backendStatus === 'online',
              'bg-red-500': backendStatus === 'offline',
            }"
          />
          <span class="text-muted-foreground">
            Backend API:
            <template v-if="backendStatus === 'checking'">checking…</template>
            <template v-else-if="backendStatus === 'online'">online</template>
            <template v-else>offline (start ./backend/run.sh)</template>
          </span>
        </div>

        <div class="flex items-center gap-3">
          <Button variant="default">Get started</Button>
          <Button variant="outline" @click="checkBackend">Re-check backend</Button>
        </div>
      </section>
    </div>
  </main>
</template>
