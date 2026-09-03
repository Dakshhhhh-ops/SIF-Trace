/**
 * API client. Every call returns data or throws an Error with a message the UI
 * can show the user directly - never a raw stack trace.
 */

/**
 * API base.
 *
 * Empty by default, so calls go to a relative /api on the same origin - which is
 * what happens when the backend serves the built frontend, and in local dev via
 * the Vite proxy.
 *
 * For split hosting (frontend on Vercel, backend on Render) set VITE_API_BASE to
 * the backend origin at build time, e.g.
 *     VITE_API_BASE=https://sif-trace.onrender.com
 */
const API_ROOT = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
const BASE = `${API_ROOT}/api`;

/**
 * Write token.
 *
 * A deployment can set SIF_ADMIN_TOKEN so that upload and threshold changes -
 * which mutate state every viewer sees - are not open to anyone with the link.
 * Reads stay public. The token is held per-browser; it is never bundled.
 */
const TOKEN_KEY = "sif-trace-token";

export const auth = {
  get: () => {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch {
      return "";
    }
  },
  set: (t) => {
    try {
      t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* private browsing - the token simply will not persist */
    }
  },
};

function withToken(options = {}) {
  const token = auth.get();
  if (!token) return options;
  return { ...options, headers: { ...(options.headers || {}), "X-SIF-Token": token } };
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, withToken(options));
  } catch {
    throw new Error(
      API_ROOT
        ? `Cannot reach the SIF-Trace API at ${API_ROOT}. The backend may be waking up - free hosting sleeps when idle, so the first request can take up to a minute. Retry shortly.`
        : "Cannot reach the SIF-Trace API. Start the backend with: uvicorn main:app --port 8000"
    );
  }

  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status-based message */
    }
    throw new Error(detail);
  }
  return res.json();
}

const qs = (params) => {
  const sp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== "all") sp.append(k, v);
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  health: () => request("/health"),
  kpis: () => request("/kpis"),
  filters: () => request("/filters"),
  reports: (params) => request(`/reports${qs(params)}`),
  report: (id) => request(`/reports/${encodeURIComponent(id)}`),
  siteRanking: () => request("/rankings/sites"),
  activityRanking: () => request("/rankings/activities"),
  iogpRules: () => request("/iogp-rules"),
  patterns: (params) => request(`/patterns${qs(params)}`),
  headlinePatterns: (n = 8) => request(`/patterns/headline${qs({ n })}`),
  alerts: (limit = 12) => request(`/alerts${qs({ limit })}`),
  validation: () => request("/validation"),
  reviewQueue: (limit = 100) => request(`/review-queue${qs({ limit })}`),
  settings: () => request("/settings"),

  analyse: (narrative) =>
    request("/analyse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ narrative }),
    }),

  updateThresholds: (patch) =>
    request("/settings/thresholds", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  reloadDemo: () => request("/reload-demo", { method: "POST" }),

  upload: (file, isDemo = true) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/upload${qs({ is_demo: isDemo })}`, { method: "POST", body: fd });
  },
};

export default api;
