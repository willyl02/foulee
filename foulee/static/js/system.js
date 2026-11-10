// Réglages de l'installation : clé Garmin, dossier des données, Claude Desktop, application,
// réseau local, mises à jour. Chaque rubrique a ses propres boutons (rien à « enregistrer »).
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const CLAUDE_DOWNLOAD = "https://claude.ai/download";
const GITHUB_TOKEN_PAGE = "https://github.com/settings/personal-access-tokens/new";

const link = (href, text) => `<a href="${F.escape(href)}" target="_blank" rel="noopener">${text}${icon("external")}</a>`;
const fail = (text) => `<p class="computed warn">${icon("warning")}<span>${F.escape(text)}</span></p>`;

function contentText(content) {
  if (!content) return "aucune donnée pour l'instant";
  if (content.illisible) return "base illisible";
  const span = content.debut ? `, du ${F.dateLong(content.debut, { year: true, weekday: false })} au ${F.dateLong(content.fin, { year: true, weekday: false })}` : "";
  return `${F.int(content.seances)} séances, ${F.int(content.valeurs)} valeurs quotidiennes${span}`;
}

// ================================================================ sections
export function systemSections(boot) {
  const local = boot.acces === "local";
  const parts = [];
  if (local && !boot.demo) {
    parts.push(section("cle", "Clé API Garmin", `Foulée s'en sert pour récupérer tes données chez Garmin. Elle est rangée ${boot.machine === "pc" ? "dans le Gestionnaire d'identification de Windows" : "sur le serveur, dans un fichier que seul Foulée peut lire"} : ni l'interface ni Claude ne la voient.`));
  }
  if (local) {
    parts.push(section("dossier", "Dossier des données", "Ta base (séances, mesures, réglages, vues) et tes fichiers FIT. Tu peux la ranger ailleurs, sur un autre disque par exemple. L'ancien dossier n'est jamais effacé : tu le supprimes toi-même une fois rassuré."));
  }
  if (local && boot.machine === "pc") {
    parts.push(section("claude", "Claude Desktop", "Relie Foulée à Claude Desktop pour lui demander d'analyser tes séances, ta forme ou tes allures. Claude lit ta base ici même, sur ce PC."));
  }
  if (boot.application) {
    parts.push(section("app", "Application", "Foulée tourne en arrière-plan, avec son icône près de l'horloge : clic pour ouvrir l'interface, clic droit pour synchroniser ou quitter."));
  }
  if (boot.machine === "serveur" && !boot.demo) {
    parts.push(section("lan", "Accès depuis le réseau local", "Ouvre Foulée depuis n'importe quel appareil de la maison, sans Tailscale, avec l'adresse du serveur. Un mot de passe le protège ; par Tailscale, il n'est jamais demandé."));
  }
  if (!local) {
    parts.push(`<section data-section="distant"><h2>Installation</h2><p class="intro">La clé Garmin et le dossier des données se règlent par Tailscale ou sur le serveur lui-même.</p></section>`);
  }
  parts.push(section("maj", "Mises à jour", ""));
  return parts.join("");
}

function section(name, title, intro) {
  return `<section data-section="${name}">
      <h2>${F.escape(title)}</h2>${intro ? `<p class="intro">${intro}</p>` : ""}
      <div data-body><p class="computed">Chargement…</p></div>
    </section>`;
}

export function wireSystem(root, boot, ctx) {
  const find = (name) => root.querySelector(`[data-section="${name}"] [data-body]`);
  if (find("cle")) keyPanel(find("cle"), boot, ctx);
  if (find("dossier")) folderPanel(find("dossier"), boot, ctx);
  if (find("claude")) claudePanel(find("claude"), ctx);
  if (find("app")) appPanel(find("app"), ctx);
  if (find("lan")) lanPanel(find("lan"), ctx);
  if (find("maj")) updatesPanel(find("maj"), boot, ctx);
}

