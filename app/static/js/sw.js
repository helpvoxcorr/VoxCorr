// VoxCorr Service Worker v2
const CACHE_NAME = 'voxcorr-v3';
const urlsToCache = [
  '/',
  '/static/css/voxcorr.css',
  '/static/js/recorder.js',
  '/static/js/modules/api.js',
  '/static/js/modules/ui.js',
  '/static/js/record_page.js',
  '/static/manifest.json',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://unpkg.com/wavesurfer.js@7.4.0/dist/wavesurfer.min.js',
  'https://cdn.plot.ly/plotly-3.1.0.min.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  
  // Exclure les requêtes API et audio (ne pas cacher)
  if (url.pathname.startsWith('/teacher/api/') ||
      url.pathname.startsWith('/student/api/') ||
      url.pathname.includes('/api/') ||
      url.pathname.startsWith('/c/') ||
      url.hostname.includes('cloudinary.com') ||
      url.pathname.endsWith('.mp3') ||
      url.pathname.endsWith('.webm')) {
    event.respondWith(fetch(event.request));
    return;
  }
  
  // Stratégie : cache d'abord, puis réseau
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request).then(
          response => {
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }
            const responseToCache = response.clone();
            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });
            return response;
          }
        );
      })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});