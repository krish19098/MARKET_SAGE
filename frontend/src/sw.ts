/// <reference lib="webworker" />
// Service worker: precaching (installable PWA, offline shell) and Web Push display.
// Monitoring itself runs on the backend; this only shows notifications the server sends.
import { precacheAndRoute } from "workbox-precaching";

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<{ url: string; revision: string | null }> };

precacheAndRoute(self.__WB_MANIFEST);
self.addEventListener("install", () => void self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data: { title?: string; body?: string; url?: string; alert_id?: number } = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "MARKET SAGE", body: event.data?.text() };
  }
  event.waitUntil(
    self.registration.showNotification(data.title ?? "MARKET SAGE alert", {
      body: data.body ?? "",
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      tag: data.alert_id ? `alert-${data.alert_id}` : undefined,
      data: { url: data.url ?? "/alerts" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data as { url?: string })?.url ?? "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
      const w = wins.find((c) => "focus" in c);
      if (w) {
        void (w as WindowClient).navigate(url);
        return (w as WindowClient).focus();
      }
      return self.clients.openWindow(url);
    }),
  );
});
