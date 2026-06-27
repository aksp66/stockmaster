/**
 * ╔══════════════════════════════════════════════════════════════════╗
 * ║  STOCKMASTER PWA — Service Worker v1.0                          ║
 * ║  Fichier : static/pwa/sw.js                                     ║
 * ║                                                                  ║
 * ║  Stratégies :                                                    ║
 * ║   - Statiques (CSS/JS/fonts) : Cache First                      ║
 * ║   - Pages HTML              : Network First + fallback offline   ║
 * ║   - API REST                : Network First + sync différée     ║
 * ╚══════════════════════════════════════════════════════════════════╝
 */

const APP_VERSION    = "stockmaster-v1.0.0";
const CACHE_STATIC   = `${APP_VERSION}-static`;
const CACHE_PAGES    = `${APP_VERSION}-pages`;
const CACHE_API      = `${APP_VERSION}-api`;
const SYNC_QUEUE_KEY = "stockmaster-sync-queue";

// ── Ressources précachées au premier install ──────────────────────────
const STATIC_ASSETS = [
  "/static/pwa/offline.html",
  "/static/pwa/manifest.json",
  "/static/pwa/icons/icon-72.png",
  "/static/pwa/icons/icon-96.png",
  "/static/pwa/icons/icon-128.png",
  "/static/pwa/icons/icon-192.png",
  "/static/pwa/icons/icon-512.png",
  "/static/pwa/app.js",
  "/static/sounds/beep_ok.mp3",
  "/static/sounds/beep_err.mp3",
];

// ── URLs API à mettre en cache pour consultation offline ──────────────
const API_CACHE_PATTERNS = [
  /\/api\/v1\/produits\/$/,
  /\/api\/v1\/produits\/alertes\//,
  /\/api\/v1\/categories\//,
  /\/api\/v1\/entrepots\//,
  /\/api\/v1\/mobile\/dashboard\//,
];

// ── Pages shell (navigation principale) ──────────────────────────────
const SHELL_PAGES = [
  "/magasinier/",
  "/magasinier/scan/",
  "/magasinier/stocks/",
  "/magasinier/alertes/",
];


// ════════════════════════════════════════════════════════════════════
//  INSTALL — Précache les assets critiques
// ════════════════════════════════════════════════════════════════════

self.addEventListener("install", event => {
  console.log("[SW] Installation…");
  event.waitUntil(
    caches.open(CACHE_STATIC)
      .then(cache => {
        // Ajouter les assets un par un pour éviter qu'un seul échec bloque tout
        return Promise.allSettled(
          STATIC_ASSETS.map(url =>
            cache.add(url).catch(err => console.warn(`[SW] Impossible de cacher : ${url}`, err))
          )
        );
      })
      .then(() => {
        console.log("[SW] Assets statiques mis en cache.");
        return self.skipWaiting();  // Activer immédiatement sans attendre la fermeture des onglets
      })
  );
});


// ════════════════════════════════════════════════════════════════════
//  ACTIVATE — Nettoyage des anciens caches
// ════════════════════════════════════════════════════════════════════

self.addEventListener("activate", event => {
  console.log("[SW] Activation…");
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys
          .filter(key => key.startsWith("stockmaster-") && key !== CACHE_STATIC
                        && key !== CACHE_PAGES && key !== CACHE_API)
          .map(key => {
            console.log(`[SW] Suppression ancien cache : ${key}`);
            return caches.delete(key);
          })
      );
    }).then(() => self.clients.claim())
  );
});


// ════════════════════════════════════════════════════════════════════
//  FETCH — Routeur de stratégies
// ════════════════════════════════════════════════════════════════════

