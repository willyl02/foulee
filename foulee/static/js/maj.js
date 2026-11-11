// Mises à jour : l'alerte « Une nouvelle version est disponible ! » en haut à droite de l'interface,
// et l'installation (partagée avec Réglages → Installation → Mises à jour).
import * as api from "./api.js";
import { openDialog } from "./editor.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// L'interface redemande toutes les 30 minutes ; le serveur n'interroge GitHub que toutes les 3 heures
const ASK_EVERY = 30 * 60 * 1000;
const SETTINGS = "#/reglages?section=maj";

export const noAnswer = (mode) => (mode === "serveur"
  ? "Le service de mise à jour ne répond pas. Lance une fois la mise à jour en SSH (voir le README), puis réessaie."
  : "Pas de réponse : réessaie dans un instant.");

/** Attend un état de mise à jour postérieur à la demande (écrit par l'application ou par le service du serveur). */
export async function waitFor(since, finals, onProgress, timeoutMs) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    await sleep(1200);
    let res;
    try { res = await api.get("/api/maj", null, { fresh: true }); } catch (err) { continue; }
    const st = res.etat;
    if (!st || st.horodatage < since) continue;
    onProgress?.(st);
    if (finals.includes(st.statut)) return st;
  }
  return null;
}

/**
 * Lance l'installation, suit sa progression, puis recharge la page quand Foulée a redémarré.
 * Renvoie l'état d'erreur si elle échoue (rien sinon : la page se recharge).
 */
export async function installUpdate({ mode, boot, onProgress }) {
  const req = await api.post("/api/maj", { action: "installer" });
  const st = await waitFor(req.horodatage, ["termine", "erreur"], onProgress, 20 * 60 * 1000);
  if (!st || st.statut === "erreur") return st || { statut: "erreur", message: noAnswer(mode) };
  onProgress?.({
    statut: "termine",
    message: mode === "exe"
      ? "Foulée se ferme, s'installe et se relance tout seul : cette page se rechargera d'elle-même (une minute environ)."
      : st.message,
  });
  // Redémarrage : on recharge la page dès que Foulée répond de nouveau
  const end = Date.now() + 5 * 60 * 1000;
  while (Date.now() < end) {
    await sleep(2000);
    try {
      const fresh = await api.get("/api/bootstrap", null, { fresh: true });
      if (fresh.demarre_le !== boot.demarre_le) break;
    } catch (err) { /* redémarrage en cours */ }
  }
  setTimeout(() => location.reload(), 600);
  return null;
}

// ------------------------------------------------------------------ alerte
let alertBox = null;
let alertBoot = () => null;
let last = null;
let busy = false;

/** Démarre l'alerte : une première vérification, puis toutes les 30 minutes et au retour sur l'onglet. */
export function startUpdateAlert(box, getBoot) {
  alertBox = box;
  alertBoot = getBoot;
  refreshUpdateAlert();
  setInterval(refreshUpdateAlert, ASK_EVERY);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && last?.verifie_le && Date.now() / 1000 - last.verifie_le > 3 * 3600) refreshUpdateAlert();
  });
}

/** Redemande l'état (après une vérification ou un changement de canal dans les Réglages). */
export async function refreshUpdateAlert() {
  if (!alertBox) return;
  try {
    last = await api.get("/api/maj/alerte", null, { fresh: true });
  } catch (err) {
    return;  // serveur occupé ou hors ligne : l'alerte attendra la prochaine fois
  }
  paint();
}

function paint() {
  if (!alertBox) return;
  if (!last?.nouvelle) {
    alertBox.hidden = true;
    alertBox.innerHTML = "";
    return;
  }
  alertBox.hidden = false;
  alertBox.innerHTML = `<button class="update-pill" type="button" aria-haspopup="dialog"
      title="Foulée ${F.escape(last.version)}${last.beta ? " (bêta)" : ""} : voir les nouveautés et installer">
    <span class="update-dot" aria-hidden="true"></span>${icon("download")}<span>Une nouvelle version est disponible !</span></button>`;
  alertBox.querySelector("button").addEventListener("click", openUpdateDialog);
}

