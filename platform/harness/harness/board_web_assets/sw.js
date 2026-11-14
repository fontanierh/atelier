/* Atelier Board Service Worker: handles native DM notifications and click-to-focus navigation without caching HTML/API. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const targetUrl = new URL(data.url || "/", self.location.origin).href;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of windows) {
        if (new URL(client.url).origin !== self.location.origin) continue;
        client.postMessage({ type: "atelier-open-dm", channelId: data.channelId, rootId: data.rootId || null, url: targetUrl });
        return client.focus();
      }
      return self.clients.openWindow(targetUrl);
    })()
  );
});
