// The app shell works offline; the feed is fetched fresh when there is a network and
// served from cache when there is not. Figures stay on their publishers' servers.
// Only successful responses are cached, so a 404 or 500 during a deploy never sticks.
const SHELL = "ff-shell-v5";
const DATA = "ff-data";
const FILES = ["./", "index.html", "style.css", "app.js", "manifest.webmanifest", "icons/ff.svg", "icons/ff-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== SHELL && k !== DATA).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const cache = url.pathname.includes("/data/") ? DATA : SHELL;
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) {
      const copy = r.clone();
      caches.open(cache).then((c) => c.put(e.request, copy));
    }
    return r;
  }).catch(() => caches.match(e.request)));
});
