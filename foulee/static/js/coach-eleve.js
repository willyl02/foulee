// Côté élève : « Mon coach » (ses séances proposées, la conversation, ce que je partage) et l'écran de l'accord,
// case par case, sans lequel rien ne part vers le relais.
import * as api from "./api.js";
import * as F from "./format.js";
import { calendarCard } from "./coach-cal.js";
import { icon } from "./icons.js";
import { avatar, blocksHtml, dayLabel, fail, loading, mountThread, statusChip, sportIcon } from "./coach-ui.js";
import { clubLogoURL } from "./settings-club.js";

const CHOICES = [
  ["seances", "Tes séances des 4 dernières semaines", "En résumé : date, sport, distance, durée, allure, FC, charge, effet d'entraînement, tours, renfo, ta description. Jamais celles venues de Strava."],
  ["objectif", "Ton objectif et ta VMA", "La course visée, sa date et ton temps visé : ton coach calcule tes allures."],
  ["gps", "Le tracé GPS de tes séances", "Une version simplifiée de chaque parcours, sans fond de carte."],
  ["masquer", "… en masquant le départ et l'arrivée", "Les 500 premiers et derniers mètres restent cachés : ta maison n'apparaît pas.", "sub"],
  ["sante", "Ton sommeil, ta VFC et ta FC au repos", "Une valeur par jour, pour que ton coach adapte la charge."],
  ["poids", "Ton poids", "Si une balance est reliée à Foulée (Withings)."],
];

function shareList(accord) {
  if (!accord) return `<p class="co-empty">Tu n'as encore rien choisi : rien n'est parti vers le relais.</p>`;
  const yes = (v, extra = "") => (v ? `<span class="co-chip good">${icon("check")}oui${extra}</span>` : `<span class="co-chip">non</span>`);
  return `<dl class="co-dl wide"><dt>Séances (4 semaines)</dt><dd>${yes(accord.seances)}</dd><dt>Objectif, VMA</dt><dd>${yes(accord.objectif)}</dd>
    <dt>Tracés GPS</dt><dd>${yes(accord.gps, accord.gps && accord.masquer ? ", départ et arrivée masqués" : "")}</dd>
    <dt>Sommeil, VFC</dt><dd>${yes(accord.sante)}</dd><dt>Poids</dt><dd>${yes(accord.poids)}</dd></dl>`;
}

/** L'envoi sur la montre d'une séance : « sur ta montre », « à renvoyer » (le coach l'a modifiée), ou rien. */
function watchChip(m) {
  if (!m) return "";
  if (!m.a_jour) return `<span class="co-chip warn" title="${F.escape(m.erreur || "Ton coach l'a modifiée depuis l'envoi")}">${icon("watch")}à renvoyer</span>`;
  return `<span class="co-chip good" title="Dans ton calendrier Garmin pour le ${F.escape(dayLabel(m.date).toLowerCase())} (envoyée ${F.escape(F.relative(m.envoye_le))}${m.par === "coach" ? " par ton coach" : ""})">${icon("watch")}sur ta montre</span>`;
}