// ============================================================ clé Garmin
export async function keyPanel(box, boot, { toast, onSaved, compact = false }) {
  let info;
  try {
    info = await api.get("/api/cle", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(`État de la clé indisponible : ${err.message}`);
    return;
  }
  const where = boot.machine === "pc" ? "sur ce PC" : "sur le serveur";

  const form = () => `
    <ol class="steps">
      <li>Ouvre ${link(info.page_garmin, "la page « API personnelle » de Garmin Connect")}, connecte-toi et crée une clé. Perdue ? Régénère-la : l'ancienne cesse alors de fonctionner.</li>
      <li>Copie la clé (elle commence par <code>GCDC_</code>), colle-la ci-dessous et valide : Foulée la teste auprès de Garmin avant de l'enregistrer.</li>
    </ol>
    <div class="key-row">
      <input type="password" data-key-input autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="GCDC_…" aria-label="Clé API Garmin">
      <button class="btn btn-ghost icon-btn" type="button" data-key-show title="Afficher la clé" aria-label="Afficher la clé" aria-pressed="false">${icon("eye")}</button>
      <button class="btn btn-primary" type="button" data-key-save>${icon("check")}Tester et enregistrer</button>
      ${info.enregistree ? `<button class="btn btn-ghost" type="button" data-key-cancel>Annuler</button>` : ""}
    </div>
    <p class="hint" data-key-status aria-live="polite"></p>`;

  const render = (editing) => {
    const refused = info.refus;
    let status;
    if (refused) {
      const gone = [404, 410].includes(Number(refused.statut));
      status = `<p class="computed warn">${icon("warning")}<span><b>${gone ? "Garmin ne connaît plus ta clé" : "Garmin refuse ta clé"}</b> depuis le ${F.escape(F.dateTime(refused.depuis))}${refused.statut ? ` (HTTP ${F.escape(refused.statut)})` : ""} : la synchro est en pause. ${gone ? "Elle a été supprimée ou régénérée dans Garmin Connect" : "Elle a peut-être été révoquée ou régénérée"} : remplace-la par ta clé actuelle.</span></p>`;
    } else if (info.enregistree) {
      status = `<p class="computed ok">${icon("check")}<span>Clé enregistrée ${where}${info.enregistree_le ? ` le ${F.escape(F.dateTime(info.enregistree_le))}` : ""}.</span></p>`;
    } else {
      status = `<p class="computed">Aucune clé ${where} pour l'instant.</p>`;
    }
    const open = editing || refused || !info.enregistree;
    box.innerHTML = `${status}${open ? form() : `
      <div class="inline-actions">
        <button class="btn" type="button" data-key-edit>${icon("key")}Remplacer la clé</button>
        ${compact ? "" : `<button class="btn btn-ghost btn-danger" type="button" data-key-forget>${icon("trash")}Supprimer la clé ${where}</button>`}
      </div>`}`;
    wire();
  };

  const wire = () => {
    box.querySelector("[data-key-edit]")?.addEventListener("click", () => { render(true); box.querySelector("[data-key-input]")?.focus(); });
    box.querySelector("[data-key-cancel]")?.addEventListener("click", () => render(false));
    box.querySelector("[data-key-forget]")?.addEventListener("click", async () => {
      if (!window.confirm(`Supprimer la clé ${where} ? La synchro s'arrêtera jusqu'à ce que tu en enregistres une autre.`)) return;
      try {
        info = await api.del("/api/cle");
        toast("Clé supprimée.");
        render(false);
        onSaved?.(info);
      } catch (err) {
        toast(`Suppression impossible : ${err.message}`, { error: true });
      }
    });
    const input = box.querySelector("[data-key-input]");
    if (!input) return;
    const status = box.querySelector("[data-key-status]");
    const show = box.querySelector("[data-key-show]");
    show.addEventListener("click", () => {
      const visible = input.type === "password";
      input.type = visible ? "text" : "password";
      show.setAttribute("aria-pressed", String(visible));
    });
    const save = async () => {
      const value = input.value;
      if (!value.trim()) { status.textContent = "Colle d'abord ta clé dans le champ."; input.focus(); return; }
      const button = box.querySelector("[data-key-save]");
      button.disabled = true;
      status.classList.remove("error");
      status.textContent = "Test auprès de Garmin…";
      try {
        const res = await api.put("/api/cle", { cle: value });
        input.value = "";  // vidé tout de suite : rien ne reste dans la page
        info = res;
        toast("Clé acceptée par Garmin et enregistrée.");
        render(false);
        if (res.corrections?.length) {
          box.insertAdjacentHTML("beforeend", `<p class="hint">Copie nettoyée : ${F.escape(res.corrections.join(", "))}.</p>`);
        }
        onSaved?.(res);
      } catch (err) {
        status.classList.add("error");
        status.textContent = err.message;
        button.disabled = false;
      }
    };
    box.querySelector("[data-key-save]").addEventListener("click", save);
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); save(); } });
  };
  render(false);
  return info;
}

