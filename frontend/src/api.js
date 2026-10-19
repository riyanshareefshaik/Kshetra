import { accessToken } from "./auth.js";

export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  const token = await accessToken();
  const headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.blob();
}

const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const form = (entries) => {
  const f = new FormData();
  for (const [k, v] of Object.entries(entries)) if (v != null && v !== "") f.append(k, v);
  return { method: "POST", body: f };
};
const qs = (params) => new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== "")).toString();

export const api = {
  fields: () => request("/api/fields"),
  field: (id) => request(`/api/fields/${id}`),
  createField: (body) => request("/api/fields", json("POST", body)),
  updateField: (id, body) => request(`/api/fields/${id}`, json("PATCH", body)),
  deleteField: (id) => request(`/api/fields/${id}`, { method: "DELETE" }),
  refreshField: (id) => request(`/api/fields/${id}/refresh`, { method: "POST" }),
  autoBoundary: (lat, lon) => request("/api/fields/auto-boundary", json("POST", { lat, lon })),
  timeseries: (id, params) => request(`/api/fields/${id}/timeseries?${qs(params)}`),
  seasons: (id) => request(`/api/fields/${id}/seasons`),
  events: (id) => request(`/api/fields/${id}/events`),
  confirmSeason: (sid, body) => request(`/api/seasons/${sid}`, json("PATCH", body)),
  why: (sid) => request(`/api/seasons/${sid}/why`),
  twins: (sid) => request(`/api/seasons/${sid}/twins`),
  varieties: (season) => request(`/api/crop-varieties${season ? `?season=${season}` : ""}`),
  whatIf: (id, body, signal) => request(`/api/fields/${id}/what-if`, { ...json("POST", body), signal }),
  plan: (id, season) => request(`/api/fields/${id}/plan${season ? `?season=${season}` : ""}`),
  today: (id, crop, sowingDate) => request(`/api/fields/${id}/today?${qs({ crop, sowing_date: sowingDate })}`),
  soilTests: (id) => request(`/api/fields/${id}/soil-tests`),
  addSoilTest: (id, body) => request(`/api/fields/${id}/soil-tests`, json("POST", body)),
  readSoilCard: (id, file) => request(`/api/fields/${id}/soil-tests/card`, form({ image: file })),
  fertilizer: (id, crop, season) => request(`/api/fields/${id}/fertilizer?${qs({ crop, season })}`),
  market: (id, crop) => request(`/api/fields/${id}/market?${qs({ crop })}`),
  claims: (id) => request(`/api/fields/${id}/claims`),
  claimPdf: (id, cid) => request(`/api/fields/${id}/claims/${cid}.pdf`),
  report: (id) => request(`/api/fields/${id}/report.pdf`),
  schemes: () => request("/api/schemes"),
  groups: () => request("/api/groups"),
  createGroup: (body) => request("/api/groups", json("POST", body)),
  joinGroup: (code) => request("/api/groups/join", json("POST", { code })),
  shareGroup: (gid, on) => request(`/api/groups/${gid}/share`, json("PUT", { share_with_group: on })),
  leaveGroup: (gid) => request(`/api/groups/${gid}/members/me`, { method: "DELETE" }),
  groupDashboard: (gid) => request(`/api/groups/${gid}/dashboard`),
  ask: (id, question, language) => request(`/api/fields/${id}/ask`, json("POST", { question, language })),
  askVoice: (id, blob, language) => request(`/api/fields/${id}/ask/voice`, form({ audio: new File([blob], "q.webm"), language })),
  askHistory: (id) => request(`/api/fields/${id}/ask/history`),
  diary: (id) => request(`/api/fields/${id}/diary`),
  addDiary: (id, { text, audio, language, entryDate }) =>
    request(`/api/fields/${id}/diary`, form({ text, audio: audio ? new File([audio], "note.webm") : null, language, entry_date: entryDate })),
  seedPacket: (file, fieldId, language) => request("/api/seed-packet", form({ image: file, field_id: fieldId, language })),
  speak: (text, language) => request("/api/voice/speak", json("POST", { text, language })),
  me: () => request("/api/users/me"),
  updateMe: (body) => request("/api/users/me", { ...json("PATCH", body) }),
  setConsent: (on) => request("/api/users/me/consent", json("PUT", { data_sharing_consent: on })),
  insights: (params) => request(`/api/insights?${qs(params)}`),
};

export function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
