// Réglages → Strava : le pas-à-pas (appli Strava de l'installation, Client ID et Client Secret, autorisation de
// chaque profil), les règles de Strava, puis l'état de la connexion.
import * as api from "./api.js";
import { copyText } from "./feedback.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const POLL = 1500;
const ext = (href, text) => `<a href="${F.escape(href)}" target="_blank" rel="noopener">${text}${icon("external")}</a>`;
const fail = (text) => `<p class="computed warn">${icon("warning")}<span>${F.escape(text)}</span></p>`;

/** Ce que Strava impose, dit simplement (affiché avant les étapes et dans l'aide). */
export function stravaRules(info) {
  return `<ul class="st-rules">
    <li>${icon("lock")}<span><b>Lecture seule.</b> Foulée ne demande que le droit de lire tes séances : il ne peut rien publier, modifier ni effacer sur ton compte Strava.</span></li>
    <li>${icon("clock")}<span><b>${F.escape(String(info.garde_heures || 48))} heures au plus.</b> Strava interdit de garder ses données : Foulée les relit à chaque synchro et oublie ce qui n'a pas été relu depuis ${F.escape(String(info.garde_heures || 48))} heures. Une séance effacée sur Strava disparaît aussi de Foulée.</span></li>
    <li>${icon("chat")}<span><b>Pas pour Claude.</b> Strava interdit de confier ses données à une IA : Claude Desktop ne voit pas tes séances Strava dans Foulée. Pour en parler avec Claude, branche le connecteur Strava officiel dans Claude.</span></li>
    <li>${icon("layers")}<span><b>Pas de doublons.</b> Une séance que Garmin a déjà donnée n'est comptée qu'une fois, avec les données de Garmin ; son titre et sa description Strava s'affichent dessus.</span></li>
  </ul>`;
}