self.addEventListener("fetch", event => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignorer les requêtes non-GET sauf pour la file de sync
  if (request.method !== "GET") {
    event.respondWith(handleMutation(request));
    return;
  }

  // ── Stratégie 1 : Assets statiques → Cache First ─────────────────
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(request, CACHE_STATIC));
    return;
  }

  // ── Stratégie 2 : API REST → Network First + cache + fallback ────
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirstApi(request));
    return;
  }

  // ── Stratégie 3 : Pages HTML → Network First + fallback offline ──
  if (request.headers.get("accept")?.includes("text/html")) {
    event.respondWith(networkFirstPage(request));
    return;
  }

  // Défaut : réseau simple
  event.respondWith(fetch(request).catch(() => new Response("", { status: 503 })));
});


// ════════════════════════════════════════════════════════════════════
//  STRATÉGIES
// ════════════════════════════════════════════════════════════════════

/** Cache First : retourne le cache, sinon réseau puis met en cache. */
async function cacheFirst(request, cacheName) {
  const cache  = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    return new Response("Asset non disponible hors ligne.", { status: 503 });
  }
}

/** Network First API : réseau → cache → erreur JSON. */
async function networkFirstApi(request) {
  const url   = new URL(request.url);
  const cache = await caches.open(CACHE_API);

  try {
    const response = await fetch(request, { signal: AbortSignal.timeout(5000) });
    if (response.ok && shouldCacheApiResponse(url)) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Hors ligne : chercher dans le cache
    const cached = await cache.match(request);
    if (cached) {
      // Indiquer que la réponse est depuis le cache
      const data = await cached.json();
      return new Response(JSON.stringify({
        ...data,
        _offline: true,
        _cached_at: cached.headers.get("date"),
      }), {
        headers: { "Content-Type": "application/json", "X-From-Cache": "true" }
      });
    }
    return new Response(
      JSON.stringify({ detail: "Hors ligne — données non disponibles.", _offline: true }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

/** Network First Page : réseau → cache → page offline.html. */
async function networkFirstPage(request) {
  const cache = await caches.open(CACHE_PAGES);
  try {
    const response = await fetch(request, { signal: AbortSignal.timeout(8000) });
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;

    // Fallback : page offline
    const offline = await caches.match("/static/pwa/offline.html");
    return offline || new Response(
      "<h1>Hors ligne</h1><p>StockMaster n'est pas accessible. Vérifiez votre connexion.</p>",
      { headers: { "Content-Type": "text/html" } }
    );
  }
}


// ════════════════════════════════════════════════════════════════════
//  MUTATIONS HORS LIGNE (POST/PATCH) — File de synchronisation
// ════════════════════════════════════════════════════════════════════

async function handleMutation(request) {
  // Toujours essayer le réseau d'abord
  try {
    return await fetch(request.clone(), { signal: AbortSignal.timeout(8000) });
  } catch {
    // Hors ligne : mettre dans la file de sync si c'est un mouvement
    if (request.url.includes("/api/v1/mouvements/")) {
      await enqueueSync(request);
      return new Response(JSON.stringify({
        _queued:  true,
        message:  "Mouvement mis en file d'attente. Il sera synchronisé à la reconnexion.",
      }), {
        status:  202,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify({ detail: "Hors ligne — action impossible.", _offline: true }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function enqueueSync(request) {
  const body    = await request.text();
  const headers = {};
  request.headers.forEach((val, key) => { headers[key] = val; });

  const queue = await getSyncQueue();
  queue.push({
    id:        Date.now(),
    url:       request.url,
    method:    request.method,
    headers,
    body,
    timestamp: new Date().toISOString(),
  });
  await setSyncQueue(queue);

  // Enregistrer une tâche Background Sync si disponible
  try {
    const reg = await self.registration;
    await reg.sync.register("sync-mouvements");
    console.log("[SW] Background Sync enregistré.");
  } catch {
    console.warn("[SW] Background Sync non supporté.");
  }
}


// ════════════════════════════════════════════════════════════════════
//  BACKGROUND SYNC — Rejoue la file au retour de connexion
// ════════════════════════════════════════════════════════════════════

self.addEventListener("sync", event => {
  if (event.tag === "sync-mouvements") {
    console.log("[SW] Background Sync déclenché.");
    event.waitUntil(replayQueue());
  }
});

async function replayQueue() {
  const queue = await getSyncQueue();
  if (queue.length === 0) return;

  console.log(`[SW] Rejeu de ${queue.length} requête(s) en attente…`);
  const successes = [];
  const failures  = [];

  for (const item of queue) {
    try {
      const response = await fetch(item.url, {
        method:  item.method,
        headers: item.headers,
        body:    item.body,
      });
      if (response.ok) {
        successes.push(item.id);
        console.log(`[SW] ✅ Requête ${item.id} synchronisée.`);
      } else {
        failures.push(item);
      }
    } catch {
      failures.push(item);
    }
  }

  // Conserver uniquement les échecs
  await setSyncQueue(failures);

  // Notifier les clients
  notifyClients({
    type:     "SYNC_COMPLETE",
    succes:   successes.length,
    echecs:   failures.length,
    message:  `${successes.length} mouvement(s) synchronisé(s).`,
  });
}


// ════════════════════════════════════════════════════════════════════
//  PUSH NOTIFICATIONS
// ════════════════════════════════════════════════════════════════════

self.addEventListener("push", event => {
  if (!event.data) return;
  const data = event.data.json();

  const options = {
    body:    data.message || "Nouvelle alerte StockMaster",
    icon:    "/static/pwa/icons/icon-192.png",
    badge:   "/static/pwa/icons/icon-72.png",
    vibrate: [200, 100, 200],
    data:    { url: data.url || "/magasinier/alertes/" },
    actions: [
      { action: "voir",    title: "Voir l'alerte" },
      { action: "ignorer", title: "Ignorer" },
    ],
    tag:     "stockmaster-alerte",
    renotify: true,
  };

  event.waitUntil(
    self.registration.showNotification(data.title || "StockMaster", options)
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  if (event.action === "voir") {
    event.waitUntil(
      clients.openWindow(event.notification.data.url)
    );
  }
});


// ════════════════════════════════════════════════════════════════════
//  MESSAGES depuis l'app (mise à jour, skip waiting)
// ════════════════════════════════════════════════════════════════════

self.addEventListener("message", event => {
  if (event.data?.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
  if (event.data?.type === "GET_QUEUE_COUNT") {
    getSyncQueue().then(q => {
      event.ports[0]?.postMessage({ count: q.length });
    });
  }
});


// ════════════════════════════════════════════════════════════════════
//  UTILITAIRES
// ════════════════════════════════════════════════════════════════════

function isStaticAsset(url) {
  return url.pathname.startsWith("/static/")
      || url.hostname === "cdnjs.cloudflare.com"
      || url.hostname === "fonts.gstatic.com"
      || url.hostname === "fonts.googleapis.com"
      || url.hostname === "cdn.tailwindcss.com";
}

function shouldCacheApiResponse(url) {
  return API_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname));
}

async function getSyncQueue() {
  try {
    const db  = await openDB();
    const val = await dbGet(db, SYNC_QUEUE_KEY);
    return val ? JSON.parse(val) : [];
  } catch { return []; }
}

async function setSyncQueue(queue) {
  try {
    const db = await openDB();
    await dbPut(db, SYNC_QUEUE_KEY, JSON.stringify(queue));
  } catch { /* IndexedDB indisponible */ }
}

function notifyClients(data) {
  self.clients.matchAll({ type: "window" }).then(clientList => {
    clientList.forEach(client => client.postMessage(data));
  });
}

// ── IndexedDB minimal (clé-valeur) ────────────────────────────────
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("stockmaster-sw", 1);
    req.onupgradeneeded = e => e.target.result.createObjectStore("kv");
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}
function dbGet(db, key) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction("kv", "readonly");
    const req = tx.objectStore("kv").get(key);
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}
function dbPut(db, key, value) {
  return new Promise((resolve, reject) => {
    const tx  = db.transaction("kv", "readwrite");
    const req = tx.objectStore("kv").put(value, key);
    req.onsuccess = () => resolve();
    req.onerror   = e => reject(e.target.error);
  });
}
