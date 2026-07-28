import { useAuth0 } from '@auth0/auth0-vue';

/**
 * Thin fetch wrapper that attaches an Auth0 Bearer token to every request.
 *
 * Usage:
 *   const { apiFetch } = useApi();
 *   const data = await apiFetch('/api/excel/parse', { method: 'POST', body: formData });
 */
export function useApi() {
  const { getAccessTokenSilently } = useAuth0();

  async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const token = await getAccessTokenSilently();

    const headers = new Headers(options.headers);
    headers.set('Authorization', `Bearer ${token}`);

    return fetch(url, { ...options, headers });
  }

  return { apiFetch };
}
