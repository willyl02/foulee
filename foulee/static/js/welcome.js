// Page d'accueil du premier lancement : clé Garmin, premier import, Claude Desktop.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { claudePanel, keyPanel } from "./system.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const SINCE = [[182, "6 mois"], [365, "1 an"], [730, "2 ans (conseillé)"], [1825, "5 ans"], ["date", "Depuis une date précise…"]];

export function renderWelcome(page, boot, { toast, onImport, onDone }) {
  const local = boot.acces === "local";
  const hasData = Boolean(boot.volumes.daily || boot.volumes.activities);
  // Profil autre que le principal : sa clé et son import ; l'installation (démo, Claude, ancien dossier) ne le regarde pas
  const principal = boot.utilisateur?.principal !== false;
  const me = (boot.utilisateurs || []).find((u) => u.courant);
  page.innerHTML = `
    <div class="welcome">
      <header class="welcome-head">
        <span class="blaze" aria-hidden="true"></span>
        <div><h1>${principal ? "Bienvenue dans Foulée" : `Bienvenue, ${F.escape(me?.prenom || "")}`}</h1>
          <p>${principal ? "Tes données Garmin rangées chez toi, des tableaux de bord que tu composes, et Claude pour les analyser avec toi. Trois étapes et c'est parti."
            : "Ce profil est à toi : tes données Garmin, tes vues et tes réglages, séparés de ceux des autres. Deux étapes et c'est parti."}</p></div>
      </header>
      <div data-previous></div>
      <ol class="welcome-steps">
        <li class="step" data-step="cle">
          <div class="step-num" aria-hidden="true">1</div>
          <div class="step-body"><h2>${icon("key")}Ta clé API Garmin</h2><div data-key></div>
            ${local && !boot.demo ? `<p class="hint welcome-strava">${icon("activity")}<span>Pas de montre Garmin (Coros, Suunto, Polar, Apple…) ? Tes séances peuvent venir de Strava, en lecture seule : <a href="#/reglages?section=strava">Réglages → Strava</a>. Ensuite, ouvre simplement ton tableau de bord.</span></p>` : ""}</div>
        </li>
        <li class="step" data-step="import">
          <div class="step-num" aria-hidden="true">2</div>
          <div class="step-body"><h2>${icon("download")}Premier import</h2><div data-import></div></div>
        </li>
        ${boot.machine === "pc" && principal ? `<li class="step" data-step="claude">
          <div class="step-num" aria-hidden="true">3</div>
          <div class="step-body"><h2>${icon("chat")}Claude Desktop <span class="optional">facultatif</span></h2><div data-claude></div></div>
        </li>` : ""}
      </ol>
      <div class="welcome-foot">
        <button class="btn btn-primary" type="button" data-done>${icon("chart")}Ouvrir mon tableau de bord</button>
        ${local && principal && !boot.demo && !boot.cle ? `<button class="btn btn-ghost" type="button" data-demo>${icon("info")}Pas de clé sous la main ? Découvrir avec des données fictives</button>` : ""}
      </div>
    </div>`;

  const step = (name) => page.querySelector(`[data-step="${name}"]`);
  const markDone = (name, done = true) => step(name)?.classList.toggle("done", done);
  let keyReady = boot.cle;

  if (!local) {
    page.querySelector("[data-key]").innerHTML = `<p class="computed">La clé s'enregistre depuis le serveur lui-même ou par Tailscale.</p>`;
  } else if (boot.demo) {
    page.querySelector("[data-key]").innerHTML = `<p class="computed">Tu es en mode démo : quitte-le (bandeau en haut de page) pour enregistrer ta clé.</p>`;
  } else {
    keyPanel(page.querySelector("[data-key]"), boot, {
      toast, compact: true,
      onSaved: (info) => {
        keyReady = info.enregistree;
        markDone("cle", keyReady);
        if (keyReady) page.querySelector("[data-demo]")?.remove();
        renderImport();
      },
    });
  }
  markDone("cle", keyReady);
  markDone("import", hasData);

  // ------------------------------------------------------------ import
  const importBox = page.querySelector("[data-import]");
  function renderImport() {
    if (hasData) {
      importBox.innerHTML = `<p class="computed ok">${icon("check")}<span>Déjà fait : ${F.int(boot.volumes.activities)} séances et ${F.int(boot.volumes.daily)} valeurs quotidiennes. La synchro continue ensuite toute seule.</span></p>`;
      return;
    }
    importBox.innerHTML = `
      <p class="computed">Foulée récupère ton historique chez Garmin : séances, sommeil, VFC, fréquence cardiaque, pas… Compte quelques minutes pour deux ans ; tu peux utiliser l'interface pendant ce temps.</p>
      <div class="inline-actions">
        <label class="inline-field"><span>Depuis</span>
          <select data-since>${SINCE.map(([v, l]) => `<option value="${v}" ${v === 730 ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <input type="date" data-since-date hidden aria-label="Date de début" max="${F.isoDate(new Date())}">
        <button class="btn btn-primary" type="button" data-import-go ${keyReady ? "" : "disabled"}>${icon("download")}Lancer l'import</button>
      </div>
      <p class="hint" data-import-status aria-live="polite">${keyReady ? "" : "Enregistre d'abord ta clé (étape 1)."}</p>`;
    const select = importBox.querySelector("[data-since]");
    const dateInput = importBox.querySelector("[data-since-date]");
    select.addEventListener("change", () => { dateInput.hidden = select.value !== "date"; if (!dateInput.hidden) dateInput.focus(); });
    importBox.querySelector("[data-import-go]").addEventListener("click", startImport);
  }

  async function startImport() {
    const select = importBox.querySelector("[data-since]");
    const dateInput = importBox.querySelector("[data-since-date]");
    const status = importBox.querySelector("[data-import-status]");
    const since = select.value === "date" ? dateInput.value : F.isoDate(F.addDays(new Date(), -Number(select.value)));
    if (!since) { status.textContent = "Choisis une date de début."; return; }
    try {
      const res = await api.post("/api/sync", { depuis: since });
      if (!res.lance) { status.textContent = res.message; return; }
    } catch (err) {
      status.textContent = err.message;
      return;
    }
    onImport?.();
    follow();
  }

  async function follow() {
    importBox.innerHTML = `<p class="computed" data-msg>Démarrage…</p><div class="progress"><span></span></div>
      <p class="hint">Tu peux ouvrir ton tableau de bord dès maintenant : l'import continue en arrière-plan.</p>`;
    const msg = importBox.querySelector("[data-msg]");
    const bar = importBox.querySelector(".progress > span");
    for (;;) {
      await sleep(1500);
      if (!importBox.isConnected) return;  // on a quitté la page
      let status;
      try { status = await api.get("/api/sync", null, { fresh: true }); } catch (err) { continue; }
      const job = status.job;
      if (job.en_cours || status.en_cours) {
        msg.textContent = job.message || "Import en cours…";
        bar.style.width = `${Math.round((job.progression || 0) * 100)}%`;
        continue;
      }
      const garmin = job.resultat?.sources?.garmin || {};
      if (job.erreur || garmin.erreur) {
        importBox.innerHTML = `<p class="computed warn">${icon("warning")}<span>${F.escape(job.erreur || garmin.erreur)}</span></p>`;
        renderImportRetry();
        return;
      }
      importBox.innerHTML = `<p class="computed ok">${icon("check")}<span>Import terminé : ${F.int(garmin.seances_nouvelles || 0)} séances${garmin.fit ? ` et ${F.int(garmin.fit)} fichiers FIT` : ""}. Ensuite, la synchro se fait toute seule.</span></p>`;
      markDone("import");
      return;
    }
  }

  function renderImportRetry() {
    importBox.insertAdjacentHTML("beforeend", `<div class="inline-actions"><button class="btn" type="button" data-retry>${icon("reset")}Réessayer</button></div>`);
    importBox.querySelector("[data-retry]").addEventListener("click", () => renderImport());
  }

  if (boot.synchro?.en_cours) follow(); else renderImport();

  // ----------------------------------------------------- Claude Desktop
  const claudeBox = page.querySelector("[data-claude]");
  if (claudeBox) {
    if (local) {
      claudePanel(claudeBox, { toast, compact: true, onChange: (info) => markDone("claude", Boolean(info?.connecte)) });
    } else {
      claudeBox.innerHTML = `<p class="computed">Claude Desktop se relie depuis le PC où il est installé.</p>`;
    }
  }

  // --------------------------------- données d'une ancienne installation
  if (local && principal && !hasData && !boot.demo) {
    api.get("/api/dossier", { anciennes: 1 }, { fresh: true }).then((info) => {
      const old = (info.anciennes || [])[0];
      if (!old) return;
      const box = page.querySelector("[data-previous]");
      const c = old.contenu;
      box.innerHTML = `<div class="callout">
          <b>Tu as déjà utilisé Foulée sur ce PC</b>
          <p>Des données existent dans <code>${F.escape(old.chemin)}</code> : ${F.int(c.seances)} séances${c.debut ? `, du ${F.escape(F.dateLong(c.debut, { year: true, weekday: false }))} au ${F.escape(F.dateLong(c.fin, { year: true, weekday: false }))}` : ""}. Reprends-les ici : rien à réimporter de chez Garmin.</p>
          <div class="inline-actions"><button class="btn btn-primary" type="button" data-take>${icon("download")}Reprendre ces données</button>
            <span class="hint" data-take-status>Copie : l'ancien dossier n'est pas modifié.</span></div>
        </div>`;
      box.querySelector("[data-take]").addEventListener("click", async (event) => {
        event.currentTarget.disabled = true;
        const status = box.querySelector("[data-take-status]");
        status.textContent = "Copie en cours…";
        try {
          const res = await api.put("/api/dossier", { chemin: old.chemin, mode: "importer" });
          toast(`Données reprises : ${F.int(res.rapport.base?.seances)} séances.`);
          setTimeout(() => location.reload(), 800);
        } catch (err) {
          status.textContent = err.message;
          event.currentTarget.disabled = false;
        }
      });
    }).catch(() => { /* rien à proposer */ });
  }

  // ------------------------------------------------------------- sortie
  page.querySelector("[data-done]").addEventListener("click", onDone);
  page.querySelector("[data-demo]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.lastChild.textContent = "Préparation des données fictives (une vingtaine de secondes)…";
    try {
      await api.post("/api/demo", { actif: true });
      for (let i = 0; i < 120; i += 1) {
        const st = await api.get("/api/demo", null, { fresh: true });
        if (st.erreur) throw new Error(st.erreur);
        if (!st.preparation) break;
        await sleep(1000);
      }
      location.hash = "#/";
      location.reload();
    } catch (err) {
      toast(`Démo indisponible : ${err.message}`, { error: true });
      button.disabled = false;
    }
  });
}
