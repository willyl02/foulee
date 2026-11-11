// Accès à l'API locale de Foulée. Les requêtes qui modifient quelque chose
// portent l'en-tête X-Foulee, exigé par le serveur.

const cache = new Map();
const CACHE_MS = 20000;
let profileId = null;  // profil pour lequel la page est ouverte (vérifié par le serveur à chaque requête)

/** Le serveur refuse ensuite toute requête si ce navigateur est passé sur un autre profil (autre onglet). */
export function setProfile(id) { profileId = id || null; }

function url(path, params) {
  const query = new URLSearchParams();
  for (const [key, val] of Object.entries(params || {})) {
    if (val !== undefined && val !== null && val !== "") query.set(key, val);
  }
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

async function request(method, path, body) {
  const options = { method, headers: { Accept: "application/json" } };
  if (profileId) options.headers["X-Foulee-Profil"] = profileId;
  if (method !== "GET") {
    options.headers["X-Foulee"] = "1";
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch (e) { /* réponse non JSON */ }
    // Le profil de ce navigateur n'est plus valable (code changé ailleurs…) : retour à « Qui es-tu ? »
    if (response.status === 409 && data?.profil_requis) setTimeout(() => location.reload(), 30);
    const detail = data?.detail || `${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.status === 204 ? null : response.json();
}

export function get(path, params, { fresh = false } = {}) {
  const key = url(path, params);
  const hit = cache.get(key);
  if (!fresh && hit && Date.now() - hit.at < CACHE_MS) return hit.promise;
  const promise = request("GET", key).catch((error) => { cache.delete(key); throw error; });
  cache.set(key, { at: Date.now(), promise });
  return promise;
}

export function clearCache() { cache.clear(); }
export const post = (path, body) => { clearCache(); return request("POST", path, body ?? {}); };
export const put = (path, body) => { clearCache(); return request("PUT", path, body ?? {}); };
export const del = (path) => { clearCache(); return request("DELETE", path); };

/** Envoi d'un fichier tel quel (photo de profil). */
export async function putBlob(path, blob) {
  clearCache();
  const headers = { "X-Foulee": "1", "Content-Type": blob.type || "application/octet-stream", Accept: "application/json" };
  if (profileId) headers["X-Foulee-Profil"] = profileId;
  const response = await fetch(path, { method: "PUT", headers, body: blob });
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch (e) { /* réponse non JSON */ }
    if (response.status === 409 && data?.profil_requis) setTimeout(() => location.reload(), 30);
    throw new Error(data?.detail || `${response.status}`);
  }
  return response.json();
}
