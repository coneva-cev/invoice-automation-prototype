<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useAuth0 } from '@auth0/auth0-vue';
import { Button } from '@coneva-cev/storybook';
import { useApi } from './composables/useApi';
import UploadView from './views/UploadView.vue';

const { user, logout } = useAuth0();
const { apiFetch } = useApi();

const backendStatus = ref<'checking' | 'online' | 'offline'>('checking');

async function checkBackend() {
  backendStatus.value = 'checking';
  try {
    // Health endpoint is public — no auth token needed
    const res = await fetch('/api/health');
    const data = await res.json();
    backendStatus.value = data?.status === 'ok' ? 'online' : 'offline';
  } catch {
    backendStatus.value = 'offline';
  }
}

function handleLogout() {
  logout({ logoutParams: { returnTo: window.location.origin } });
}

onMounted(checkBackend);
</script>

<template>
  <main class="min-h-screen bg-background text-foreground">
    <!-- Top navigation bar -->
    <nav class="border-b border-border bg-background/80 backdrop-blur-sm sticky top-0 z-10">
      <div class="mx-auto max-w-5xl px-6 h-14 flex items-center justify-between">
        <span class="font-semibold text-sm tracking-tight">Invoice Automation</span>

        <div class="flex items-center gap-4">
          <!-- Backend status indicator -->
          <div class="flex items-center gap-2 text-xs">
            <span
              class="inline-block h-2 w-2 rounded-full"
              :class="{
                'bg-yellow-400': backendStatus === 'checking',
                'bg-green-500': backendStatus === 'online',
                'bg-red-500': backendStatus === 'offline',
              }"
            />
            <span class="text-muted-foreground">API {{ backendStatus }}</span>
          </div>

          <!-- User info + logout -->
          <div v-if="user" class="flex items-center gap-3">
            <img
              v-if="user.picture"
              :src="user.picture"
              :alt="user.name ?? 'User avatar'"
              class="h-7 w-7 rounded-full object-cover"
            />
            <span class="text-sm text-muted-foreground hidden sm:inline">{{ user.name ?? user.email }}</span>
            <Button variant="outline" size="sm" @click="handleLogout">Log out</Button>
          </div>
        </div>
      </div>
    </nav>

    <div class="mx-auto max-w-5xl px-6 py-10">
      <UploadView />
    </div>
  </main>
</template>