export async function stravaPanel(box, boot, { toast, onChange, startSync }) {
  let info;
  try {
    info = await api.get("/api/strava", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(`État de Strava indisponible : ${err.message}`);
    return;
  }
  const where = boot.machine === "pc" ? "dans le Gestionnaire d'identification de Windows" : "sur le serveur, dans un fichier que seul Foulée peut lire";
  let editingApp = false;
  let showSteps = false;
  let polling = null;
  box.classList.add("wi-panel", "st-panel");

  let note = info.note;
  if (note?.statut === "connecte" && !info.synchro?.en_cours) {
    note = null;
    toast("Compte Strava connecté : tes séances sont importées.");
  }
  const noteHtml = () => {
    if (!note) return "";
    const ok = note.statut === "connecte";
    return `<p class="computed ${ok ? "ok" : "warn"} wi-note" role="status">${icon(ok ? "check" : "warning")}<span>${F.escape(note.message)}</span></p>`;
  };

  const quotaText = () => {
    const q = info.quota || {};
    return `${F.int(q.used_day || 0)} sur ${F.int(q.limit_day || 1000)} aujourd'hui (${F.int(q.used15 || 0)} sur ${F.int(q.limit15 || 100)} ce quart d'heure)`;
  };

  // ---------------------------------------------------------------- état
  const connectedHtml = (actions = true) => {
    const refused = info.refus;
    const running = info.synchro?.en_cours;
    const c = info.cache || {};
    const since = info.connecte_le ? ` depuis le ${F.escape(F.dateLong(info.connecte_le.slice(0, 10), { year: true, weekday: false }))}` : "";
    const lines = [];
    if (refused) {
      lines.push(`<p class="computed warn">${icon("warning")}<span><b>Strava n'accepte plus l'accès de Foulée</b> depuis le ${F.escape(F.dateTime(refused.depuis))} : tu as peut-être retiré Foulée de tes applis dans Strava, ou l'appli Strava a changé. Tes séances Strava ont été oubliées, comme Strava le demande. Reconnecte ton compte (étape 3) pour les retrouver.</span></p>`);
    } else if (note?.statut !== "connecte") {
      lines.push(`<p class="computed ok">${icon("check")}<span><b>Compte Strava connecté${since}.</b> Tes séances arrivent avec la synchro automatique (toutes les 3 heures par défaut).</span></p>`);
    }
    if (!info.seances_privees && !refused) {
      lines.push(`<p class="computed info">${icon("info")}<span>Tes séances « Moi uniquement » restent invisibles : la case correspondante a été décochée sur la page de Strava. Reconnecte ton compte en la laissant cochée pour les voir.</span></p>`);
    }
    lines.push(`<dl class="about wi-about">
        <dt>Séances Strava</dt><dd>${running ? `<span class="wi-running">${icon("sync")}Synchro en cours…</span>` : c.seances ? `${F.int(c.seules)} ajoutée${c.seules > 1 ? "s" : ""} à tes séances, ${F.int(c.copies)} déjà données par Garmin` : "pas encore"}</dd>
        <dt>Dernière liste complète</dt><dd>${c.liste_complete_le ? F.escape(F.relative(c.liste_complete_le)) : "pas encore"}${c.premiere ? `, séances depuis le ${F.escape(F.dateLong(c.premiere, { year: true, weekday: false }))}` : ""}</dd>
        <dt>Appels à Strava</dt><dd>${quotaText()}</dd>
        <dt>Appli Strava</dt><dd>Client ID ${F.escape(info.client_id || "")}${info.principal ? "" : ` (celle de ${F.escape(info.prenom_principal || "l'utilisateur principal")})`}</dd>
      </dl>`);
    if (actions) lines.push(`<div class="inline-actions">
        ${refused ? `<button class="btn btn-primary" type="button" data-connect>${icon("sync")}Reconnecter mon compte</button>` : `<button class="btn" type="button" data-sync ${running ? "disabled" : ""}>${icon("sync")}Synchroniser maintenant</button>`}
        <button class="btn btn-ghost" type="button" data-steps>${icon("help")}Revoir les étapes</button>
        <button class="btn btn-ghost btn-danger" type="button" data-disconnect>${icon("trash")}Déconnecter Strava</button>
      </div>`);
    return lines.join("");
  };

  // --------------------------------------------------------- les étapes
  const stepsHtml = () => {
    const appSaved = info.appli && !editingApp;
    const connected = info.connecte && !info.refus;
    const domain = info.domaine_rappel || location.hostname;
    const head = F.escape(info.prenom_principal || "l'utilisateur principal");
    const appName = `Foulée de ${(boot.profil?.prenom_affiche || info.prenom_principal || "").trim() || "moi"}`;
    const step1 = info.principal ? `
          <p>Strava ne donne pas de clé toute faite : on crée une « appli » sur son site, une seule pour toute l'installation (les autres profils s'en servent aussi). Pas besoin d'être développeur.</p>
          <ol class="wi-howto">
            <li>Ouvre ${ext(info.page_appli, "les réglages API de Strava")} et connecte-toi avec ton compte Strava (abonné : voir plus haut).</li>
            <li>Remplis le formulaire :
              <dl class="wi-form-help">
                <dt>Application Name</dt><dd><b>${F.escape(appName)}</b>, ou ce que tu veux, <b>sans le mot « Strava »</b> (Strava le refuse)</dd>
                <dt>Category</dt><dd><b>Visualizer</b></dd>
                <dt>Club</dt><dd>laisse vide</dd>
                <dt>Website</dt><dd><b>https://github.com/willyl02/foulee</b></dd>
                <dt>Application Description</dt><dd><b>Mon tableau de bord Foulée</b>, par exemple</dd>
                <dt>Authorization Callback Domain</dt><dd>colle exactement :
                  <span class="wi-copy"><code data-domain>${F.escape(domain)}</code><button class="btn btn-ghost" type="button" data-copy-domain>${icon("copy")}Copier</button></span></dd>
              </dl></li>
            <li>Accepte l'accord de l'API, puis <b>Create</b>. Strava demande ensuite une image pour l'appli : prends ${`<a href="/static/icons/icon-512.png" download="foulee.png">celle de Foulée</a>`} (jamais le logo de Strava).</li>
            <li>La page « My API Application » affiche le <b>Client ID</b> et le <b>Client Secret</b> (clique sur « show »). Laisse-la ouverte pour l'étape 2.</li>
            ${(boot.utilisateurs || []).length > 1 ? `<li>D'autres profils de cette installation utiliseront Strava ? Sur la même page, passe l'appli à <b>10 athlètes</b> (sans examen par Strava) : sinon, seul ton compte peut s'y connecter.</li>` : ""}
          </ol>
          <p class="hint">Le domaine de rappel est l'adresse de Foulée, telle que ton navigateur l'affiche : c'est là que Strava te renvoie après « Autoriser ». 127.0.0.1 et localhost sont toujours acceptés par Strava, ce qui permet de te connecter aussi depuis le PC.</p>` : `
          <p>${info.appli ? `<span class="computed ok" style="display:flex">${icon("check")}<span>L'appli Strava de l'installation est enregistrée par ${head}.</span></span>` : `C'est ${head} qui crée l'appli Strava de l'installation, depuis son profil (Réglages → Strava). Demande-lui de passer l'appli à 10 athlètes pour que ton compte puisse s'y connecter.`}</p>`;
    return `
    <div class="callout wi-before">
      <b>Ce que Strava impose</b>
      ${stravaRules(info)}
      <p class="hint">Depuis juin 2026, Strava réserve son API aux abonnés : le compte qui crée l'appli Strava de Foulée (étape 1) doit avoir un abonnement Strava. Les autres profils s'y connectent sans abonnement.</p>
    </div>

    <ol class="wi-steps">
      <li class="wi-step ${info.appli ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">1</span>
        <div class="wi-step-body">
          <h3>Crée l'appli Strava de Foulée <small>une seule fois, pour toute l'installation</small></h3>
          ${step1}
        </div>
      </li>

      <li class="wi-step ${appSaved ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">2</span>
        <div class="wi-step-body">
          <h3>Donne le Client ID et le Client Secret à Foulée</h3>
          ${appSaved ? `
            <p class="computed ok">${icon("check")}<span>Appli enregistrée (Client ID ${F.escape(info.client_id || "")})${info.principal ? `, rangée ${where}` : ""}.</span></p>
            ${info.principal ? `<div class="inline-actions"><button class="btn btn-ghost" type="button" data-edit-app>${icon("edit")}Changer d'appli Strava</button>
              <button class="btn btn-ghost btn-danger" type="button" data-forget-app>${icon("trash")}Oublier l'appli</button></div>` : ""}` : info.principal ? `
            <p>Recopie-les depuis la page « My API Application » de Strava.</p>
            <label class="field"><span>Client ID</span>
              <input type="text" inputmode="numeric" data-client-id autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="Un nombre, par exemple 123456"></label>
            <label class="field"><span>Client Secret</span>
              <span class="key-row"><input type="password" data-client-secret autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="40 lettres et chiffres">
              <button class="btn btn-ghost icon-btn" type="button" data-show-secret title="Afficher le Client Secret" aria-label="Afficher le Client Secret" aria-pressed="false">${icon("eye")}</button></span></label>
            <div class="inline-actions">
              <button class="btn btn-primary" type="button" data-save-app>${icon("check")}Enregistrer</button>
              ${info.appli ? `<button class="btn btn-ghost" type="button" data-cancel-app>Annuler</button>` : ""}
            </div>
            <p class="hint" data-app-status aria-live="polite"></p>
            <p class="hint">Le Client Secret est comme un mot de passe : Foulée le range ${where}, et ne l'affiche plus jamais. Ne le donne à personne.</p>` : `
            <p class="hint">À faire par ${head}.</p>`}
        </div>
      </li>

      <li class="wi-step ${connected ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">3</span>
        <div class="wi-step-body">
          <h3>Connecte ton compte Strava</h3>
          <ol class="wi-howto">
            <li>Clique sur le bouton ci-dessous : la page de Strava s'ouvre à la place de Foulée.</li>
            <li>Connecte-toi si besoin, laisse cochée la case des séances, puis clique sur <b>Autoriser</b>.</li>
            <li>Tu reviens tout seul ici, et le premier import démarre.</li>
          </ol>
          <div class="inline-actions">
            <button class="btn btn-primary" type="button" data-connect ${appSaved ? "" : "disabled"}>${icon("activity")}${connected ? "Reconnecter mon compte Strava" : "Connecter mon compte Strava"}</button>
            ${appSaved ? "" : `<span class="hint">D'abord les étapes 1 et 2.</span>`}
          </div>
          <p class="hint" data-connect-status aria-live="polite"></p>
        </div>
      </li>

      <li class="wi-step ${connected && info.cache?.liste_complete_le ? "done" : ""}">
        <span class="wi-step-num" aria-hidden="true">4</span>
        <div class="wi-step-body">
          <h3>C'est prêt</h3>
          <p>Tes séances Strava rejoignent tes séances dans toutes les vues : listes, volumes, charge, renfo. Chaque tuile dit d'où viennent ses chiffres (Garmin, Strava, Withings), et une séance Strava propose « View on Strava ». Les séances de musculation notées avec une appli comme Hevy ou Strong montrent leurs exercices, sous le nom écrit dans la description.</p>
        </div>
      </li>
    </ol>
    ${helpHtml()}`;
  };

  const helpHtml = () => `
    <details class="wi-help">
      <summary>${icon("help")}Un souci ? Les cas les plus courants</summary>
      <dl>
        <dt>Strava affiche « Bad Request » et « redirect_uri invalid »</dt>
        <dd>Le domaine de rappel de l'appli Strava ne correspond pas à l'adresse de Foulée. Dans les réglages API de Strava, mets <code>${F.escape(info.domaine_rappel || location.hostname)}</code> dans « Authorization Callback Domain », puis relance la connexion.</dd>
        <dt>« Limit of connected athletes exceeded »</dt>
        <dd>L'appli Strava n'accepte qu'un athlète tant qu'elle n'est pas passée à 10 : ${F.escape(info.prenom_principal || "l'utilisateur principal")} le fait depuis les réglages API de Strava.</dd>
        <dt>Strava refuse de créer l'appli, ou l'API répond « Forbidden »</dt>
        <dd>Depuis juin 2026, l'API de Strava demande un abonnement Strava au compte qui a créé l'appli.</dd>
        <dt>Des séances Strava ont disparu</dt>
        <dd>Foulée n'a pas pu les relire depuis ${F.escape(String(info.garde_heures || 48))} heures (PC éteint, pas d'Internet) : elles reviennent avec la synchro suivante. C'est la règle de Strava.</dd>
        <dt>Le détail ou les courbes d'une séance arrivent plus tard</dt>
        <dd>Strava limite les appels (${F.escape(quotaText())}). Foulée garde de la marge et complète au fil des synchros.</dd>
      </dl>
    </details>`;

  // ------------------------------------------------------------- rendu
  const render = () => {
    let html = noteHtml();
    if (info.demo) {
      html += `<p class="computed">${icon("info")}<span>Mode démo : des séances fictives « vues sur Strava » (vélo avec un compteur Wahoo, musculation notée avec Hevy) s'ajoutent à celles de Garmin, et les séances Garmin montrent leur titre Strava. Pour relier ton vrai compte Strava, quitte la démo.</span></p>${stravaRules(info)}`;
    } else if (!info.local) {
      html += info.connecte ? connectedHtml(false) : "";
      html += `<p class="computed">${icon("lock")}<span>La connexion à Strava se règle ${boot.machine === "pc" ? "sur le PC lui-même" : "par Tailscale, ou sur le serveur lui-même"} : le Client Secret ne voyage pas sur le réseau local.</span></p>`;
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
    info = { ...info, ...(await api.get("/api/strava", null, { fresh: true })) };
  };

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
    if (status) { status.classList.remove("error"); status.textContent = "Ouverture de la page de Strava…"; }
    try {
      const res = await api.post("/api/strava/connexion", { origine: location.origin });
      location.href = res.url;
    } catch (err) {
      button.disabled = false;
      if (status) { status.classList.add("error"); status.textContent = err.message; } else toast(err.message, { error: true });
    }
  };

  const wire = () => {
    box.querySelector("[data-copy-domain]")?.addEventListener("click", async () => {
      toast(await copyText(info.domaine_rappel || location.hostname) ? "Domaine copié : colle-le dans « Authorization Callback Domain »." : "Copie impossible : sélectionne le domaine et copie-le.");
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
        status.textContent = "Colle le Client ID et le Client Secret, chacun dans son champ.";
        (id.value.trim() ? secret : id).focus();
        return;
      }
      button.disabled = true;
      status.classList.remove("error");
      status.textContent = "Enregistrement…";
      try {
        info = { ...info, ...(await api.put("/api/strava/appli", { client_id: id.value, client_secret: secret.value })) };
        id.value = "";
        secret.value = "";  // vidés tout de suite : rien ne reste dans la page
        editingApp = false;
        note = null;
        showSteps = true;
        toast("Appli Strava enregistrée : passe à l'étape 3.");
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
      await startSync();
      try {
        await refresh();
      } catch (err) { /* l'état se rafraîchira au prochain passage */ }
      render();
      follow();
    });
    box.querySelector("[data-disconnect]")?.addEventListener("click", async () => {
      if (!window.confirm("Déconnecter Strava ? Foulée retire son accès chez Strava et oublie tes séances Strava (Strava ne permet pas de les garder). Tes séances Garmin ne bougent pas, et l'appli Strava reste enregistrée pour te reconnecter en un clic.")) return;
      try {
        const res = await api.del("/api/strava");
        info = { ...info, ...res };
        showSteps = false;
        note = null;
        toast(res.revoque === false ? "Strava déconnecté. Strava n'a pas pu être joint : retire aussi Foulée de « Mes applis » sur Strava." : "Strava déconnecté.");
        render();
        onChange?.();
      } catch (err) {
        toast(`Déconnexion impossible : ${err.message}`, { error: true });
      }
    });
    box.querySelector("[data-forget-app]")?.addEventListener("click", async () => {
      if (!window.confirm("Oublier l'appli Strava ? Les profils connectés à Strava ne pourront plus se synchroniser tant qu'une appli n'est pas enregistrée de nouveau.")) return;
      try {
        info = { ...info, ...(await api.del("/api/strava/appli")) };
        editingApp = false;
        showSteps = true;
        toast("Appli Strava oubliée.");
        render();
        onChange?.();
      } catch (err) {
        toast(err.message, { error: true });
      }
    });
  };

  render();
  follow();
}
