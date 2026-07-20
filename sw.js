/* くらしの仕組み化 — Service Worker
   PWAのオフライン起動。自分のファイルはネット優先で取得し（更新が届く）、
   オフライン時はキャッシュにフォールバックする。全ファイル同一オリジンで完結（外部CDN無し）。
   通知はNotification APIで、アプリを開いている時のローカル通知をベストエフォートで扱う。 */

const CACHE = "kurashi-v3";

// アプリ本体（オフラインで確実に必要なもの）
const CORE = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./icon-192.png",
  "./icon-512.png",
  "./apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const sameOrigin = new URL(req.url).origin === self.location.origin;

  if (sameOrigin) {
    // 自分のアプリのファイル（index.html, main.py, style.css …）は「ネット優先」。
    // → 更新したファイルが確実に反映される。オフライン時だけキャッシュにフォールバック。
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(req, copy).catch(() => {}));
        return res;
      }).catch(() => caches.match(req))
    );
  } else {
    // CDN（PyScript / Pyodide＝大きくて変わらない）は「キャッシュ優先」で高速＆オフライン対応。
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy).catch(() => {}));
          return res;
        });
      })
    );
  }
});

// 通知（開いている時のローカル通知のベストエフォート）
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const c of list) { if ("focus" in c) return c.focus(); }
      if (self.clients.openWindow) return self.clients.openWindow("./index.html");
    })
  );
});
