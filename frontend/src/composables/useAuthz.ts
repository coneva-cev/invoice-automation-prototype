import { computed } from 'vue';
import { useAuth0 } from '@auth0/auth0-vue';

/**
 * Central authorization logic for the frontend.
 *
 * The role that gates the app and the ID-token claim that carries the user's
 * roles are configured in ONE place (env vars). Components never hardcode the
 * role name.
 *
 * We gate on the Auth0 role (present in the `coneva/roles` ID-token claim)
 * rather than the API `permissions` claim, because Auth0 surfaces roles to the
 * SPA via the ID token, whereas `permissions` live only in the access token
 * (and would otherwise require a custom Auth0 Action to expose).
 *
 * Note: this is a UX gate only. The backend independently enforces the required
 * API permission on every request, so it remains authoritative even if the
 * frontend is bypassed.
 */

/** Role required to use the app (present in the roles claim). */
export const REQUIRED_ROLE: string =
  import.meta.env.VITE_REQUIRED_ROLE ?? 'Invoice Automation Admin';

/** ID-token claim that lists the user's Auth0 roles. */
const ROLES_CLAIM: string =
  import.meta.env.VITE_ROLES_CLAIM ?? 'coneva/roles';

export function useAuthz() {
  const { user, isAuthenticated, isLoading } = useAuth0();

  const roles = computed<string[]>(() => {
    const claim = user.value?.[ROLES_CLAIM];
    return Array.isArray(claim) ? (claim as string[]) : [];
  });

  const isAdmin = computed<boolean>(() => roles.value.includes(REQUIRED_ROLE));

  return {
    isAuthenticated,
    isLoading,
    isAdmin,
    roles,
    requiredRole: REQUIRED_ROLE,
  };
}
