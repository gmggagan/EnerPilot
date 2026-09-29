// Thin client for the ENERPILOT FastAPI backend.
// In dev, Vite proxies /api to the backend (see vite.config.js).
// For a static deployment set VITE_API_BASE to the backend origin.
const BASE = (import.meta.env.VITE_API_BASE || '').trim().replace(/\/+$/, '') + '/api/v1';

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = JSON.stringify((await res.json()).detail); } catch { /* keep status text */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

const qs = (params) =>
  '?' + Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');

export const api = {
  health: () => request('/health'),
  household: () => request('/household/default'),
  dashboard: (p) => request('/dashboard' + qs(p)),
  planOptimize: (body) => request('/optimization/plan', { method: 'POST', body: JSON.stringify(body) }),
  pvSimulate: (body) => request('/pv/simulate', { method: 'POST', body: JSON.stringify(body) }),
  metrics: () => request('/model/metrics'),
  historical: (days) => request('/historical' + qs({ days })),
};
