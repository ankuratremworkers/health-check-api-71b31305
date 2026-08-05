/**
 * The HTTP client. One place that knows the base URL.
 *
 * Deliberately dependency-free: the scaffold installs no axios, so an `api.ts`
 * that imported it would fail to build. The shape (`.get(...).then(r => r.data)`)
 * matches what the fullstack skill's examples use.
 *
 * VITE_API_URL is the backend BASE, wired at deploy time. Endpoints live under
 * `/api`. Never hardcode localhost — it works in dev and breaks on deploy.
 */
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');

export type Res<T> = { data: T; status: number };

async function request<T>(method: string, path: string, body?: unknown): Promise<Res<T>> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === 'string') detail = j.detail;
    } catch {
      /* keep the status line */
    }
    throw new Error(detail);
  }
  // 204 has no body — reading it as JSON throws, and a delete that "fails"
  // because it succeeded is a confusing bug to chase.
  const data = res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  return { data, status: res.status };
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
  delete: <T>(path: string) => request<T>('DELETE', path),
};

export const apiBaseUrl = () => BASE;
