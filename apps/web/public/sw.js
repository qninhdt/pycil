// Pycil PWA service worker (P11 phases 1-3).
//
// Responsibilities:
//   1. Cache static shell + JS/CSS so the app boots offline.
//   2. Background-sync queue for offline study answers.
//   3. Display web push notifications routed via VAPID.
//
// Registered from `apps/web/src/lib/pwa-register.ts` on first load. Bumping
// CACHE_VERSION invalidates clients on the next service-worker update cycle.

const CACHE_VERSION = "pycil-v1";
const PRECACHE_URLS = [
  "/",
  "/dashboard",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(PRECACHE_URLS)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_VERSION)
          .map((k) => caches.delete(k)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  if (req.url.includes("/api/")) return;
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((res) => {
          if (!res.ok || !res.type.startsWith("basic")) return res;
          const copy = res.clone();
          caches.open(CACHE_VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match("/"));
    }),
  );
});

self.addEventListener("push", (event) => {
  if (!event.data) return;
  let payload = { title: "Pycil", body: "Time to study", data: {} };
  try {
    payload = { ...payload, ...event.data.json() };
  } catch {
    payload.body = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: payload.data,
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/dashboard";
  event.waitUntil(self.clients.openWindow(url));
});

self.addEventListener("sync", (event) => {
  if (event.tag === "pycil-answer-queue") {
    event.waitUntil(flushAnswerQueue());
  }
});

async function flushAnswerQueue() {
  const clients = await self.clients.matchAll({ includeUncontrolled: true });
  for (const c of clients) c.postMessage({ type: "SYNC_FLUSH" });
}