function proposal(p, vma, watch) {
  const href = p.seance ? `#/coach/seance/${encodeURIComponent(p.seance.cle)}` : "";
  const open = p.statut !== "fait" && p.statut !== "manque";
  const sent = p.montre && p.montre.a_jour;
  return `<article class="co-myprop is-${F.escape(p.statut || "")}">
    <header><span class="co-ico">${sportIcon(p.sport)}</span><div><b>${F.escape(p.titre)}</b><span>${F.escape(dayLabel(p.date))}${p.sport_label ? ` · ${F.escape(p.sport_label)}` : ""}</span></div><span class="co-chips">${watchChip(p.montre)}${statusChip(p.statut)}</span></header>
    ${blocksHtml(p.blocs, vma)}
    ${p.consigne ? `<p class="co-consigne">« ${F.escape(p.consigne)} »</p>` : ""}
    <div class="inline-actions" style="margin:8px 0 0">
      ${href ? `<a class="btn btn-small" href="${href}">${icon("activity")}Ma séance : ${F.escape(p.seance.nom || "voir")}</a>` : ""}
      ${open && watch?.disponible ? `<button type="button" class="btn btn-small ${sent ? "btn-ghost" : "btn-primary"}" data-watch="${p.id}" title="${sent ? "La renvoyer (elle remplace la précédente)" : "Dans ton calendrier Garmin Connect, à sa date : ta montre la récupère à sa synchro"}">${icon("watch")}${sent ? "Renvoyer sur ma montre" : "Envoyer sur ma montre"}</button>` : ""}
      ${open ? `<a class="btn btn-small btn-ghost" href="/api/coach/seances/${p.id}.fit" download title="Fichier d'entraînement Garmin, avec tes allures, à copier par câble USB">${icon("download")}${watch?.disponible ? "Fichier .fit" : "Pour ma montre (.fit)"}</a>
        <button type="button" class="btn btn-small btn-ghost" data-fit-help>${icon("info")}Comment ?</button>` : ""}
    </div>
  </article>`;
}

/** La carte « Ta montre Garmin » : relier, ce que le coach peut faire, délier. */
function watchCard(watch, first) {
  if (!watch?.disponible) return "";
  if (!watch.relie) {
    return `<section class="coach-card co-watchcard"><h2>${icon("watch")}Ta montre Garmin</h2>
      <p>Relie une fois ton compte Garmin Connect : les séances de ${F.escape(first)} partiront ensuite sur ta montre en un clic, avec <b>tes</b> allures, à leur date dans ton calendrier Garmin.</p>
      <p class="hint">Tu te connectes chez Garmin, sur le site de Garmin, puis tu cliques sur «&nbsp;Accepter&nbsp;». Foulée ne voit jamais ton mot de passe et ne lit rien de ta montre : il ne fait qu'y déposer des séances.</p>
      <div class="inline-actions" style="margin:10px 0 0"><button type="button" class="btn btn-small" data-watch-link>${icon("watch")}Relier mon compte Garmin</button></div></section>`;
  }
  return `<section class="coach-card co-watchcard"><h2>${icon("watch")}Ta montre Garmin <span class="co-chip good">${icon("check")}reliée</span></h2>
    <p class="hint">Compte Garmin Connect relié ${F.escape(F.relative(watch.relie_le))}. «&nbsp;Envoyer sur ma montre&nbsp;» range la séance dans ton calendrier Garmin, à sa date ; synchronise ta montre pour l'y trouver.</p>
    <label class="co-check"><input type="checkbox" data-watch-coach ${watch.coach_peut_envoyer ? "checked" : ""}><span>${F.escape(first)} peut envoyer ses séances directement sur ma montre</span></label>
    <div class="inline-actions" style="margin:10px 0 0"><button type="button" class="btn btn-small btn-ghost" data-watch-unlink>${icon("close")}Délier mon compte Garmin</button></div></section>`;
}

