/* Offline support.
   Pages (navigations / HTML): network-first, cache fallback. A phone that is
   online ALWAYS gets the newest HTML — no manual CACHE bump is ever needed
   for an HTML/JS change again.
   Static assets (icons, manifest, audio): cache-first, network refreshes cache.
   Bump CACHE only when the precached asset SET changes. */
const CACHE = 'first-english-v3';
const ASSETS = ['./', 'index.html', 'manifest.json', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
function isNavRequest(req) {
  if (req.mode === 'navigate') return true;
  const acc = req.headers.get('accept') || '';
  return req.destination === 'document' || acc.includes('text/html');
}
self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;
  if (isNavRequest(e.request)) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() =>
          caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || caches.match('index.html'))
        )
    );
    return;
  }
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(
      (hit) =>
        hit ||
        fetch(e.request)
          .then((res) => {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
            return res;
          })
          .catch(() => caches.match('index.html'))
    )
  );
});