function openUpdateDialog() {
  const info = last;
  if (!info?.nouvelle) return;
  const boot = alertBoot() || {};
  const news = info.nouveautes || [];
  const date = info.publiee_le ? ` · publiée le ${F.escape(F.dateLong(info.publiee_le, { year: true, weekday: false }))}` : "";
  let action;
  if (info.peut_installer) {
    action = `<p class="hint">${info.mode === "exe"
      ? "Foulée se ferme une minute environ, s'installe et se relance tout seul."
      : "Le serveur s'installe puis redémarre, une minute environ."} Tes données, ta clé et tes vues sont conservées.</p>`;
  } else if (info.mode === "dev") {
    action = `<p class="hint">Cette copie de Foulée a été installée à la main : elle se met à jour avec <code>Mettre-a-jour-Foulee.cmd</code>.</p>`;
  } else {
    action = `<p class="hint">La mise à jour s'installe depuis le profil principal, dans les Réglages.</p>`;
  }
  const dialog = openDialog(`<div class="dlg dlg-maj" role="document">
    <div class="dlg-head">
      <h2>${icon("download")}Foulée ${F.escape(info.version)} est disponible${info.beta ? ` <span class="badge">bêta</span>` : ""}</h2>
      <p>Tu as la version ${F.escape(info.installee)}${date}.</p>
    </div>
    <div class="dlg-body">
      ${news.length ? `<p class="maj-lead">Au programme :</p><ul class="maj-news">${news.map((n) => `<li>${F.escape(n)}</li>`).join("")}</ul>` : ""}
      ${action}
      <p class="computed maj-progress" data-progress role="status" hidden></p>
    </div>
    <div class="dlg-foot">
      ${info.principal ? `<a class="btn btn-ghost" href="${SETTINGS}" data-settings>${icon("settings")}Voir dans les Réglages</a>` : ""}
      <button class="btn" type="button" data-later>${info.peut_installer ? "Plus tard" : "Fermer"}</button>
      ${info.peut_installer ? `<button class="btn btn-primary" type="button" data-install>${icon("download")}Installer maintenant</button>` : ""}
    </div></div>`);
  const progress = dialog.querySelector("[data-progress]");
  const install = dialog.querySelector("[data-install]");
  dialog.querySelector("[data-later]").addEventListener("click", () => { if (!busy) dialog.close(); });
  dialog.querySelector("[data-settings]")?.addEventListener("click", () => dialog.close());
  // Pendant l'installation, ni Échap ni un clic à côté ne ferment la fenêtre
  dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
  dialog.addEventListener("click", (event) => { if (busy && event.target === dialog) event.stopImmediatePropagation(); }, true);
  install?.addEventListener("click", async () => {
    busy = true;
    install.disabled = true;
    dialog.querySelectorAll("[data-later], [data-settings]").forEach((b) => b.setAttribute("aria-disabled", "true"));
    dialog.classList.add("busy");
    progress.hidden = false;
    progress.textContent = "Demande envoyée…";
    try {
      const failed = await installUpdate({
        mode: info.mode, boot, onProgress: (st) => { progress.textContent = st.message; },
      });
      if (failed) {
        busy = false;
        dialog.classList.remove("busy");
        progress.textContent = `✗ ${failed.message}`;
        install.disabled = false;
        install.lastChild.textContent = "Réessayer";
        dialog.querySelectorAll("[aria-disabled]").forEach((b) => b.removeAttribute("aria-disabled"));
      }
    } catch (err) {
      busy = false;
      dialog.classList.remove("busy");
      progress.textContent = `✗ ${err.message}`;
      install.disabled = false;
      dialog.querySelectorAll("[aria-disabled]").forEach((b) => b.removeAttribute("aria-disabled"));
    }
  });
}