export async function renderMyCoach(ctx) {
  const { page, me, host, toast } = ctx;
  page.innerHTML = `${ctx.head(`<h1>Mon coach</h1>`)}${ctx.tabs("coach")}<div class="co-page wide">${loading("Lecture du relais…")}</div>`;
  const data = await api.get("/api/coach/moi", null, { fresh: true });
  const coachName = data.coach?.nom || me.coach?.nom || "Ton coach";
  const first = coachName.split(" ")[0];
  const accord = data.accord_local || data.accord;
  const today = F.isoDate(new Date());
  const props = data.propositions || [];
  const upcoming = props.filter((p) => p.date >= today);
  const past = props.filter((p) => p.date < today).reverse();
  // Le coach fait partie du club de l'élève (Réglages → Coach et élèves) : le logo du club sur sa carte
  const sameClub = Boolean(ctx.info?.meme_club);
  const clubLogo = sameClub ? clubLogoURL(ctx.boot?.club_logo) : null;
  const clubName = sameClub ? (ctx.boot?.club?.nom || "") : "";

  page.innerHTML = `${ctx.head(`<h1>Mon coach</h1>`, `<span>Relais <b>${F.escape(host)}</b> · ton identifiant : <code>${F.escape(me.identifiant)}</code></span>`)}
    ${ctx.tabs("coach")}
    ${!accord ? `<section class="co-callout">${icon("lock")}<div><b>Dernière étape : choisis ce que tu partages avec ${F.escape(first)}</b>
        <span>Rien ne part vers le relais avant ton accord. Tu pourras changer d'avis à tout moment.</span></div><a class="btn btn-primary" href="#/coach/partage">${icon("check")}Choisir</a></section>` : ""}
    ${data.mois ? calendarCard("Ton calendrier", `ce que ${first} voit : 4 semaines passées, celle-ci, 4 à venir`, data.mois, {
      vma: data.vma_kmh, goals: data.objectifs || [], sessionHref: (s) => `#/coach/seance/${encodeURIComponent(s.cle)}` }) : ""}
    <div class="co-grid2">
      <div class="co-page">
        <section class="coach-card co-coachcard">${avatar(coachName, { size: "lg" })}<div><h2>${F.escape(coachName)}</h2>
            <span class="muted">${data.coach?.derniere_connexion ? `passé sur le relais ${F.escape(F.relative(data.coach.derniere_connexion))}` : "ton coach"}${clubName ? ` · ${F.escape(clubName)}` : ""}</span></div>
          ${clubLogo ? `<img class="co-club-logo" src="${clubLogo}" alt="Logo du club${clubName ? ` ${F.escape(clubName)}` : ""}" title="${F.escape(first)} fait partie de ton club${clubName ? ` : ${F.escape(clubName)}` : ""}">` : ""}
          <div class="co-actions"><a class="btn btn-small" href="#/coach/messages?fil=groupe">${icon("club")}Fil du groupe</a></div></section>
        <section class="coach-card"><h2>${icon("calendar")}Séances proposées par ${F.escape(first)} ${upcoming.length ? `<span class="co-count">${upcoming.length}</span>` : ""}</h2>
          ${upcoming.length ? upcoming.map((p) => proposal(p, data.vma_kmh, data.montre)).join("") : `<p class="co-empty">Rien de prévu pour l'instant.</p>`}
          ${upcoming.length ? `<p class="hint" style="margin:10px 0 0">Elles sont aussi dans ta vue « Calendrier », en pointillé bleu.${data.vma_kmh ? ` Allures calculées avec ta VMA (${F.dec1(data.vma_kmh)} km/h).` : " Indique ta VMA dans Réglages → Profil pour voir tes allures."}</p>` : ""}
          <div class="co-fit-help" data-fit-box hidden><b>${icon("download")}Mettre la séance sur ta montre</b>
            <ol><li>Télécharge le fichier <b>.fit</b> (bouton « Pour ma montre »). Il contient chaque bloc, avec <b>tes</b> allures en fourchette ou la zone de FC.</li>
              <li>Branche ta montre Garmin à l'ordinateur en USB et ouvre-la dans l'Explorateur de fichiers.</li>
              <li>Copie le fichier dans le dossier <code>GARMIN\\NewFiles</code> de la montre.</li>
              <li>Débranche la montre : la séance apparaît dans <b>Entraînement → Entraînements</b>.</li></ol>
            <p>${data.montre?.disponible ? "Plus simple : « Envoyer sur ma montre », sans câble." : "Pas de câble sous la main ? Recopie la séance dans Garmin Connect (Entraînement → Entraînements → Créer), bloc par bloc."}</p></div>
          ${past.length ? `<details class="co-past"><summary>Les 2 dernières semaines (${past.length})</summary>${past.map((p) => proposal(p, data.vma_kmh, data.montre)).join("")}</details>` : ""}
        </section>
      </div>
      <div class="co-page">
        <div data-watch-wait hidden></div>
        ${watchCard(data.montre, first)}
        <section class="coach-card co-minichat"><h2>${icon("chat")}Conversation avec ${F.escape(first)}</h2><div data-thread></div>
          <a class="hint" href="#/coach/messages?fil=eleve-${me.id}">Ouvrir dans Messages ›</a></section>
        <section class="coach-card"><h2>${icon("lock")}Ce que tu partages</h2>${shareList(accord)}
          ${accord ? `<p class="hint" style="margin:10px 0 0">${data.partage ? `${data.partage.seances} séance${data.partage.seances > 1 ? "s" : ""}${data.partage.traces ? ` dont ${data.partage.traces} avec tracé` : ""} chez le relais · ` : ""}${data.envoye_le ? `dernier envoi ${F.escape(F.relative(data.envoye_le))}` : "rien envoyé encore"}. Foulée envoie après chaque synchro.</p>` : ""}
          <div class="inline-actions" style="margin:12px 0 0">${accord ? `<button class="btn btn-small" type="button" data-push>${icon("sync")}Envoyer maintenant</button>` : ""}
            <a class="btn btn-small btn-ghost" href="#/coach/partage">${icon("edit")}${accord ? "Changer mes choix" : "Choisir"}</a></div></section>
      </div>
    </div>`;

  bindWatch(ctx, page, data, first);
  page.querySelectorAll("[data-fit-help]").forEach((b) => b.addEventListener("click", () => {
    const box = page.querySelector("[data-fit-box]");
    box.hidden = !box.hidden;
    if (!box.hidden) box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }));
  mountThread(page.querySelector("[data-thread]"), {
    fil: `eleve-${me.id}`, role: "eleve", style: "bubbles", toast, onRead: () => ctx.poke(),
    placeholder: `Écrire à ${first}…`, empty: `Une question sur une séance, une douleur, un empêchement ? Écris à ${first}.`,
  });
  page.querySelector("[data-push]")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const res = await api.post("/api/coach/echange");
      toast(res.envoi ? `C'est envoyé : ${res.envoi.seances} séance${res.envoi.seances > 1 ? "s" : ""} partagée${res.envoi.seances > 1 ? "s" : ""} avec ${first}.` : "À jour.");
      renderMyCoach(ctx);
    } catch (err) { toast(err.message); btn.disabled = false; }
  });
}

