// Service worker: a small script the browser keeps on the device so a
// notification can be shown even when the app is closed.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { /* plain text push */ }
  event.waitUntil(
    self.registration.showNotification(data.title || 'StocksWatch', { body: data.body || '' })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow('/'));
});