// ================================================== dossier des données
export async function folderPanel(box, boot, { toast }) {
  let info;
  try {
    info = await api.get("/api/dossier", { anciennes: 1 }, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(`Dossier indisponible : ${err.message}`);
    return;
  }
  const badge = info.source === "env" ? "fixé par le serveur" : info.est_defaut ? "par défaut" : "choisi par toi";
  const empty = !info.contenu;
  const previous = empty ? (info.anciennes || []) : [];
  box.innerHTML = `
    <dl class="about">
      <dt>Emplacement</dt><dd><code>${F.escape(info.chemin)}</code> <span class="badge">${badge}</span></dd>
      <dt>Contenu</dt><dd>${F.escape(contentText(info.contenu))} · ${F.size(info.taille)}</dd>
    </dl>
    ${info.onedrive ? `<p class="computed warn">${icon("warning")}<span>Ce dossier est synchronisé par OneDrive : tes données de santé partent dans le cloud de Microsoft. Mieux vaut un dossier hors OneDrive.</span></p>` : ""}
    ${previous.map((old) => `
      <div class="callout" data-previous="${F.escape(old.chemin)}">
        <b>Données d'une autre installation de Foulée</b>
        <p><code>${F.escape(old.chemin)}</code> : ${F.escape(contentText(old.contenu))} (${F.size(old.taille)}).</p>
        <div class="inline-actions"><button class="btn btn-primary" type="button" data-import>${icon("download")}Copier ces données ici</button>
          <span class="hint">L'ancien dossier n'est pas modifié.</span></div>
      </div>`).join("")}
    ${info.modifiable ? `
      <div class="inline-actions">
        <button class="btn" type="button" data-change>${icon("folder")}Changer de dossier…</button>
        ${info.est_defaut ? "" : `<button class="btn btn-ghost" type="button" data-default>Revenir au dossier par défaut</button>`}
      </div>
      <div class="change-panel" data-panel hidden>
        <label class="field"><span>Nouveau dossier</span>
          <span class="path-row"><input type="text" data-path spellcheck="false" placeholder="${boot.machine === "pc" ? "D:\\Sport\\Foulee" : "/chemin/vers/le/dossier"}">
          ${info.choix_fenetre ? `<button class="btn" type="button" data-browse>${icon("folder")}Parcourir…</button>` : ""}</span></label>
        <div data-verdict aria-live="polite"></div>
      </div>` : `<p class="computed">Ce dossier est imposé par la configuration du serveur (variable FOULEE_DATA).</p>`}`;

  const panel = box.querySelector("[data-panel]");
  const input = box.querySelector("[data-path]");
  const verdict = box.querySelector("[data-verdict]");

  const run = async (path, mode, button) => {
    const labels = { deplacer: "Copie de tes données…", utiliser: "Vérification de la base…", importer: "Copie des données…" };
    if (button) button.disabled = true;
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = labels[mode];
    (verdict || box).appendChild(note);
    try {
      const res = await api.put("/api/dossier", { chemin: path, mode });
      const base = res.rapport.base || {};
      toast(mode === "importer"
        ? `Données importées : ${F.int(base.seances)} séances, ${F.int(base.valeurs)} valeurs.`
        : `Foulée utilise maintenant ${res.rapport.nouveau}.`);
      setTimeout(() => location.reload(), 900);  // tout vient d'une autre base : on repart de zéro
    } catch (err) {
      note.textContent = err.message;
      note.classList.add("error");
      if (button) button.disabled = false;
    }
  };

  box.querySelectorAll("[data-import]").forEach((button) => button.addEventListener("click", () => {
    run(button.closest("[data-previous]").dataset.previous, "importer", button);
  }));
  if (!panel) return info;

  let timer = null;
  let asked = 0;
  const examine = async () => {
    const path = input.value.trim();
    if (!path) { verdict.innerHTML = ""; return; }
    const ticket = ++asked;
    let res;
    try {
      res = await api.post("/api/dossier/examiner", { chemin: path });
    } catch (err) {
      verdict.innerHTML = fail(err.message);
      return;
    }
    if (ticket !== asked) return;  // une saisie plus récente a pris le relais
    if (res.probleme) { verdict.innerHTML = fail(res.probleme); return; }
    const actions = [];
    if (res.modes.includes("deplacer")) {
      actions.push(`<p class="computed">${res.existe ? (res.vide ? "Dossier vide." : "Dossier sans données Foulée.") : "Ce dossier sera créé."} Foulée y copiera tes données (${F.size(info.taille)}) puis s'en servira.</p>
        <div class="inline-actions"><button class="btn btn-primary" type="button" data-mode="deplacer">${icon("folder")}Déplacer mes données ici</button></div>`);
    }
    if (res.contenu && !res.contenu.illisible) {
      actions.push(`<p class="computed">Ce dossier contient déjà des données Foulée : ${F.escape(contentText(res.contenu))}.</p>
        <div class="inline-actions">
          ${res.modes.includes("utiliser") ? `<button class="btn btn-primary" type="button" data-mode="utiliser">Utiliser ce dossier</button>` : ""}
          ${res.modes.includes("importer") ? `<button class="btn" type="button" data-mode="importer">${icon("download")}Copier ces données ici</button>` : ""}
        </div>
        <p class="hint">« Utiliser » : Foulée travaille désormais dans ce dossier ; tes données actuelles restent dans l'ancien.${res.modes.includes("importer") ? " « Copier » : ces données remplacent ta base actuelle, encore vide." : ""}</p>`);
    }
    if (!actions.length) {
      const reasons = Object.values(res.refus || {});
      actions.push(fail(reasons[0] || "Ce dossier ne convient pas."));
    }
    if (res.onedrive) actions.push(`<p class="computed warn">${icon("warning")}<span>Ce dossier est synchronisé par OneDrive : tes données de santé partiraient dans le cloud.</span></p>`);
    verdict.innerHTML = actions.join("");
    verdict.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => run(res.chemin, button.dataset.mode, button)));
  };
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(examine, 450); });
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); clearTimeout(timer); examine(); } });

  box.querySelector("[data-change]").addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) input.focus();
  });
  box.querySelector("[data-default]")?.addEventListener("click", () => {
    panel.hidden = false;
    input.value = info.defaut;
    examine();
  });
  box.querySelector("[data-browse]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const res = await api.post("/api/dossier/parcourir", { depart: input.value.trim() || info.chemin });
      if (res.chemin) { input.value = res.chemin; examine(); }
    } catch (err) {
      verdict.innerHTML = fail(err.message);
    }
    button.disabled = false;
  });
  return info;
}