// ------------------------------------------------------------ la montre (Garmin)
let waiting = null; // la liaison en cours chez Garmin (une seule à la fois)

function bindWatch(ctx, page, data, first) {
  const { toast } = ctx;
  const box = page.querySelector("[data-watch-wait]");
  if (waiting) showWait(box, waiting.url, waiting.title);

  // Garmin s'ouvre dans une autre fenêtre ; on guette le retour (compte relié, séance partie)
  const waitForLink = (url, title, proposalId) => {
    waiting = { url, title, proposalId, until: Date.now() + 15 * 60 * 1000 };
    showWait(box, url, title);
    const tick = async () => {
      if (!waiting || Date.now() > waiting.until) { waiting = null; return; }
      try {
        const st = await api.get("/api/coach/garmin", null, { fresh: true });
        if (st.relie) {
          const done = waiting;
          waiting = null;
          toast(done.proposalId ? `Compte Garmin relié : « ${done.title} » est partie dans ton calendrier Garmin. Synchronise ta montre.` : "Compte Garmin relié : tes séances partiront maintenant en un clic.");
          if (location.hash.startsWith("#/coach")) renderMyCoach(ctx);
          return;
        }
      } catch { /* relais momentanément injoignable : on réessaie */ }
      setTimeout(tick, 3000);
    };
    setTimeout(tick, 3000);
  };

  // window.open tout de suite (dans le clic), sinon le navigateur bloque la fenêtre
  const openGarmin = () => {
    const win = window.open("about:blank", "_blank");
    if (win) { try { win.opener = null; win.document.title = "Garmin Connect…"; } catch { /* rien */ } }
    return win;
  };
  const go = (win, url) => { if (win && !win.closed) win.location.href = url; };

  page.querySelectorAll("[data-watch]").forEach((btn) => btn.addEventListener("click", async () => {
    const id = Number(btn.dataset.watch);
    const p = (data.propositions || []).find((x) => x.id === id);
    const win = data.montre?.relie ? null : openGarmin();
    btn.disabled = true;
    try {
      const res = await api.post(`/api/coach/seances/${id}/montre`);
      if (res.envoi) {
        win?.close();
        toast(`« ${p?.titre || "La séance"} » est dans ton calendrier Garmin pour le ${dayLabel(res.envoi.date).toLowerCase()} : synchronise ta montre.`);
        renderMyCoach(ctx);
        return;
      }
      if (res.a_relier) {
        if (res.raison) toast(res.raison);
        go(win, res.adresse);
        waitForLink(res.adresse, p?.titre || "La séance", id);
        btn.disabled = false;
      }
    } catch (err) {
      win?.close();
      toast(err.message);
      btn.disabled = false;
    }
  }));
  page.querySelector("[data-watch-link]")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const win = openGarmin();
    btn.disabled = true;
    try {
      const res = await api.post("/api/coach/garmin/relier");
      go(win, res.adresse);
      waitForLink(res.adresse, "", null);
    } catch (err) { win?.close(); toast(err.message); }
    btn.disabled = false;
  });
  page.querySelector("[data-watch-coach]")?.addEventListener("change", async (e) => {
    try {
      await api.put("/api/coach/garmin", { coach_peut_envoyer: e.target.checked });
      toast(e.target.checked ? `${first} peut envoyer ses séances sur ta montre.` : `${first} ne peut plus envoyer sur ta montre : toi seul le fais.`);
    } catch (err) { toast(err.message); e.target.checked = !e.target.checked; }
  });
  page.querySelector("[data-watch-unlink]")?.addEventListener("click", async (e) => {
    if (!window.confirm("Délier ton compte Garmin ? Foulée perd le droit d'y déposer des séances (l'autorisation est aussi retirée chez Garmin). Les séances déjà envoyées restent dans ton calendrier Garmin.")) return;
    const btn = e.currentTarget; // après un await, e.currentTarget ne vaut plus rien
    btn.disabled = true;
    try { await api.del("/api/coach/garmin"); toast("Compte Garmin délié."); renderMyCoach(ctx); }
    catch (err) { toast(err.message); btn.disabled = false; }
  });
}

