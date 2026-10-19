// Kshetra service worker: works offline in villages with weak internet.
// - App shell and hashed build files: cached, served even offline.
// - Field data (GET /api/...): network first, saved copy when offline.
// - Map tiles: saved as you view them (capped), so your field's map also opens offline.
const SHELL = "kshetra-shell-v1";
const API = "kshetra-api";
const TILES = "kshetra-tiles";
const MAX_TILES = 600;
const SHELL_FILES = ["/", "/index.html", "/manifest.webmanifest", "/favicon.svg", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith("kshetra-shell-") && k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function networkFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req);
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(req, cacheName, limit) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.ok || res.type === "opaque") {
    await cache.put(req, res.clone());
    if (limit) {
      const keys = await cache.keys();
      if (keys.length > limit) await Promise.all(keys.slice(0, keys.length - limit).map((k) => cache.delete(k)));
    }
  }
  return res;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/index.html")));
    return;
  }
  if (url.origin === self.location.origin && (url.pathname.startsWith("/assets/") || SHELL_FILES.includes(url.pathname))) {
    e.respondWith(cacheFirst(req, SHELL));
    return;
  }
  if (url.pathname.startsWith("/api/") && !url.pathname.endsWith(".pdf") && !url.pathname.startsWith("/api/voice")) {
    e.respondWith(networkFirst(req, API));
    return;
  }
  if (url.hostname.endsWith("arcgisonline.com") || url.hostname.endsWith("tile.openstreetmap.org")) {
    e.respondWith(cacheFirst(req, TILES, MAX_TILES));
  }
});
