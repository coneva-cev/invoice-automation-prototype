import { useAuth0 } from '@auth0/auth0-vue';

/**
 * Thin fetch wrapper that attaches an Auth0 Bearer token to every request.
 *
 * Usage:
 *   const { apiFetch } = useApi();
 *   const data = await apiFetch('/api/excel/parse', { method: 'POST', body: formData });
 */
export function useApi() {
  const { getAccessTokenSilently, loginWithRedirect } = useAuth0();

  async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
    let token: string;
    try {
      token = await getAccessTokenSilently();
    } catch (err) {
      // Silent renewal can fail if the session/refresh token is missing or
      // expired (e.g. a stale refresh token from before `offline_access` was
      // requested). Recover by sending the user through a fresh login rather
      // than surfacing a cryptic "Missing Refresh Token" error into the UI.
      await loginWithRedirect({ appState: { target: window.location.pathname } });
      throw err;
    }

    const headers = new Headers(options.headers);
    headers.set('Authorization', `Bearer ${token}`);

    return fetch(url, { ...options, headers });
  }

  return { apiFetch };
}