function showWait(box, url, title) {
  if (!box) return;
  box.hidden = false;
  box.innerHTML = `<section class="co-callout co-watchwait"><span class="spinner" aria-hidden="true"></span><div><b>Garmin Connect s'est ouvert dans une autre fenêtre</b>
    <span>Connecte-toi chez Garmin et clique sur «&nbsp;Accepter&nbsp;»${title ? ` : «&nbsp;${F.escape(title)}&nbsp;» partira aussitôt` : ""}. Cette page se met à jour toute seule.</span></div>
    <a class="btn btn-small" href="${F.escape(url)}" target="_blank" rel="noopener">${icon("external")}Rouvrir Garmin</a></section>`;
}

export async function renderAccord(ctx) {
  const { page, me, host, toast } = ctx;
  page.innerHTML = `${ctx.head(`<h1>Ce que tu partages</h1>`)}${ctx.tabs("partage")}<div class="co-page wide">${loading()}</div>`;
  let data;
  try {
    data = await api.get("/api/coach/accord", null, { fresh: true });
  } catch (err) {
    page.querySelector(".co-page").innerHTML = fail(err.message);
    return;
  }
  const firstTime = !data.accord;
  const values = { ...data.defaut, ...(data.accord || {}) };
  const coachName = me.coach?.nom || "ton coach";

  page.innerHTML = `${ctx.head(`<h1>Ce que tu partages avec ${F.escape(coachName)}</h1>`,
    `<span>${firstTime ? "Dernière étape avant que ton coach voie tes séances : rien ne part tant que tu n'as pas validé." : "Une case décochée efface tout de suite la donnée chez le relais."}</span>`)}
    ${ctx.tabs("partage")}
    <div class="co-grid2 even">
      <section class="coach-card"><h2>${icon("check")}Partagé avec ${F.escape(coachName.split(" ")[0])}</h2>
        <div class="co-toggles">${CHOICES.map(([key, title, text, cls]) => `<label class="co-toggle ${cls || ""}">
          <input type="checkbox" data-a="${key}" ${values[key] ? "checked" : ""}><span class="co-sw" aria-hidden="true"></span><div><b>${title}</b><span>${text}</span></div></label>`).join("")}</div>
      </section>
      <div class="co-page">
        <section class="coach-card"><h2>${icon("lock")}Jamais partagé</h2>
          <div class="co-never"><span class="co-chip red">Séances venues de Strava</span><span class="co-chip red">Tes clés et mots de passe</span><span class="co-chip red">Ton historique au-delà de 4 semaines</span><span class="co-chip red">Tes autres profils</span></div>
          <p>Le relais ne garde que les 4 dernières semaines, remplacées à chaque envoi. Quitter le groupe efface aussitôt ton compte et tout ce que tu as partagé.</p></section>
        <section class="coach-card"><h2>${icon("user")}Récapitulatif</h2>
          <dl class="co-dl"><dt>Coach</dt><dd>${F.escape(coachName)}</dd><dt>Relais</dt><dd>${F.escape(host)}</dd><dt>Identifiant</dt><dd>${F.escape(me.identifiant)}</dd>
            ${data.envoye_le ? `<dt>Dernier envoi</dt><dd>${F.escape(F.relative(data.envoye_le))}</dd>` : ""}</dl>
          <div class="inline-actions" style="margin:14px 0 0"><button class="btn btn-primary" type="button" data-save>${icon("check")}${firstTime ? "Valider et partager" : "Enregistrer et envoyer"}</button>
            <a class="btn btn-ghost" href="#/coach">${firstTime ? "Plus tard" : "Annuler"}</a></div>
          <p class="hint" data-status aria-live="polite"></p></section>
      </div>
    </div>`;

  const box = (key) => page.querySelector(`[data-a="${key}"]`);
  const sync = () => {
    box("gps").disabled = !box("seances").checked;
    if (!box("seances").checked) box("gps").checked = false;
    box("masquer").disabled = !box("gps").checked;
    page.querySelectorAll(".co-toggle").forEach((l) => l.classList.toggle("off", l.querySelector("input").disabled));
  };
  page.querySelectorAll("[data-a]").forEach((b) => b.addEventListener("change", sync));
  sync();
  page.querySelector("[data-save]").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const status = page.querySelector("[data-status]");
    const accord = Object.fromEntries(CHOICES.map(([key]) => [key, box(key).checked]));
    btn.disabled = true;
    status.textContent = "Envoi au relais…";
    try {
      const res = await api.put("/api/coach/accord", accord);
      const sent = res.echange?.envoi;
      toast(sent ? `C'est fait : ${sent.seances} séance${sent.seances > 1 ? "s" : ""} partagée${sent.seances > 1 ? "s" : ""} avec ${coachName.split(" ")[0]}.` : "Choix enregistrés.");
      location.hash = "#/coach";
    } catch (err) {
      status.textContent = err.message;
      btn.disabled = false;
    }
  });
}
