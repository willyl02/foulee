// Réglages → Withings : le pas-à-pas pour relier son compte Withings (appli créée sur le tableau de bord de
// Withings, ClientID et Secret, autorisation), puis l'état de la connexion. Chaque profil a son propre accès.
import * as api from "./api.js";
import { copyText } from "./feedback.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const DEVICES = { corps: ["scale", "Balance"], tension: ["heart", "Tensiomètre"], sommeil: ["moon", "Sommeil"], activite: ["activity", "Activité"] };
const POLL = 1500;

const ext = (href, text) => `<a href="${F.escape(href)}" target="_blank" rel="noopener">${text}${icon("external")}</a>`;
const fail = (text) => `<p class="computed warn">${icon("warning")}<span>${F.escape(text)}</span></p>`;

export async function withingsPanel(box, boot, { toast, onChange, startSync }) {
  let info;
  try {
    info = await api.get("/api/withings", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(`État de Withings indisponible : ${err.message}`);
    return;
  }
  const where = boot.machine === "pc" ? "dans le Gestionnaire d'identification de Windows" : "sur le serveur, dans un fichier que seul Foulée peut lire";
  let editingApp = false;
  let showSteps = false;
  let polling = null;
  box.classList.add("wi-panel");

  // Résultat de la connexion qui vient de se terminer (retour de Withings) : affiché jusqu'à la prochaine
  // action (ou jusqu'à la fin du premier import, pour « connecté »)
  let note = info.note;
  if (note?.statut === "connecte" && !info.synchro?.en_cours) {
    note = null;  // premier import déjà fini : l'état de la connexion suffit
    toast("Compte Withings connecté : tes mesures sont importées.");
  }

  const noteHtml = () => {
    if (!note) return "";
    const ok = note.statut === "connecte";
    return `<p class="computed ${ok ? "ok" : "warn"} wi-note" role="status">${icon(ok ? "check" : "warning")}<span>${F.escape(note.message)}</span></p>`;
  };

  // ---------------------------------------------------------------- état
  const devices = () => (info.familles || []).map((f) => DEVICES[f]).filter(Boolean)
    .map(([ic, label]) => `<span class="badge-soft">${icon(ic)}${label}</span>`).join("");

  const connectedHtml = (actions = true) => {
    const refused = info.refus;
    const running = info.synchro?.en_cours;
    const since = info.connecte_le ? ` depuis le ${F.escape(F.dateLong(info.connecte_le.slice(0, 10), { year: true, weekday: false }))}` : "";
    const lines = [];
    if (refused) {
      lines.push(`<p class="computed warn">${icon("warning")}<span><b>Withings n'accepte plus l'accès de Foulée</b> depuis le ${F.escape(F.dateTime(refused.depuis))} : la synchro de tes mesures Withings est en pause. Tu as peut-être retiré l'accès dans ton compte Withings, ou la connexion a expiré. Reconnecte ton compte (étape 3) : tes mesures déjà importées restent là.</span></p>`);
    } else if (note?.statut !== "connecte") {  // sinon, la note du retour dit déjà « connecté »
      lines.push(`<p class="computed ok">${icon("check")}<span><b>Compte Withings connecté${since}.</b> Tes mesures arrivent avec la synchro, toutes les 3 heures.</span></p>`);
    }
    lines.push(`<dl class="about wi-about">
        <dt>Dernière synchro Withings</dt><dd>${running ? `<span class="wi-running">${icon("sync")}En cours…</span>` : info.derniere_synchro ? F.escape(F.relative(info.derniere_synchro)) : "pas encore"}</dd>
        <dt>Mesures reçues</dt><dd>${devices() || (running ? "import en cours…" : "aucune pour l'instant : pèse-toi, et la mesure arrivera à la prochaine synchro")}</dd>
        <dt>Appli Withings</dt><dd>ClientID …${F.escape(info.client_id_fin || "")}${info.appli_le ? `, enregistrée le ${F.escape(F.dateLong(info.appli_le.slice(0, 10), { year: true, weekday: false }))}` : ""}</dd>
      </dl>`);
    if (actions) lines.push(`<div class="inline-actions">
        ${info.vue ? `<a class="btn btn-primary" href="#/vue/withings">${icon("scale")}Ouvrir la vue Withings</a>` : ""}
        ${refused ? `<button class="btn btn-primary" type="button" data-connect>${icon("sync")}Reconnecter mon compte</button>` : `<button class="btn" type="button" data-sync ${running ? "disabled" : ""}>${icon("sync")}Synchroniser maintenant</button>`}
        <button class="btn btn-ghost" type="button" data-steps>${icon("help")}Revoir les étapes</button>
        <button class="btn btn-ghost btn-danger" type="button" data-disconnect>${icon("trash")}Déconnecter Withings</button>
      </div>`);
    return lines.join("");
  };

  // --------------------------------------------------------- les étapes
  const stepsHtml = () => {
    const appSaved = info.appli && !editingApp;
    const connected = info.connecte && !info.refus;
    return `
    <div class="callout wi-before">
      <b>Avant de commencer</b>
      <p>Il te faut un compte Withings, avec tes appareils (balance, tensiomètre, Sleep Analyzer, montre…) déjà reliés à l'appli Withings de ton téléphone. Compte une dizaine de minutes, une seule fois. Le plus simple : depuis ${boot.machine === "pc" ? "ce PC" : "un ordinateur relié à ton serveur par Tailscale"}, pour copier-coller d'une page à l'autre.</p>
      <p class="hint">Compte Withings créé après le 12 octobre 2026 ? Withings demande alors un abonnement Withings+ pour partager tes données avec une appli comme Foulée. Les comptes plus anciens ne sont pas concernés.</p>
    </div>

    <ol class="wi-steps">
      <li class="wi-step ${info.appli ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">1</span>
        <div class="wi-step-body">
          <h3>Crée ton appli Withings <small>gratuite, une seule fois</small></h3>
          <p>Withings ne donne pas une simple clé comme Garmin : chacun crée sa propre « appli » sur son site pour développeurs. Rassure-toi, pas besoin d'être développeur.</p>
          <ol class="wi-howto">
            <li>Ouvre le ${ext(info.tableau_de_bord, "tableau de bord développeur de Withings")} et connecte-toi avec ton compte Withings habituel (le même que dans l'appli). La page est en anglais : les mots à repérer sont en gras ci-dessous.</li>
            <li>Si Withings te demande de choisir un cloud, prends <b>Withings public cloud</b> (pas « US medical cloud »).</li>
            <li>Clique sur <b>Create an application</b>, choisis <b>Public API integration</b>, puis accepte les conditions.</li>
            <li>Remplis le formulaire :
              <dl class="wi-form-help">
                <dt>Target environment</dt><dd><b>Development</b> (c'est l'appli de toi seul)</dd>
                <dt>Application name</dt><dd><b>Foulée</b>, ou ce que tu veux</dd>
                <dt>Application description</dt><dd><b>Mon tableau de bord Foulée</b>, par exemple</dd>
                <dt>Registered URLs</dt><dd>colle exactement cette adresse, sans rien y changer :
                  <span class="wi-copy"><code data-relay>${F.escape(info.relais)}</code><button class="btn btn-ghost" type="button" data-copy-relay>${icon("copy")}Copier</button></span></dd>
              </dl>
              Le logo est facultatif.</li>
            <li>Valide : Withings affiche ton <b>ClientID</b> et ton <b>Secret</b>. Laisse cette page ouverte pour l'étape 2.</li>
          </ol>
          <p class="hint">L'adresse à coller est celle d'une petite page relais de Foulée : après « Autoriser », Withings y renvoie ton navigateur, et elle le renvoie aussitôt vers ton Foulée. Withings n'accepte pas l'adresse de ton PC directement. La page ne garde rien et ne transmet rien ailleurs.</p>
        </div>
      </li>

      <li class="wi-step ${appSaved ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">2</span>
        <div class="wi-step-body">
          <h3>Donne le ClientID et le Secret à Foulée</h3>
          ${appSaved ? `
            <p class="computed ok">${icon("check")}<span>Appli enregistrée ${where} (ClientID …${F.escape(info.client_id_fin || "")}${info.appli_le ? `, le ${F.escape(F.dateTime(info.appli_le))}` : ""}).</span></p>
            <div class="inline-actions"><button class="btn btn-ghost" type="button" data-edit-app>${icon("edit")}Changer d'appli Withings</button></div>` : `
            <p>Copie-les depuis le tableau de bord (chacun a son bouton de copie), puis colle-les ici.</p>
            <label class="field"><span>ClientID</span>
              <input type="text" data-client-id autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="Une longue suite de lettres et de chiffres"></label>
            <label class="field"><span>Secret</span>
              <span class="key-row"><input type="password" data-client-secret autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="Une autre longue suite, différente du ClientID">
              <button class="btn btn-ghost icon-btn" type="button" data-show-secret title="Afficher le Secret" aria-label="Afficher le Secret" aria-pressed="false">${icon("eye")}</button></span></label>
            <div class="inline-actions">
              <button class="btn btn-primary" type="button" data-save-app>${icon("check")}Enregistrer</button>
              ${info.appli ? `<button class="btn btn-ghost" type="button" data-cancel-app>Annuler</button>` : ""}
            </div>
            <p class="hint" data-app-status aria-live="polite"></p>
            <p class="hint">Le Secret est comme un mot de passe : Foulée le range ${where}, et ne l'affiche plus jamais. Ne le donne à personne, pas même dans un message pour demander de l'aide.</p>`}
        </div>
      </li>

      <li class="wi-step ${connected ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">3</span>
        <div class="wi-step-body">
          <h3>Connecte ton compte</h3>
          <ol class="wi-howto">
            <li>Clique sur le bouton ci-dessous : la page de Withings s'ouvre à la place de Foulée.</li>
            <li>Connecte-toi si besoin. Si ton compte Withings réunit plusieurs personnes (toute la famille, par exemple), choisis ton profil.</li>
            <li>Clique sur <b>Allow this app</b> (autoriser).</li>
            <li>Tu reviens tout seul ici, en passant un instant par la page relais de Foulée.</li>
          </ol>
          <div class="inline-actions">
            <button class="btn btn-primary" type="button" data-connect ${appSaved ? "" : "disabled"}>${icon("scale")}${connected ? "Reconnecter mon compte Withings" : "Connecter mon compte Withings"}</button>
            ${appSaved ? "" : `<span class="hint">D'abord les étapes 1 et 2.</span>`}
          </div>
          <p class="hint" data-connect-status aria-live="polite"></p>
        </div>
      </li>

      <li class="wi-step ${connected && info.derniere_synchro ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">4</span>
        <div class="wi-step-body">
          <h3>C'est prêt</h3>
          <p>Le premier import récupère ton historique${boot.reglages?.historique_depuis ? ` depuis le ${F.escape(F.dateLong(boot.reglages.historique_depuis, { year: true, weekday: false }))}` : ""}, et la vue <b>Withings</b> apparaît dans la colonne de gauche, juste après l'Accueil. Ensuite, tes pesées, ta tension et tes nuits arrivent avec la synchro, toutes les 3 heures, comme tes données Garmin. Tu retrouves aussi les mesures Withings dans toutes les tuiles (catégorie « Withings ») et Claude Desktop les voit.</p>
        </div>
      </li>
    </ol>
    ${helpHtml()}`;
  };

  const helpHtml = () => `
    <details class="wi-help">
      <summary>${icon("help")}Un souci ? Les cas les plus courants</summary>
      <dl>
        <dt>Withings affiche « redirect_uri_mismatch » ou une erreur d'adresse</dt>
        <dd>L'adresse enregistrée dans ton appli (Registered URLs) doit être exactement <code>${F.escape(info.relais)}</code>, barre finale comprise. Corrige-la dans le tableau de bord de Withings, puis relance la connexion (étape 3).</dd>
        <dt>« Withings refuse de terminer la connexion »</dt>
        <dd>Le ClientID ou le Secret ne correspondent pas : recopie-les avec leurs boutons de copie (étape 2, « Changer d'appli Withings »). Ou plus de 30 secondes se sont écoulées entre « Allow » et le retour dans Foulée : relance simplement la connexion.</dd>
        <dt>Je reste bloqué sur la page « Retour vers Foulée… »</dt>
        <dd>Clique sur son bouton « Revenir à Foulée » tout de suite. Foulée doit tourner sur ${boot.machine === "pc" ? "ce PC" : "ton serveur"}, et la connexion doit partir de cette même page des Réglages.</dd>
        <dt>Withings dit que mon compte ne peut pas partager ses données</dt>
        <dd>Compte créé après le 12 octobre 2026 sans abonnement Withings+ : Withings le demande pour partager tes données avec une appli comme Foulée.</dd>
        <dt>Connecté, mais aucune mesure</dt>
        <dd>Vérifie que tes mesures apparaissent dans l'appli Withings de ton téléphone : Foulée lit ce que Withings a reçu. Une nouvelle pesée arrive avec la synchro suivante, toutes les 3 heures, ou tout de suite avec « Synchroniser maintenant ».</dd>
      </dl>
    </details>`;

  // ------------------------------------------------------------- rendu
  const render = () => {
    let html = noteHtml();
    if (info.demo) {
      html += `<p class="computed">${icon("info")}<span>Mode démo : la vue « Withings » montre une balance, un tensiomètre et un Sleep Analyzer fictifs. Pour relier ton vrai compte Withings, quitte la démo.</span></p>
        ${info.vue ? `<div class="inline-actions"><a class="btn" href="#/vue/withings">${icon("scale")}Ouvrir la vue Withings</a></div>` : ""}`;
    } else if (!info.local) {
      html += info.connecte ? connectedHtml(false) : "";
      html += `<p class="computed">${icon("lock")}<span>La connexion à Withings se règle ${boot.machine === "pc" ? "sur le PC lui-même" : "par Tailscale, ou sur le serveur lui-même"} : le Secret de ton appli Withings ne voyage pas sur le réseau local.</span></p>`;
    } else if (info.connecte && !showSteps && !editingApp) {
      html += connectedHtml();
    } else {
      if (info.connecte && (showSteps || editingApp)) {
        html += `<div class="inline-actions"><button class="btn btn-ghost" type="button" data-hide-steps>${icon("check")}Revenir à l'état de la connexion</button></div>`;
      }
      html += stepsHtml();
    }
    box.innerHTML = html;
    wire();
  };

  // ------------------------------------------------------------ actions
  const refresh = async () => {
    info = { ...info, ...(await api.get("/api/withings", null, { fresh: true })) };
  };

  // Synchro en cours avec Withings connecté (premier import compris) : on suit, puis l'état se met à jour.
  // Pendant les étapes (ClientID en cours de saisie…), le panneau ne se redessine pas.
  const follow = () => {
    if (polling || !info.connecte || !info.synchro?.en_cours) return;
    polling = setInterval(async () => {
      if (!box.isConnected) { clearInterval(polling); polling = null; return; }
      try {
        await refresh();
      } catch (err) { return; }
      const typing = editingApp || showSteps;
      if (info.synchro?.en_cours) {
        if (!typing) render();
        return;
      }
      // Fini : la colonne annonce le bilan (un seul message), le panneau se met à jour
      clearInterval(polling);
      polling = null;
      if (note?.statut === "connecte") note = null;
      if (!typing) render();
      onChange?.();
    }, POLL);
  };

  const connect = async (button) => {
    const status = box.querySelector("[data-connect-status]");
    button.disabled = true;
    note = null;
    if (status) { status.classList.remove("error"); status.textContent = "Ouverture de la page de Withings…"; }
    try {
      const res = await api.post("/api/withings/connexion", { origine: location.origin });
      location.href = res.url;
    } catch (err) {
      button.disabled = false;
      if (status) { status.classList.add("error"); status.textContent = err.message; } else toast(err.message, { error: true });
    }
  };

  const wire = () => {
    box.querySelector("[data-copy-relay]")?.addEventListener("click", async () => {
      toast(await copyText(info.relais) ? "Adresse copiée : colle-la dans « Registered URLs »." : "Copie impossible : sélectionne l'adresse et copie-la.");
    });
    box.querySelector("[data-show-secret]")?.addEventListener("click", (event) => {
      const input = box.querySelector("[data-client-secret]");
      const visible = input.type === "password";
      input.type = visible ? "text" : "password";
      event.currentTarget.setAttribute("aria-pressed", String(visible));
    });
    box.querySelector("[data-edit-app]")?.addEventListener("click", () => { editingApp = true; render(); box.querySelector("[data-client-id]")?.focus(); });
    box.querySelector("[data-cancel-app]")?.addEventListener("click", () => { editingApp = false; render(); });
    box.querySelector("[data-steps]")?.addEventListener("click", () => { showSteps = true; render(); });
    box.querySelector("[data-hide-steps]")?.addEventListener("click", () => { showSteps = false; editingApp = false; render(); });
    box.querySelector("[data-save-app]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const status = box.querySelector("[data-app-status]");
      const id = box.querySelector("[data-client-id]");
      const secret = box.querySelector("[data-client-secret]");
      if (!id.value.trim() || !secret.value.trim()) {
        status.classList.add("error");
        status.textContent = "Colle le ClientID et le Secret, chacun dans son champ.";
        (id.value.trim() ? secret : id).focus();
        return;
      }
      button.disabled = true;
      status.classList.remove("error");
      status.textContent = "Enregistrement…";
      try {
        info = { ...info, ...(await api.put("/api/withings/appli", { client_id: id.value, client_secret: secret.value })) };
        id.value = "";
        secret.value = "";  // vidés tout de suite : rien ne reste dans la page
        editingApp = false;
        note = null;
        showSteps = true;
        toast("Appli Withings enregistrée : passe à l'étape 3.");
        render();
        box.querySelector("[data-connect]")?.focus();
      } catch (err) {
        status.classList.add("error");
        status.textContent = err.message;
        button.disabled = false;
      }
    });
    box.querySelectorAll("[data-connect]").forEach((button) => button.addEventListener("click", () => connect(button)));
    box.querySelector("[data-sync]")?.addEventListener("click", async (event) => {
      event.currentTarget.disabled = true;
      note = null;
      await startSync();  // la synchro de toutes les sources, suivie dans la colonne comme le bouton « Synchroniser »
      try {
        await refresh();
      } catch (err) { /* l'état se rafraîchira au prochain passage */ }
      render();
      follow();
    });
    box.querySelector("[data-disconnect]")?.addEventListener("click", async () => {
      if (!window.confirm("Déconnecter Withings ? La synchro de tes mesures Withings s'arrête et la vue « Withings » s'en va. Les mesures déjà importées restent dans Foulée, et ton appli Withings reste enregistrée pour te reconnecter en un clic.")) return;
      try {
        info = { ...info, ...(await api.del("/api/withings")) };
        showSteps = false;
        note = null;
        toast("Withings déconnecté.");
        render();
        onChange?.();
      } catch (err) {
        toast(`Déconnexion impossible : ${err.message}`, { error: true });
      }
    });
  };

  render();
  follow();
}