// ========================================================= Claude Desktop
export async function claudePanel(box, { toast, compact = false, onChange = null }) {
  let info;
  try {
    info = await api.get("/api/claude", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(`État de Claude Desktop indisponible : ${err.message}`);
    return;
  }
  if (!info.possible) {
    box.innerHTML = `<p class="computed">Claude Desktop se relie depuis le PC où il est installé.</p>`;
    return;
  }
  const tutorial = (open) => `
    <details class="howto" ${open ? "open" : ""}>
      <summary>Comment ça marche ?</summary>
      <ol class="steps">
        <li>Clique sur « Relier ». Foulée s'ajoute à la configuration de Claude Desktop (une copie de sauvegarde est faite à côté).</li>
        <li>Ouvre Claude Desktop. La toute première fois, Foulée met une vingtaine de secondes à apparaître.</li>
        <li>Dans une conversation, clique sur <b>+</b> puis <b>Connecteurs</b> : « foulee » y figure, activé.</li>
        <li>Demande par exemple : « Résume ma semaine d'entraînement », « Compare mon sommeil d'un poste à l'autre » ou « Quelles allures pour 6 × 800 m à 100 % de VMA ? ».</li>
      </ol>
      <p class="hint">Foulée n'apparaît pas ? Dans Claude Desktop, Paramètres → Développeur : l'entrée « foulee » indique ce qui ne va pas.</p>
    </details>`;
  if (!info.installe) {
    box.innerHTML = `<p class="computed">Claude Desktop ne semble pas installé sur ce PC. ${link(CLAUDE_DOWNLOAD, "Télécharge-le")}, ouvre-le une première fois, puis reviens ici.</p>
      <div class="inline-actions"><button class="btn" type="button" data-again>${icon("reset")}Vérifier à nouveau</button></div>${compact ? "" : tutorial(false)}`;
    box.querySelector("[data-again]").addEventListener("click", () => claudePanel(box, { toast, compact, onChange }));
    onChange?.(info);
    return info;
  }
  const other = info.fichiers.find((f) => f.foulee && !f.a_jour);
  const broken = info.fichiers.find((f) => !f.valide);
  let status;
  if (info.connecte) status = `<p class="computed ok">${icon("check")}<span>Foulée est relié à Claude Desktop.</span></p>`;
  else if (other) status = `<p class="computed">Claude Desktop est relié à une autre installation de Foulée (<code>${F.escape(other.commande || "?")}</code>) : relie-le à celle-ci.</p>`;
  else status = `<p class="computed">Foulée n'est pas encore relié à Claude Desktop.</p>`;
  const verb = info.connecte ? "Relier à nouveau" : "Relier Foulée à Claude Desktop";
  box.innerHTML = `${status}
    ${broken ? fail(`Le fichier ${broken.chemin} n'est pas un JSON valide : Foulée n'y touche pas. Corrige-le ou supprime-le, puis réessaie.`) : ""}
    ${info.ouvert ? `<p class="computed warn">${icon("info")}<span>Claude Desktop est ouvert. Il doit être fermé le temps de la modification : Foulée peut le fermer pour toi (pense à envoyer le message en cours).</span></p>` : ""}
    <div class="inline-actions">
      ${!info.connecte || !compact ? `<button class="btn ${info.connecte ? "" : "btn-primary"}" type="button" data-claude="relier">${icon("chat")}${info.ouvert ? "Fermer Claude et relier" : verb}</button>` : ""}
      ${info.connecte && !compact ? `<button class="btn btn-ghost btn-danger" type="button" data-claude="retirer">Retirer Foulée de Claude</button>` : ""}
      <span class="hint" data-claude-status aria-live="polite"></span>
    </div>
    ${tutorial(!info.connecte && !compact)}`;
  const status2 = box.querySelector("[data-claude-status]");
  box.querySelectorAll("[data-claude]").forEach((button) => button.addEventListener("click", async () => {
    const action = button.dataset.claude;
    button.disabled = true;
    status2.textContent = info.ouvert ? "Fermeture de Claude…" : "Modification…";
    try {
      const res = await api.post("/api/claude", { action, fermer: info.ouvert });
      if (res.rapport.erreurs.length) throw new Error(res.rapport.erreurs.join(" "));
      toast(action === "retirer" ? "Foulée est retiré de Claude Desktop." : "C'est fait : ouvre Claude Desktop, Foulée apparaît dans ses connecteurs.");
      claudePanel(box, { toast, compact, onChange });
    } catch (err) {
      if (/ouvert/i.test(err.message)) { claudePanel(box, { toast, compact, onChange }); return; }
      status2.textContent = err.message;
      button.disabled = false;
    }
  }));
  onChange?.(info);
  return info;
}

// ============================================================ application
async function appPanel(box, { toast }) {
  let info;
  try {
    info = await api.get("/api/app", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(err.message);
    return;
  }
  box.innerHTML = `
    ${info.demarrage_windows === null ? "" : `<label class="check"><input type="checkbox" data-startup ${info.demarrage_windows ? "checked" : ""}>Lancer Foulée à l'ouverture de session Windows</label>`}
    <p class="computed">Tant que Foulée tourne, la synchro se fait toute seule toutes les ${info.synchro_auto_heures} heures. Pour l'arrêter : clic droit sur son icône près de l'horloge, puis « Quitter Foulée ».</p>`;
  box.querySelector("[data-startup]")?.addEventListener("change", async (event) => {
    const wanted = event.target.checked;
    try {
      const res = await api.put("/api/app", { demarrage_windows: wanted });
      event.target.checked = res.demarrage_windows;
      toast(res.demarrage_windows ? "Foulée se lancera à l'ouverture de session." : "Foulée ne se lancera plus tout seul.");
    } catch (err) {
      event.target.checked = !wanted;
      toast(err.message, { error: true });
    }
  });
}

// ===================================================== réseau local (serveur)
async function lanPanel(body, { toast }) {
  let info;
  try {
    info = await api.get("/api/acces-reseau", null, { fresh: true });
  } catch (err) {
    body.innerHTML = fail(`État indisponible : ${err.message}`);
    return;
  }
  const links = info.adresses.map((a) => `<a href="${F.escape(a)}/" target="_blank" rel="noopener">${F.escape(a)}</a>`).join(", ");
  if (!info.ecoute) {
    body.innerHTML = `<p class="computed">Le serveur n'écoute pas encore le réseau local : installe la dernière mise à jour, puis reviens ici.</p>`;
    return;
  }
  if (info.depuis === "reseau") {
    body.innerHTML = `<p class="computed">Tu es connecté par le réseau local${links ? ` (${links})` : ""}. Pour changer le mot de passe ou couper cet accès, passe par Tailscale.</p>
      <button class="btn" type="button" data-lan-logout>${icon("close")}Se déconnecter</button>`;
    body.querySelector("[data-lan-logout]").addEventListener("click", async () => {
      try { await api.post("/api/deconnexion"); } finally { location.replace("/connexion"); }
    });
    return;
  }
  const state = info.actif
    ? `<b>Activé</b>${links ? ` : ${links}` : ""}${info.modifie_le ? `, mot de passe choisi le ${F.escape(info.modifie_le)}` : ""}.`
    : `<b>Désactivé.</b> Les autres appareils de la maison voient une page qui les renvoie vers Tailscale${links ? ` (adresse : ${F.escape(info.adresses[0])})` : ""}.`;
  body.innerHTML = `
    <p class="computed">${state}</p>
    <div class="form-grid">
      <label class="field"><span>${info.actif ? "Nouveau mot de passe" : "Mot de passe"}</span><input type="password" name="lan_pw1" autocomplete="new-password"></label>
      <label class="field"><span>Encore une fois</span><input type="password" name="lan_pw2" autocomplete="new-password"></label>
    </div>
    <div class="inline-actions">
      <button class="btn btn-primary" type="button" data-lan-save>${icon("check")}${info.actif ? "Changer le mot de passe" : "Activer l'accès"}</button>
      ${info.actif ? `<button class="btn" type="button" data-lan-off>Couper l'accès</button>` : ""}
      <span class="hint" data-lan-status></span>
    </div>
    <p class="hint">${info.longueur_min} caractères au moins. Réservé à ta maison : cette adresse n'est pas chiffrée, n'ouvre jamais ce port sur ta box Internet.</p>`;
  const status = body.querySelector("[data-lan-status]");
  const save = async () => {
    const first = body.querySelector("[name=lan_pw1]").value;
    const second = body.querySelector("[name=lan_pw2]").value;
    if (first.length < info.longueur_min) { status.textContent = `${info.longueur_min} caractères au moins.`; return; }
    if (first !== second) { status.textContent = "Les deux saisies diffèrent."; return; }
    status.textContent = "Enregistrement…";
    try {
      await api.put("/api/acces-reseau", { mot_de_passe: first });
      toast(info.actif ? "Mot de passe changé : les appareils connectés devront le saisir à nouveau." : "Accès par le réseau local activé.");
      lanPanel(body, { toast });
    } catch (err) {
      status.textContent = err.message;
    }
  };
  body.querySelector("[data-lan-save]").addEventListener("click", save);
  body.querySelectorAll("input[type=password]").forEach((input) => input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); save(); }
  }));
  body.querySelector("[data-lan-off]")?.addEventListener("click", async () => {
    try {
      await api.del("/api/acces-reseau");
      toast("Accès par le réseau local coupé.");
      lanPanel(body, { toast });
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

// ============================================================ mises à jour
async function updatesPanel(box, boot, { toast }) {
  let info;
  try {
    info = await api.get("/api/maj", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(err.message);
    return;
  }
  const isBeta = /(a|b|rc)\d*$/i.test(info.version);
  if (info.mode === "dev") {
    box.innerHTML = `<p class="computed">Version installée : <b>${F.escape(info.version)}</b>. Cette copie de Foulée a été installée à la main (dossier décompressé) : elle se met à jour avec <code>Mettre-a-jour-Foulee.cmd</code>, ou passe à l'installateur ${link(`https://github.com/${info.depot}/releases`, "Foulee-Setup.exe")}.</p>`;
    return;
  }
  const lead = info.mode === "exe"
    ? "Foulée cherche sur GitHub une version plus récente, la télécharge, vérifie son empreinte puis l'installe. Tes données, ta clé et tes vues sont conservées."
    : "Foulée regarde sur GitHub s'il existe une version plus récente et l'installe, sans commande à taper. Tes données, ta clé et tes vues sont conservées.";
  box.innerHTML = `
    <p class="intro">${lead}</p>
    <div class="inline-actions"><span>Version installée : <b>${F.escape(info.version)}</b>${isBeta ? ` <span class="badge">bêta</span>` : ""}</span>
      <button class="btn" type="button" data-maj-check>${icon("sync")}Vérifier les mises à jour</button></div>
    <label class="check"><input type="checkbox" data-beta ${info.canal === "beta" ? "checked" : ""}>Recevoir les versions bêta (avant-premières)</label>
    <p class="hint beta-hint">Les bêtas apportent les nouveautés avant tout le monde, avec parfois quelques défauts : idéal pour tester. Décoche pour revenir aux versions stables (tu y repasses à la prochaine version stable).</p>
    ${info.mode === "exe" ? tokenBlock(info) : ""}
    <div data-maj-body aria-live="polite"></div>`;
  const body = box.querySelector("[data-maj-body]");
  const button = box.querySelector("[data-maj-check]");

  box.querySelector("[data-beta]").addEventListener("change", async (event) => {
    const canal = event.target.checked ? "beta" : "stable";
    try {
      await api.put("/api/settings", { canal_maj: canal });
      info.canal = canal;
      body.innerHTML = "";
      toast(canal === "beta" ? "Canal bêta activé : vérifie les mises à jour pour installer la dernière bêta." : "Retour au canal stable.");
    } catch (err) {
      event.target.checked = !event.target.checked;
      toast(err.message, { error: true });
    }
  });
  if (info.mode === "exe") wireToken(box, info, { toast, refresh: () => updatesPanel(box, boot, { toast }) });

  // Attend un état postérieur à la demande (écrit par le service du serveur, ou par l'application)
  async function waitFor(since, finals, onProgress, timeoutMs) {
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
  const noAnswer = info.mode === "serveur"
    ? "Le service de mise à jour ne répond pas. Lance une fois la mise à jour en SSH (voir le README), puis réessaie."
    : "Pas de réponse : réessaie dans un instant.";

  async function install() {
    button.disabled = true;
    body.innerHTML = `<p class="computed" data-maj-progress>Demande envoyée…</p>`;
    const progress = body.querySelector("[data-maj-progress]");
    try {
      const req = await api.post("/api/maj", { action: "installer" });
      const st = await waitFor(req.horodatage, ["termine", "erreur"], (s) => { progress.textContent = s.message; }, 20 * 60 * 1000);
      if (!st || st.statut === "erreur") {
        progress.textContent = st ? `✗ ${st.message}` : noAnswer;
        button.disabled = false;
        return;
      }
      progress.textContent = info.mode === "exe"
        ? "Foulée se ferme, s'installe et se relance tout seul : cette page se rechargera d'elle-même (une minute environ)."
        : st.message;
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
    } catch (err) {
      progress.textContent = `✗ ${err.message}`;
      button.disabled = false;
    }
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    body.innerHTML = `<p class="computed">Recherche sur GitHub…</p>`;
    try {
      const req = await api.post("/api/maj", { action: "verifier" });
      const st = await waitFor(req.horodatage, ["verifie", "erreur"], null, 90 * 1000);
      if (!st) {
        body.innerHTML = `<p class="computed">${F.escape(noAnswer)}</p>`;
      } else if (st.statut === "erreur") {
        body.innerHTML = fail(st.message);
        if (/jeton/i.test(st.message)) box.querySelector("details.token")?.setAttribute("open", "");
      } else if (!st.retard) {
        body.innerHTML = `<p class="computed">${F.escape(st.message)}</p>`;
      } else {
        const news = st.nouveautes || [];
        body.innerHTML = `<p class="computed"><b>${F.escape(st.message)}</b>${news.length ? " Au programme :" : ""}</p>
          ${news.length ? `<ul class="maj-news">${news.map((n) => `<li>${F.escape(n)}</li>`).join("")}</ul>` : ""}
          <div class="inline-actions"><button class="btn btn-primary" type="button" data-maj-install>${icon("download")}Mettre à jour maintenant</button>
            <span class="hint">${info.mode === "exe" ? "Foulée se ferme une minute environ, puis se relance tout seul." : "L'interface redémarre ensuite, une minute environ."}</span></div>`;
        body.querySelector("[data-maj-install]").addEventListener("click", install);
      }
    } catch (err) {
      body.innerHTML = fail(err.message);
    }
    button.disabled = false;
  });
}

