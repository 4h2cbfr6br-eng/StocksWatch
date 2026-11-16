// Service worker: a small script the browser keeps on the device so a
// notification can be shown even when StocksWatch is closed.

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data ? event.data.json() : {} } catch (e) { /* plain text push */ }
  event.waitUntil(
    self.registration.showNotification(data.title || 'StocksWatch', {
      body: data.body || '',
      icon: self.registration.scope + 'icon-192.png',
      // Links are relative to wherever the app is installed.
      data: { url: new URL(data.url || '', self.registration.scope).href },
    })
  )
})

// Tapping a notification opens the stock it is about.
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || self.registration.scope
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if ('focus' in w) { w.navigate(url); return w.focus() }
      }
      return self.clients.openWindow(url)
    })
  )
})
