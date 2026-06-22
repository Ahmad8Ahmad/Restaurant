{% load i18n %}
const CACHE_NAME = 'tamini-cache-v1';
const STATIC_CACHE = 'tamini-static-v1';

const STATIC_ASSETS = [
  '/static/css/dist.css',
  '/static/leaflet/leaflet.min.css',
  '/static/leaflet/leaflet.min.js',
  'https://fonts.googleapis.com/css2?family=Cairo:wght@200..1000&family=Lalezar&display=swap'
];

self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(k => k !== CACHE_NAME && k !== STATIC_CACHE)
          .map(k => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Only handle GET requests
  if (event.request.method !== 'GET') return;

  // Don't cache API/admin/ws calls
  if (url.pathname.includes('add_to_cart') ||
      url.pathname.includes('update-cart') ||
      url.pathname.includes('remove') ||
      url.pathname.includes('admin') ||
      url.pathname.includes('ws/') ||
      url.pathname.startsWith('/media/')) {
    return;
  }

  // Static assets: Cache First
  if (url.pathname.startsWith('/static/') ||
      url.hostname.includes('fonts.googleapis') ||
      url.hostname.includes('fonts.gstatic')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        return cached || fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(STATIC_CACHE).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // HTML pages / everything else: Network First, fall back to cache
  event.respondWith(
    fetch(event.request).then(response => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
      }
      return response;
    }).catch(() => {
      return caches.match(event.request).then(cached => {
        if (cached) return cached;
        return new Response(
          '<!DOCTYPE html><html dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{% trans "غير متصل" %}</title><link rel="stylesheet" href="/static/css/dist.css"></head><body class="bg-gray-50 flex items-center justify-center min-h-screen"><div class="text-center p-8"><div class="text-6xl mb-4">📡</div><h1 class="text-2xl font-black text-gray-800 mb-2">{% trans "لا يوجد اتصال بالإنترنت" %}</h1><p class="text-gray-500">{% trans "يرجى التحقق من اتصالك والمحاولة مرة أخرى" %}</p></div></body></html>',
          { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      });
    })
  );
});
