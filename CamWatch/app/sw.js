self.addEventListener('install', function(e) { self.skipWaiting(); });
self.addEventListener('activate', function(e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function(e) {
  if (e.request.url.includes('/api/')) {
    e.respondWith(fetch(e.request).catch(function() { return new Response(JSON.stringify({error: "offline"})), {headers: {"Content-Type": "application/json"}}); }));
  } else {
    e.respondWith(fetch(e.request));
  }
});