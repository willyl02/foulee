// Côté élève : « Mon coach » (ses séances proposées, la conversation, ce que je partage) et l'écran de l'accord,
// case par case, sans lequel rien ne part vers le relais.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { avatar, blocksHtml, dayLabel, fail, loading, mountThread, statusChip, sportIcon } from "./coach-ui.js";

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

function proposal(p, vma) {
  const href = p.seance ? `#/coach/seance/${encodeURIComponent(p.seance.cle)}` : "";
  return `<article class="co-myprop is-${F.escape(p.statut || "")}">
    <header><span class="co-ico">${sportIcon(p.sport)}</span><div><b>${F.escape(p.titre)}</b><span>${F.escape(dayLabel(p.date))}${p.sport_label ? ` · ${F.escape(p.sport_label)}` : ""}</span></div>${statusChip(p.statut)}</header>
    ${blocksHtml(p.blocs, vma)}
    ${p.consigne ? `<p class="co-consigne">« ${F.escape(p.consigne)} »</p>` : ""}
    ${href ? `<div class="inline-actions" style="margin:8px 0 0"><a class="btn btn-small" href="${href}">${icon("activity")}Ma séance : ${F.escape(p.seance.nom || "voir")}</a></div>` : ""}
  </article>`;
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

  page.innerHTML = `${ctx.head(`<h1>Mon coach</h1>`, `<span>Relais <b>${F.escape(host)}</b> · ton identifiant : <code>${F.escape(me.identifiant)}</code></span>`)}
    ${ctx.tabs("coach")}
    ${!accord ? `<section class="co-callout">${icon("lock")}<div><b>Dernière étape : choisis ce que tu partages avec ${F.escape(first)}</b>
        <span>Rien ne part vers le relais avant ton accord. Tu pourras changer d'avis à tout moment.</span></div><a class="btn btn-primary" href="#/coach/partage">${icon("check")}Choisir</a></section>` : ""}
    <div class="co-grid2">
      <div class="co-page">
        <section class="coach-card co-coachcard">${avatar(coachName, { size: "lg" })}<div><h2>${F.escape(coachName)}</h2>
            <span class="muted">${data.coach?.derniere_connexion ? `passé sur le relais ${F.escape(F.relative(data.coach.derniere_connexion))}` : "ton coach"}</span></div>
          <div class="co-actions"><a class="btn btn-small" href="#/coach/messages?fil=groupe">${icon("club")}Fil du groupe</a></div></section>
        <section class="coach-card"><h2>${icon("calendar")}Séances proposées par ${F.escape(first)} ${upcoming.length ? `<span class="co-count">${upcoming.length}</span>` : ""}</h2>
          ${upcoming.length ? upcoming.map((p) => proposal(p, data.vma_kmh)).join("") : `<p class="co-empty">Rien de prévu pour l'instant.</p>`}
          ${upcoming.length ? `<p class="hint" style="margin:10px 0 0">Elles sont aussi dans ta vue « Calendrier », en pointillé bleu.${data.vma_kmh ? ` Allures calculées avec ta VMA (${F.dec1(data.vma_kmh)} km/h).` : " Indique ta VMA dans Réglages → Profil pour voir tes allures."}</p>` : ""}
          ${past.length ? `<details class="co-past"><summary>Les 2 dernières semaines (${past.length})</summary>${past.map((p) => proposal(p, data.vma_kmh)).join("")}</details>` : ""}
        </section>
      </div>
      <div class="co-page">
        <section class="coach-card co-minichat"><h2>${icon("chat")}Conversation avec ${F.escape(first)}</h2><div data-thread></div>
          <a class="hint" href="#/coach/messages?fil=eleve-${me.id}">Ouvrir dans Messages ›</a></section>
        <section class="coach-card"><h2>${icon("lock")}Ce que tu partages</h2>${shareList(accord)}
          ${accord ? `<p class="hint" style="margin:10px 0 0">${data.partage ? `${data.partage.seances} séance${data.partage.seances > 1 ? "s" : ""}${data.partage.traces ? ` dont ${data.partage.traces} avec tracé` : ""} chez le relais · ` : ""}${data.envoye_le ? `dernier envoi ${F.escape(F.relative(data.envoye_le))}` : "rien envoyé encore"}. Foulée envoie après chaque synchro.</p>` : ""}
          <div class="inline-actions" style="margin:12px 0 0">${accord ? `<button class="btn btn-small" type="button" data-push>${icon("sync")}Envoyer maintenant</button>` : ""}
            <a class="btn btn-small btn-ghost" href="#/coach/partage">${icon("edit")}${accord ? "Changer mes choix" : "Choisir"}</a></div></section>
      </div>
    </div>`;

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