function tokenBlock(info) {
  return `<details class="token">
      <summary>Jeton GitHub ${info.jeton_github ? "(enregistré)" : "(dépôt privé)"}</summary>
      <p class="hint">Tant que le dépôt de Foulée est privé, GitHub demande un jeton pour montrer ses versions. Crée-le sur ${link(GITHUB_TOKEN_PAGE, "github.com")} : type « fine-grained », accès au seul dépôt <code>${F.escape(info.depot)}</code>, permission « Contents » en lecture seule. Il est rangé dans le coffre de Windows, comme ta clé Garmin.</p>
      ${info.jeton_github
        ? `<div class="inline-actions"><span class="ok">${icon("check")}Jeton enregistré.</span><button class="btn btn-ghost btn-danger" type="button" data-token-forget>Supprimer le jeton</button></div>`
        : `<div class="key-row"><input type="password" data-token autocomplete="off" spellcheck="false" placeholder="github_pat_…" aria-label="Jeton GitHub">
            <button class="btn" type="button" data-token-save>${icon("check")}Vérifier et enregistrer</button></div>
          <p class="hint" data-token-status aria-live="polite"></p>`}
    </details>`;
}

function wireToken(box, info, { toast, refresh }) {
  box.querySelector("[data-token-forget]")?.addEventListener("click", async () => {
    try { await api.del("/api/github-jeton"); toast("Jeton GitHub supprimé."); refresh(); } catch (err) { toast(err.message, { error: true }); }
  });
  const input = box.querySelector("[data-token]");
  if (!input) return;
  const status = box.querySelector("[data-token-status]");
  const save = async () => {
    if (!input.value.trim()) { status.textContent = "Colle d'abord le jeton."; return; }
    status.textContent = "Vérification auprès de GitHub…";
    try {
      await api.put("/api/github-jeton", { jeton: input.value });
      input.value = "";
      toast("Jeton GitHub enregistré.");
      refresh();
    } catch (err) {
      status.textContent = err.message;
    }
  };
  box.querySelector("[data-token-save]").addEventListener("click", save);
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); save(); } });
}
