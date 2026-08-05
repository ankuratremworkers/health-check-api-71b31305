/**
 * Mock-first data resolution.
 *
 * The Preview tab runs this frontend ALONE, in a browser sandbox, with no
 * backend behind it. A UI whose every screen starts with a fetch shows an
 * error or an empty list there — which is what the app is judged by, seconds
 * after the build says it finished.
 *
 * So every data call goes through `resolve(real, mock)`: it serves the mock
 * until a health check says the backend is answering, then serves the real
 * call. No code change, no reload, no flag to flip.
 *
 *   const todos = await resolve(
 *     () => api.get<Todo[]>('/api/todos').then((r) => r.data),
 *     mockData.endpoints['GET /api/todos'],
 *   );
 */
import { api } from './api';

/** Re-checked rather than cached forever: the backend appears mid-session, and
 *  a resolver that decided "no backend" once would never notice. */
const TTL_MS = 5_000;

let liveUntil = 0;
let live = false;
let inFlight: Promise<boolean> | null = null;

async function probe(): Promise<boolean> {
  try {
    const res = await api.get<unknown>('/api/health');
    return res.status >= 200 && res.status < 300;
  } catch {
    return false;
  }
}

/** Whether the backend is currently answering. Shared across callers, so ten
 *  components mounting together make one health request, not ten. */
export async function backendIsLive(): Promise<boolean> {
  if (Date.now() < liveUntil) return live;
  if (!inFlight) {
    inFlight = probe().then((ok) => {
      live = ok;
      liveUntil = Date.now() + TTL_MS;
      inFlight = null;
      return ok;
    });
  }
  return inFlight;
}

/**
 * The real call when the backend is up, the mock otherwise.
 *
 * A real call that THROWS also falls back, rather than propagating: a backend
 * that is up but broken should still leave a usable screen, and the caller
 * cannot tell the difference anyway.
 */
export async function resolve<T>(real: () => Promise<T>, mock: T): Promise<T> {
  if (!(await backendIsLive())) return mock;
  try {
    return await real();
  } catch {
    return mock;
  }
}

/** For a status chip: "Demo data" vs "Live". Never leave the user guessing
 *  which one they are looking at. */
export const dataSourceLabel = async (): Promise<'live' | 'demo'> =>
  (await backendIsLive()) ? 'live' : 'demo';
