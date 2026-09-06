/* ==========================================================================
   api.js — thin fetch wrapper around the Operation Nexus backend API.
   All calls are GET/POST JSON. No external API key required anywhere.
   ========================================================================== */

const API_BASE = window.NEXUS_API_BASE || "http://127.0.0.1:8000";

async function apiGet(path, params) {
  let url = API_BASE + path;
  if (params) {
    const qs = new URLSearchParams(params).toString();
    if (qs) url += "?" + qs;
  }
  const res = await fetch(url);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || body.detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body;
}

async function apiPost(path, payload) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || body.detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body;
}

const Api = {
  health: () => apiGet("/api/health"),
  loadDemo: () => apiPost("/api/demo/load"),
  dashboard: () => apiGet("/api/dashboard"),
  cases: () => apiGet("/api/cases"),
  case: (id) => apiGet(`/api/cases/${id}`),
  caseGraph: (id, before) => apiGet(`/api/cases/${id}/graph`, before ? { before } : null),
  entities: (q, entity_type) => apiGet("/api/entities", { ...(q ? { q } : {}), ...(entity_type ? { entity_type } : {}) }),
  entity: (id) => apiGet(`/api/entities/${id}`),
  neighbors: (id) => apiGet(`/api/entities/${id}/neighbors`),
  evidence: (id) => apiGet(`/api/evidence/${id}`),
  relationship: (id) => apiGet(`/api/relationships/${id}`),
  analytics: (caseId) => apiGet(`/api/analytics/${caseId}`),
  reviewQueue: () => apiGet("/api/entity-resolution/review"),
  acceptMatch: (relId) => apiPost(`/api/entity-resolution/${relId}/accept`),
  rejectMatch: (relId) => apiPost(`/api/entity-resolution/${relId}/reject`),
  potentialLinks: (caseId) => apiGet(`/api/potential-links/${caseId}`),
  reviewLink: (linkId, action) => apiPost(`/api/potential-links/${linkId}/review`, { action }),
  timeline: (caseId) => apiGet(`/api/timeline/${caseId}`),
  nlQuery: (q) => apiGet("/api/query", { q }),
  summary: (caseId) => apiGet(`/api/cases/${caseId}/summary`),
};
