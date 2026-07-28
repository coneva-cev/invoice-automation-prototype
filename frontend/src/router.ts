import { createRouter, createWebHistory } from 'vue-router';
import { useAuth0 } from '@auth0/auth0-vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('./App.vue'),
    },
  ],
});

router.beforeEach(async () => {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0();

  // Wait for Auth0 SDK to finish its initial check (e.g. callback processing)
  if (isLoading.value) {
    await new Promise<void>((resolve) => {
      const stop = watch(isLoading, (loading) => {
        if (!loading) {
          stop();
          resolve();
        }
      });
    });
  }

  if (!isAuthenticated.value) {
    await loginWithRedirect({
      appState: { targetUrl: window.location.pathname },
    });
    // Navigation will be resumed after the Auth0 redirect callback
    return false;
  }
});

// Needed for the watch import inside the guard
import { watch } from 'vue';

export default router;
