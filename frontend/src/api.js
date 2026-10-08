export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function getJson(path) {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
