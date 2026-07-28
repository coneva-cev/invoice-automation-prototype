import { createRouter, createWebHistory } from 'vue-router';
import { authGuard } from '@auth0/auth0-vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('./App.vue'),
    },
  ],
});

// Official Auth0 guard: waits for the SDK to finish restoring the cached
// session (isLoading -> false) before evaluating auth, and only redirects to
// login when the user is genuinely unauthenticated. This avoids the
// re-login-on-refresh race present in a hand-rolled isLoading watcher.
router.beforeEach(authGuard);

export default router;
