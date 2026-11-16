// Foulée : service worker minimal, pour installer l'interface comme une appli sur le téléphone.
// Il ne garde rien en cache : tes données restent sur ton serveur. Quand le serveur est
// injoignable (Tailscale déconnecté, serveur arrêté), il affiche une explication au lieu
// de la page d'erreur du navigateur.

const OFFLINE_PAGE = `<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Foulée</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
         font: 16px/1.5 system-ui, sans-serif; background: #f2f5f3; color: #1b2420; }
  @media (prefers-color-scheme: dark) { body { background: #101614; color: #e4ebe7; } }
  main { max-width: 340px; }
  .logo { display: block; margin-bottom: 18px; }
  button { margin-top: 12px; font: inherit; padding: 8px 16px; border-radius: 8px; border: 0;
           background: #182020; color: #fff; }
  @media (prefers-color-scheme: dark) { button { background: #e4ebe7; color: #101614; } }
</style></head>
<body><main>
  <svg viewBox="0 0 32 32" width="48" height="48" class="logo" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#182020"/><rect x="8" y="6" width="5.5" height="20" rx="1.2" fill="#fff"/><rect x="8" y="6" width="16.5" height="5.5" rx="1.2" fill="#fff"/><rect x="8" y="14.5" width="12.5" height="5.5" rx="1.2" fill="#d3263a"/></svg>
  <h1 style="font-size:20px;margin:0 0 8px">Foulée est injoignable</h1>
  <p style="margin:0">Vérifie que Tailscale est connecté sur ce téléphone, puis réessaie.
  Si c'est déjà le cas, le serveur est peut-être arrêté.</p>
  <button onclick="location.reload()">Réessayer</button>
</main></body></html>`;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    fetch(event.request).catch(() => new Response(OFFLINE_PAGE, {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    })),
  );
});
