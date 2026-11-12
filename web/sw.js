// Service worker: makes the app work offline at venues after one online visit.
//
// - App files (this site): network first, so an online visit always gets
//   the latest version; falls back to the cached copy when offline or when
//   the network takes longer than NETWORK_TIMEOUT_MS (flaky venue Wi-Fi).
//   Requests use cache: "no-cache", so the browser's own HTTP cache always
//   asks the server whether a file changed (a cheap 304 if not). Without
//   it, a copy the HTTP cache still thinks is fresh (GitHub Pages allows
//   10 minutes) could be served right after a deploy.
// - Pyodide runtime (CDN, pinned version): cache first. It never changes
//   for a given version, and it's the big download (~10 MB).
//
// Bump CACHE_VERSION only to force old caches to be dropped. Keep
// PYODIDE_VERSION in step with web/js/engine.js.

const CACHE_VERSION = "1";
const PYODIDE_VERSION = "0.27.2";
const PYODIDE_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const APP_CACHE = `sadrt-app-v${CACHE_VERSION}`;
const RUNTIME_CACHE = `sadrt-pyodide-${PYODIDE_VERSION}`;
const NETWORK_TIMEOUT_MS = 4000;

// Paths relative to this file (web/). ../ reaches the shared Python files.
const APP_FILES = [
  "./",
  "index.html",
  "selftest.html",
  "manifest.webmanifest",
  "icon.svg",
  "css/style.css",
  "js/app.js",
  "js/engine.js",
  "js/selftest.js",
  "js/help.js",
  "py/bridge.py",
  "py/model.py",
  "../shared/array_math.py",
  "../shared/jsonable.py",
  "../shared/version.py",
  "../shared/sub_profiles.py",
  "../shared/sub_profiles.csv",
  "../shared/prealign_profiles.py",
  "../shared/prealign_delays.csv",
  "../tests/parity_common.py",
  "../tests/parity_cases.json",
];

const RUNTIME_FILES = [
  "pyodide.mjs",
  "pyodide.asm.js",
  "pyodide.asm.wasm",
  "python_stdlib.zip",
  "pyodide-lock.json",
].map((f) => PYODIDE_BASE + f);

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const app = await caches.open(APP_CACHE);
    await app.addAll(APP_FILES.map((p) => new Request(new URL(p, self.location), { cache: "reload" })));
    const runtime = await caches.open(RUNTIME_CACHE);
    const missing = [];
    for (const url of RUNTIME_FILES) {
      if (!(await runtime.match(url))) missing.push(url);
    }
    await runtime.addAll(missing.map((u) => new Request(u, { mode: "cors" })));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keep = new Set([APP_CACHE, RUNTIME_CACHE]);
    for (const name of await caches.keys()) {
      if (name.startsWith("sadrt-") && !keep.has(name)) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

async function networkFirst(request) {
  const cache = await caches.open(APP_CACHE);
  try {
    const response = await Promise.race([
      fetch(request, { cache: "no-cache" }),
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), NETWORK_TIMEOUT_MS)),
    ]);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (e) {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    throw e;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request.url);
  if (cached) return cached;
  // Re-request in CORS mode so the cached response isn't opaque.
  const response = await fetch(new Request(request.url, { mode: "cors" }));
  if (response.ok) cache.put(request.url, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  if (request.url.startsWith(PYODIDE_BASE)) {
    event.respondWith(cacheFirst(request));
  } else if (new URL(request.url).origin === self.location.origin) {
    event.respondWith(networkFirst(request));
  }
});
