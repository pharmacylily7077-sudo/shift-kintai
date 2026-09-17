const CACHE_NAME = 'pharmacy-kintai-v2';
const ASSETS_TO_CACHE = [
  '/static/css/style.css',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/manifest.json'
];

// インストール時にコアアセットをキャッシュ
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

// アクティベーション時に古いキャッシュを整理
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetchイベント処理（APIやHTMLページはネットワークファースト）
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // POST等の更新系、API通信、およびJavaScriptファイルはキャッシュせず通常通信
  if (event.request.method !== 'GET' || url.pathname.startsWith('/api/') || url.pathname.endsWith('.js')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // 成功したレスポンスをキャッシュに複製保存（CSSや画像アセット等）
        if (response.status === 200 && url.pathname.startsWith('/static/') && !url.pathname.endsWith('.js')) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // オフライン時はキャッシュから返す
        return caches.match(event.request);
      })
  );
});
