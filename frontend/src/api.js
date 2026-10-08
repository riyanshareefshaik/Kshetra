export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, options);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.blob();
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request("/health"),
  fields: () => request("/api/fields"),
  field: (id) => request(`/api/fields/${id}`),
  createField: (body) => request("/api/fields", json("POST", body)),
  updateField: (id, body) => request(`/api/fields/${id}`, json("PATCH", body)),
  deleteField: (id) => request(`/api/fields/${id}`, { method: "DELETE" }),
  refreshField: (id) => request(`/api/fields/${id}/refresh`, { method: "POST" }),
  autoBoundary: (lat, lon) => request("/api/fields/auto-boundary", json("POST", { lat, lon })),
  timeseries: (id, params) => request(`/api/fields/${id}/timeseries?${new URLSearchParams(params)}`),
  seasons: (id) => request(`/api/fields/${id}/seasons`),
  events: (id) => request(`/api/fields/${id}/events`),
  confirmSeason: (sid, body) => request(`/api/seasons/${sid}`, json("PATCH", body)),
  why: (sid) => request(`/api/seasons/${sid}/why`),
  twins: (sid) => request(`/api/seasons/${sid}/twins`),
  varieties: (season) => request(`/api/crop-varieties${season ? `?season=${season}` : ""}`),
  whatIf: (id, body, signal) => request(`/api/fields/${id}/what-if`, { ...json("POST", body), signal }),
  plan: (id, season) => request(`/api/fields/${id}/plan${season ? `?season=${season}` : ""}`),
  ask: (id, question, language) => request(`/api/fields/${id}/ask`, json("POST", { question, language })),
  askVoice: (id, blob, language) => {
    const form = new FormData();
    form.append("audio", blob, "question.webm");
    form.append("language", language);
    return request(`/api/fields/${id}/ask/voice`, { method: "POST", body: form });
  },
  askHistory: (id) => request(`/api/fields/${id}/ask/history`),
  diary: (id) => request(`/api/fields/${id}/diary`),
  addDiary: (id, { text, audio, language, entryDate }) => {
    const form = new FormData();
    if (text) form.append("text", text);
    if (audio) form.append("audio", audio, "note.webm");
    form.append("language", language);
    if (entryDate) form.append("entry_date", entryDate);
    return request(`/api/fields/${id}/diary`, { method: "POST", body: form });
  },
  seedPacket: (file, fieldId, language) => {
    const form = new FormData();
    form.append("image", file);
    if (fieldId) form.append("field_id", fieldId);
    form.append("language", language);
    return request("/api/seed-packet", { method: "POST", body: form });
  },
  speak: (text, language) => request("/api/voice/speak", json("POST", { text, language })),
  reportUrl: (id) => `${API_URL}/api/fields/${id}/report.pdf`,
  demoUser: () => request("/api/users/demo"),
  setConsent: (uid, on) => request(`/api/users/${uid}/consent`, json("PUT", { data_sharing_consent: on })),
  insights: (params) => request(`/api/insights?${new URLSearchParams(params)}`),
};
