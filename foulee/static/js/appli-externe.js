// L'application partenaire (Réglages → Application partenaire ; par défaut Club en ligne) : le site du club
// dans Foulée, dans un cadre, avec précédent, suivant, recharger et « ouvrir dans le navigateur ».
// Le nom du fichier évite « partner », que certains bloqueurs de pub arrêtent.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

function host(url) {
  try { return new URL(url).host; } catch (e) { return url; }
}

/** La page : barre d'outils et cadre, qui prend toute la hauteur restante de la fenêtre. */
export function renderPartnerPage(page, boot, { keep }) {
  const app = boot.partenaire || {};
  if (!app.actif) {
    page.innerHTML = `<header class="head"><div><h1>Application partenaire</h1></div></header>
      <p class="co-empty">Elle n'est pas activée : <a href="#/reglages?section=partenaire">Réglages → Application partenaire</a>.</p>`;
    return;
  }
  page.innerHTML = `
    <header class="head xa-head">
      <div><h1>${F.escape(app.nom)}</h1><div class="head-sub"><span>${F.escape(host(app.adresse))}</span></div></div>
      <div class="xa-bar" role="toolbar" aria-label="Navigation dans ${F.escape(app.nom)}">
        <button class="btn icon-btn" type="button" data-back title="Précédent" aria-label="Précédent">${icon("left")}</button>
        <button class="btn icon-btn" type="button" data-forward title="Suivant" aria-label="Suivant">${icon("right")}</button>
        <button class="btn icon-btn" type="button" data-reload title="Recharger (revient à la page de départ)" aria-label="Recharger">${icon("sync")}</button>
        <a class="btn" href="${F.escape(app.adresse)}" target="_blank" rel="noopener" title="Ouvrir dans le navigateur, si la connexion ne tient pas ici">${icon("external")}<span class="xa-label">Ouvrir dans le navigateur</span></a>
        <a class="btn btn-ghost icon-btn" href="#/reglages?section=partenaire" title="Régler l'application partenaire" aria-label="Réglages de l'application partenaire">${icon("settings")}</a>
      </div>
    </header>
    <div class="xa-frame"><iframe src="${F.escape(app.adresse)}" title="${F.escape(app.nom)}" referrerpolicy="strict-origin-when-cross-origin"
      allow="clipboard-read; clipboard-write; fullscreen"></iframe></div>`;
  const frame = page.querySelector("iframe");
  // Précédent et suivant : l'historique de la fenêtre comprend celui du cadre (le navigateur n'en laisse pas
  // lire davantage d'un autre site). Recharger repart de l'adresse réglée : la page courante d'un autre site
  // n'est pas lisible depuis Foulée.
  page.querySelector("[data-back]").addEventListener("click", () => history.back());
  page.querySelector("[data-forward]").addEventListener("click", () => history.forward());
  page.querySelector("[data-reload]").addEventListener("click", () => { frame.src = app.adresse; });
  const fit = () => {
    const top = frame.getBoundingClientRect().top + window.scrollY;
    frame.style.height = `${Math.max(420, window.innerHeight - top - 18)}px`;
  };
  fit();
  window.addEventListener("resize", fit);
  keep?.({ dispose: () => window.removeEventListener("resize", fit) });
}

/** Réglages → Application partenaire. */
export function partnerPanel(box, boot, { toast, onChange }) {
  const app = { ...(boot.partenaire || {}) };
  box.innerHTML = `
    <label class="check club-toggle"><input type="checkbox" data-on ${app.actif ? "checked" : ""}>
      <span><b>Afficher l'application dans la colonne de gauche</b><span class="hint">Elle s'ajoute sous « Nouvelle vue » et s'ouvre dans Foulée, avec précédent, suivant et recharger.</span></span></label>
    <div class="form-grid xa-form">
      <label class="field"><span>Nom dans le menu</span><input type="text" data-k="nom" maxlength="30" value="${F.escape(app.nom || "")}" placeholder="Club en ligne"></label>
      <label class="field xa-url"><span>Adresse</span><input type="text" inputmode="url" data-k="adresse" maxlength="500" value="${F.escape(app.adresse || "")}" placeholder="https://app.clubenligne.fr/"
        spellcheck="false" autocomplete="off"><span class="hint">Tu peux viser une page précise en ajoutant la fin de son adresse, par exemple <code>https://app.clubenligne.fr/entrainements</code> (copie-la depuis ton navigateur).</span></label>
    </div>
    <div class="inline-actions">
      <button class="btn btn-primary" type="button" data-save>${icon("check")}Enregistrer</button>
      <a class="btn" data-try href="${F.escape(app.adresse || "")}" target="_blank" rel="noopener">${icon("external")}Essayer l'adresse</a>
      <button class="btn btn-ghost" type="button" data-default>${icon("reset")}Remettre Club en ligne</button>
    </div>
    <p class="hint">Si la connexion au site ne tient pas dans Foulée (certains sites refusent d'être ouverts dans une autre application), le bouton « Ouvrir dans le navigateur » de la page l'ouvre à part.</p>`;
  const input = (k) => box.querySelector(`[data-k=${k}]`);
  const save = async (message) => {
    const body = { actif: box.querySelector("[data-on]").checked, nom: input("nom").value.trim(), adresse: input("adresse").value.trim() };
    try {
      const res = await api.put("/api/settings", { partenaire: body });
      const saved = res.reglages.partenaire;
      input("nom").value = saved?.nom || "";
      input("adresse").value = saved?.adresse || "";
      box.querySelector("[data-try]").href = saved?.adresse || "#";
      toast(message || "Application partenaire enregistrée.");
      await onChange?.();
    } catch (err) { toast(err.message, { error: true }); }
  };
  box.querySelector("[data-on]").addEventListener("change", (e) => save(e.target.checked
    ? `« ${input("nom").value.trim() || "Club en ligne"} » s'ajoute dans la colonne de gauche.` : "Application partenaire retirée du menu."));
  box.querySelector("[data-save]").addEventListener("click", () => save());
  box.querySelector("[data-default]").addEventListener("click", () => {
    input("nom").value = "Club en ligne";
    input("adresse").value = "https://app.clubenligne.fr/";
    save("Club en ligne remis par défaut.");
  });
  input("adresse").addEventListener("input", () => { box.querySelector("[data-try]").href = input("adresse").value.trim() || "#"; });
}
