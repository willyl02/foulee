// Pastilles de connexion, en haut à droite des vues : une par source branchée sur le profil (Garmin,
// Withings, et les suivantes). Vert : la dernière synchro de la source a abouti. Rouge : elle n'a pas
// abouti, ou la clé (l'accès) manque ou est refusée. Gris : pas encore de synchro.
// Un clic ouvre le détail : message d'erreur, dernière synchro réussie, « Synchroniser », Réglages.
import * as F from "./format.js";
import { icon } from "./icons.js";

const WORD = { ok: "connexion OK", ko: "connexion en défaut", attente: "pas encore synchronisé" };

function summary(c, busy) {
  if (busy) return `${WORD[c.etat] || ""}, synchro en cours`;
  if (c.etat === "ko") return c.erreur ? `la dernière synchro n'a pas abouti (${F.relative(c.derniere)})` : c.texte.replace(/\.$/, "");
  if (c.etat === "ok" && c.derniere_reussie) return `connexion OK, dernière synchro ${F.relative(c.derniere_reussie)}`;
  return WORD[c.etat] || c.texte;
}

/** Les pastilles (rien si le profil n'a aucune source). */
export function connPills(list = [], busy = false) {
  return list.map((c) => {
    const text = `${c.nom} : ${summary(c, busy)}`;
    return `<span class="conn-item">
        <button type="button" class="conn-pill is-${F.escape(c.etat)}${busy ? " is-busy" : ""}" data-conn="${F.escape(c.cle)}"
          aria-expanded="false" aria-label="${F.escape(text)}" title="${F.escape(text)}"><i class="conn-dot" aria-hidden="true"></i><span class="conn-name">${F.escape(c.nom)}</span></button>
        <div class="conn-pop" role="dialog" aria-label="${F.escape(c.nom)}" hidden></div>
      </span>`;
  }).join("");
}

function detail(c, { busy, demo, local }) {
  const lines = [];
  if (busy) lines.push(`<p class="conn-busy">${icon("sync")}Synchro en cours…</p>`);
  if (c.etat === "ko" || demo) lines.push(`<p>${F.escape(c.texte)}</p>`);
  if (c.erreur) lines.push(`<p class="conn-err">${F.escape(c.erreur)}<small>${F.escape(F.relative(c.derniere))}</small></p>`);
  if (c.depuis) lines.push(`<p class="conn-note">Depuis le ${F.escape(F.dateTime(c.depuis))}.</p>`);
  if (!demo && c.etat !== "attente" && !(c.bloque && !c.derniere_reussie)) {
    lines.push(`<p class="conn-note">${c.derniere_reussie ? `Dernière synchro réussie : ${F.escape(F.relative(c.derniere_reussie))}.` : "Aucune synchro réussie pour l'instant."}</p>`);
  }
  if (c.alertes) lines.push(`<p class="conn-note">${c.alertes} alerte${c.alertes > 1 ? "s" : ""} dans le journal de la dernière synchro (le reste est à jour).</p>`);
  const actions = [];
  // Le calendrier se relit seul (« Actualiser ») ; les autres pastilles lancent toute la synchro
  const own = c.cle === "calendrier";
  if (!demo && !c.bloque) actions.push(`<button class="btn" type="button" data-conn-sync="${own ? F.escape(c.cle) : ""}"${busy ? " disabled" : ""}>${icon("sync")}${c.etat === "ko" ? "Réessayer" : own ? "Actualiser" : "Synchroniser"}</button>`);
  if (!demo && c.reglages && (local || c.cle !== "garmin")) {
    actions.push(`<a class="btn btn-ghost" href="#/reglages?section=${F.escape(c.reglages)}">${icon("settings")}Réglages ${F.escape(c.nom)}</a>`);
  }
  return `<div class="conn-pop-head"><i class="conn-dot is-${F.escape(c.etat)}" aria-hidden="true"></i><b>${F.escape(c.nom)}</b><span>${F.escape(WORD[c.etat] || "")}</span></div>
    ${lines.join("")}${actions.length ? `<div class="conn-actions">${actions.join("")}</div>` : ""}`;
}

/**
 * Branche les pastilles de « root » : ouvrir / fermer le détail, synchroniser.
 * getState() → { list, busy, demo, local } au moment du clic (les temps relatifs restent justes).
 */
export function wireConn(root, getState, { onSync }) {
  const box = root.querySelector(".conn");
  if (!box) return null;
  const closeAll = (except) => box.querySelectorAll(".conn-item").forEach((item) => {
    if (item === except) return;
    item.querySelector(".conn-pop").hidden = true;
    item.querySelector(".conn-pill").setAttribute("aria-expanded", "false");
  });
  box.addEventListener("click", (e) => {
    const pill = e.target.closest(".conn-pill");
    if (pill) {
      const item = pill.closest(".conn-item");
      const pop = item.querySelector(".conn-pop");
      closeAll(item);
      if (!pop.hidden) { pop.hidden = true; pill.setAttribute("aria-expanded", "false"); return; }
      const st = getState();
      const c = st.list.find((x) => x.cle === pill.dataset.conn);
      if (!c) return;
      pop.innerHTML = detail(c, st);
      pop.hidden = false;
      pill.setAttribute("aria-expanded", "true");
      return;
    }
    const sync = e.target.closest("[data-conn-sync]");
    if (sync) { closeAll(); onSync(sync.dataset.connSync ? [sync.dataset.connSync] : null); return; }
    if (e.target.closest(".conn-pop a")) closeAll();
  });
  box.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const open = box.querySelector(".conn-pill[aria-expanded='true']");
    if (open) { e.stopPropagation(); closeAll(); open.focus(); }
  });
  const outside = (e) => { if (!box.contains(e.target)) closeAll(); };
  document.addEventListener("click", outside);
  return { dispose: () => document.removeEventListener("click", outside) };
}
