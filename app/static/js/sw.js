/* VoxCorr Service Worker
 * RÈGLE : on ne met JAMAIS en cache les fichiers audio Cloudinary.
 * Quota iOS Safari : ~50 Mo/domaine. L'audio est streamé à la demande.
 */
const CACHE = 'voxcorr-v1';
const AUDIO_HOSTS = ['res.cloudinary.com', 'cloudinary.com'];
const PRECACHE = [
  '/static/css/voxcorr.css',
  '/static/js/recorder.js',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
];

self.addEventListener('install',  e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE))); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))); self.clients.claim(); });

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (AUDIO_HOSTS.some(h => url.hostname.includes(h))) { e.respondWith(fetch(e.request)); return; }
  if (url.pathname.startsWith('/auth/') || url.pathname.startsWith('/teacher/api/')) { e.respondWith(fetch(e.request)); return; }
  if (url.pathname.startsWith('/c/')) {
    e.respondWith(fetch(e.request).then(r => { const c = r.clone(); caches.open(CACHE).then(cache => cache.put(e.request, c)); return r; }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request).then(r => { if (r?.status === 200) { const c = r.clone(); caches.open(CACHE).then(cache => cache.put(e.request, c)); } return r; })));
});
