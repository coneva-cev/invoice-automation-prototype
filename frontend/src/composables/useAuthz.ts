import { computed } from 'vue';
import { useAuth0 } from '@auth0/auth0-vue';

/**
 * Central authorization logic for the frontend.
 *
 * The permission that gates the app and its namespaced ID-token claim are
 * configured in ONE place (env vars), mirroring the backend's single
 * `REQUIRED_PERMISSION`. Components never hardcode the permission name.
 *
 * Auth0 does not surface access-token `permissions` to the SPA, so an Auth0
 * Action copies them into a namespaced ID-token claim (VITE_PERMISSIONS_CLAIM),
 * which the SDK exposes on the `user` object / id token claims.
 *
 * Note: this is a UX gate only. The backend enforces the same permission on
 * every API call, so it remains authoritative even if the frontend is bypassed.
 */

/** Permission required to use the app (matches backend REQUIRED_PERMISSION). */
export const REQUIRED_PERMISSION: string =
  import.meta.env.VITE_REQUIRED_PERMISSION ?? 'admin';

/** Namespaced ID-token claim populated by the Auth0 Action with the user's permissions. */
const PERMISSIONS_CLAIM: string =
  import.meta.env.VITE_PERMISSIONS_CLAIM ??
  'https://invoice-automation/permissions';

export function useAuthz() {
  const { user, isAuthenticated, isLoading } = useAuth0();

  const permissions = computed<string[]>(() => {
    const claim = user.value?.[PERMISSIONS_CLAIM];
    return Array.isArray(claim) ? (claim as string[]) : [];
  });

  const isAdmin = computed<boolean>(() =>
    permissions.value.includes(REQUIRED_PERMISSION),
  );

  return {
    isAuthenticated,
    isLoading,
    isAdmin,
    permissions,
    requiredPermission: REQUIRED_PERMISSION,
  };
}
