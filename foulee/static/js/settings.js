// Page « Réglages » : profil et logo, utilisateurs, mon club, coureur, objectif, horaires, zones FC et d'allure,
// synchro, vues, sauvegarde ; puis l'installation (clé Garmin, dossier, Claude Desktop, mises à jour :
// voir system.js).
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { clubPanel } from "./settings-club.js";
import { profilePanel, transferPanel } from "./settings-profile.js";
import { scheduleEditor } from "./settings-schedule.js";
import { hrZonesEditor, paceZonesEditor } from "./settings-zones.js";
import { systemSections, wireSystem } from "./system.js";
import { accessPanel, usersPanel } from "./users.js";

const SEMI = 21.0975;
const DISTANCES = [["5", "5 km"], ["10", "10 km"], [String(SEMI), "Semi-marathon"], ["42.195", "Marathon"], ["autre", "Autre distance"]];

function hms(text) {
  const parts = String(text || "").split(":").map(Number);
  if (parts.some((n) => !Number.isFinite(n))) return null;
  while (parts.length < 3) parts.unshift(0);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

export function renderSettings(page, boot, { onSaved, onProfile, refreshBoot, toast, resetViews, startSync, section = null }) {
  const s = structuredClone(boot.reglages);
  const goal = s.objectif || {};
  const preset = DISTANCES.find(([v]) => Number(v) === Number(goal.distance_km));
  const hr = boot.profil_fc || {};
  const principal = boot.utilisateur?.principal !== false;
  const users = boot.utilisateurs || [];
  const me = users.find((u) => u.courant);
  page.innerHTML = `
    <header class="head"><div><h1>Réglages</h1>
      <div class="head-sub"><span>${users.length > 1 && me ? `Profil de <b>${F.escape(me.prenom)}</b> : ces réglages ne concernent que ce profil. ` : ""}Ils servent aux calculs de l'interface et de Claude.</span></div></div></header>
    <nav class="settings-jump" aria-label="Rubriques des réglages"></nav>
    <div class="settings settings-system">
      <section data-section="profil">
        <h2>Profil et logo</h2>
        <p class="intro">Ton prénom et ta photo s'affichent sur l'accueil ; le logo choisi remplace celui de Foulée dans la colonne et l'onglet du navigateur. Chaque choix s'enregistre tout de suite.</p>
        <div data-profile></div>
        <div class="access" data-access></div>
      </section>
      ${principal ? `<section data-section="utilisateurs">
        <h2>Gestion des utilisateurs</h2>
        <p class="intro">Un profil par personne : chacun a ses données Garmin (avec sa propre clé), ses vues, ses réglages et sa synchro. Tu es l'utilisateur principal : toi seul ajoutes ou retires des profils et règles l'installation (mises à jour, dossier des données${boot.machine === "serveur" ? ", accès par le réseau local" : ""}…). On passe d'un profil à l'autre avec son prénom, en haut à droite de l'Accueil.</p>
        <div data-users></div>
      </section>` : ""}
      <section data-section="club">
        <h2>Mon club</h2>
        <p class="intro">Licencié dans un club d'athlétisme ? Coche la case : Foulée t'ajoute une vue « Mon club » avec ses coordonnées, ta licence et, en un clic, le classement du club sur le site de la FFA.</p>
        <div data-club></div>
      </section>
    </div>
    <form class="settings" id="settings-form" novalidate>
      <section data-section="coureur">
        <h2>Profil de coureur</h2>
        <p class="intro">La VMA cale tes allures et tes fractions rapides. Laisse les fréquences cardiaques vides pour utiliser tes zones Garmin et ta FC de repos mesurée.</p>
        <div class="form-grid">
          <label class="field"><span>VMA (km/h)</span><input type="number" step="0.1" min="8" max="30" name="vma_kmh" value="${F.escape(s.vma_kmh)}"></label>
          <label class="field"><span>FC max (bpm)</span><input type="number" min="120" max="230" name="fc_max" value="${F.escape(s.fc_max ?? "")}" placeholder="${F.int(hr.max)} (${F.escape(hr.source_max || "auto")})"></label>
          <label class="field"><span>FC de repos (bpm)</span><input type="number" min="30" max="100" name="fc_repos" value="${F.escape(s.fc_repos ?? "")}" placeholder="${F.int(hr.rest)} (${F.escape(hr.source_rest || "auto")})"></label>
          <label class="field"><span>Formule du TRIMP</span><select name="sexe"><option value="H" ${s.sexe !== "F" ? "selected" : ""}>Homme (coefficient 1,92)</option><option value="F" ${s.sexe === "F" ? "selected" : ""}>Femme (coefficient 1,67)</option></select></label>
        </div>
      </section>

      <section data-section="objectif">
        <h2>Objectif course</h2>
        <p class="intro">Il alimente le compte à rebours, l'allure cible et la tuile des fractions rapides.</p>
        <div class="form-grid">
          <label class="field"><span>Nom</span><input type="text" name="goal_nom" value="${F.escape(goal.nom || "")}"></label>
          <label class="field"><span>Date</span><input type="date" name="goal_date" value="${F.escape(goal.date || "")}"></label>
          <label class="field"><span>Distance</span><select name="goal_preset">${DISTANCES.map(([v, l]) => `<option value="${v}" ${(preset ? preset[0] : "autre") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          <label class="field" data-custom-distance ${preset ? "hidden" : ""}><span>Distance (km)</span><input type="number" step="0.001" min="0.4" name="goal_distance" value="${F.escape(goal.distance_km ?? "")}"></label>
          <label class="field"><span>Temps visé (h:mm:ss)</span><input type="text" name="goal_temps" value="${F.escape(goal.temps_cible || "")}" placeholder="1:25:00" pattern="^\\d{1,2}(:\\d{2}){1,2}$"></label>
        </div>
        <p class="computed" data-goal-computed></p>
      </section>

      <section data-section="horaires">
        <h2>Horaires de travail</h2>
        <p class="intro">Foulée s'en sert pour comparer ta récupération d'un poste à l'autre, colorer tes courbes et t'afficher ton poste du jour.</p>
        <div data-schedule></div>
      </section>

      <section data-section="zones-fc">
        <h2>Zones de fréquence cardiaque</h2>
        <p class="intro">Elles comptent ton temps par zone dans chaque séance. Tire les séparations de la barre pour les ajuster.</p>
        <div data-hr-zones></div>
      </section>

      <section data-section="zones">
        <h2>Zones d'allure et fractions</h2>
        <p class="intro">Cinq zones d'allure pour la course à pied. Le seuil des fractions décide quels tours comptent comme rapides.</p>
        <div data-pace-zones></div>
        <div class="form-grid" style="margin-top:12px">
          <label class="field"><span>Fractions rapides (% VMA)</span><input type="number" min="60" max="120" step="1" name="fractions" value="${F.escape(s.fractions_seuil_pct_vma)}"></label>
        </div>
        <p class="computed" data-fractions></p>
      </section>

      <section data-section="synchro">
        <h2>Synchro et calculs</h2>
        <div class="form-grid">
          <label class="field"><span>Fichiers FIT téléchargés d'office</span><select name="fit_auto_jours">${[[0, "Aucun (à la demande)"], [90, "3 derniers mois"], [180, "6 derniers mois"], [365, "Dernière année"], [730, "Deux dernières années"]].map(([v, l]) => `<option value="${v}" ${Number(s.fit_auto_jours) === v ? "selected" : ""}>${l}</option>`).join("")}</select>
            <span class="hint">Les plus anciens se téléchargent quand tu ouvres la séance.</span></label>
          <label class="field"><span>Charge d'une séance</span><select name="charge_source"><option value="garmin" ${s.charge_source !== "trimp" ? "selected" : ""}>Charge Garmin (TRIMP si absente)</option><option value="trimp" ${s.charge_source === "trimp" ? "selected" : ""}>TRIMP calculé par Foulée</option></select></label>
          <label class="field"><span>Fond de carte</span><select name="carte_fond">${[["osm", "OpenStreetMap"], ["ign", "Plan IGN"], ["aucun", "Aucun (tracé seul, rien ne sort du PC)"]].map(([v, l]) => `<option value="${v}" ${s.carte_fond === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        </div>
        ${syncRhythm(s, boot)}
      </section>

      <section data-section="vues">
        <h2>Vues</h2>
        <p class="intro">Restaure les six vues d'origine (dont l'accueil) si tu les as trop modifiées. Tes vues personnelles sont conservées.</p>
        <button class="btn" type="button" data-reset-views>${icon("reset")}Restaurer les vues d'origine</button>
      </section>

      <div class="settings-foot"><button class="btn btn-primary" type="submit">${icon("check")}Enregistrer les réglages</button><span class="hint" data-status></span></div>
    </form>
    <div class="settings settings-system" id="settings-system">
      <section data-section="sauvegarde">
        <h2>Sauvegarde des réglages</h2>
        <p class="intro">Chaque installation (ce PC, ton serveur) garde ses propres réglages. Exporte-les dans un fichier pour les reprendre ailleurs, ou les mettre de côté.</p>
        <div data-transfer></div>
      </section>
      ${systemSections(boot)}
      <section data-section="apropos">
        <h2>À propos</h2>
        <dl class="about">
          <dt>Version</dt><dd>Foulée ${F.escape(boot.version)}${boot.demo ? " (mode démo)" : ""}</dd>
          <dt>Installation</dt><dd>${{ exe: "application Windows (Foulee-Setup.exe)", serveur: "serveur", dev: "dossier décompressé (installation manuelle)" }[boot.installation] || F.escape(boot.installation)}</dd>
          <dt>Clé API Garmin</dt><dd>${boot.demo ? "Inutile en mode démo" : boot.cle ? (boot.machine === "serveur" ? "Enregistrée sur le serveur" : "Enregistrée sur ce PC") : "Absente : ajoute-la dans la rubrique « Clé API Garmin »"}</dd>
          <dt>Données</dt><dd>${F.escape(boot.dossier_donnees || "")}</dd>
          <dt>Contenu</dt><dd>${F.int(boot.volumes.activities)} séances, ${F.int(boot.volumes.daily)} valeurs quotidiennes, ${F.int(boot.volumes.streams)} séances avec courbes</dd>
          <dt>Depuis le</dt><dd>${boot.premiere_date ? F.dateLong(boot.premiere_date, { year: true }) : "–"}</dd>
        </dl>
        <div class="inline-actions">
          <a class="btn" href="#/aide">${icon("help")}Aide et questions fréquentes</a>
          <a class="btn" href="#/retours">${icon("feedback")}Un bug, une idée ? Parles-en !</a>
        </div>
        ${boot.acces === "local" && !boot.demo ? `<p class="hint"><a href="#/bienvenue">Revoir la page d'accueil</a> (clé, premier import, Claude Desktop).</p>` : ""}
      </section>
    </div>`;

  const form = page.querySelector("#settings-form");
  const val = (name) => form.elements[name]?.value;
  const num = (name) => { const v = val(name); return v === "" || v === undefined ? null : Number(v); };
  const vma = () => num("vma_kmh") || 16;
  const profile = () => ({ max: num("fc_max") || hr.max || 190, rest: num("fc_repos") || hr.rest || 50 });

  profilePanel(page.querySelector("[data-profile]"), boot, { toast, onProfile });
  accessPanel(page.querySelector("[data-access]"), boot, { toast, onChange: () => refreshBoot() });
  if (principal) usersPanel(page.querySelector("[data-users]"), boot, { toast, onChange: () => refreshBoot() });
  clubPanel(page.querySelector("[data-club]"), boot, { toast, onChange: () => refreshBoot() });
  const schedule = scheduleEditor(page.querySelector("[data-schedule]"), s.horaires);
  const hrZones = hrZonesEditor(page.querySelector("[data-hr-zones]"), boot, profile);
  const paceZones = paceZonesEditor(page.querySelector("[data-pace-zones]"), boot, vma);
  transferPanel(page.querySelector("[data-transfer]"), boot, {
    toast,
    onImported: () => refreshBoot("sauvegarde"),
  });

  const refresh = (event) => {
    const distance = val("goal_preset") === "autre" ? num("goal_distance") : Number(val("goal_preset"));
    const secs = hms(val("goal_temps"));
    const goalOut = form.querySelector("[data-goal-computed]");
    if (distance && secs) {
      const speed = (distance * 1000) / secs;
      goalOut.innerHTML = `Allure cible <b>${F.pace(speed)} /km</b>, soit <b>${F.dec1(speed * 3.6)} km/h</b> et <b>${Math.round((speed * 3.6 / vma()) * 100)} %</b> de ta VMA.`;
    } else {
      goalOut.textContent = "Renseigne une distance et un temps visé (h:mm:ss) pour voir l'allure cible.";
    }
    form.querySelector("[data-fractions]").innerHTML = `Fractions rapides : plus rapides que <b>${F.pace((vma() * (num("fractions") || 85)) / 100 / 3.6)} /km</b>.`;
    form.querySelector("[data-custom-distance]").hidden = val("goal_preset") !== "autre";
    const name = event?.target?.name;
    if (name === "fc_max" || name === "fc_repos") hrZones.refresh();
    if (name === "vma_kmh") paceZones.refresh();
  };
  form.addEventListener("input", refresh);
  refresh();

  form.querySelector("[data-reset-views]").addEventListener("click", resetViews);
  wireSyncRhythm(form);
  // Withings connecté ou déconnecté : la colonne (vue « Withings ») et le bandeau suivent, la page reste en place
  wireSystem(page.querySelector("#settings-system"), boot, { toast, startSync, onWithings: () => refreshBoot() });
  buildJumps(page);
  if (section) {
    const target = page.querySelector(`[data-section="${CSS.escape(section)}"]`);
    if (target) keepInView(page, target);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = form.querySelector("[data-status]");
    const secs = hms(val("goal_temps"));
    if (val("goal_temps") && !secs) { status.textContent = "Temps visé illisible : utilise h:mm:ss, par exemple 1:25:00."; return; }
    const pace = paceZones.value();
    const payload = {
      vma_kmh: vma(),
      fc_max: num("fc_max"),
      fc_repos: num("fc_repos"),
      sexe: val("sexe"),
      objectif: {
        nom: val("goal_nom"), date: val("goal_date"),
        distance_km: val("goal_preset") === "autre" ? num("goal_distance") : Number(val("goal_preset")),
        temps_cible: val("goal_temps"),
      },
      horaires: schedule.value(),
      zones_fc: hrZones.value(),
      zones_allure: pace,
      fractions_seuil_pct_vma: num("fractions") || 85,
      fit_auto_jours: Number(val("fit_auto_jours")),
      synchro_auto: syncRhythmValue(form, s),
      charge_source: val("charge_source"),
      carte_fond: val("carte_fond"),
    };
    if (pace.methode === "pct_vma" && pace.pct) payload.zones_allure_pct_vma = pace.pct;  // réglage historique
    status.textContent = "Enregistrement…";
    try {
      const res = await api.put("/api/settings", payload);
      status.textContent = "";
      toast(res.recalcul ? "Réglages enregistrés. Zones et charge sont en cours de recalcul." : "Réglages enregistrés.");
      onSaved(res);
    } catch (err) {
      status.textContent = `Enregistrement impossible : ${err.message}`;
      status.classList.add("error");
    }
  });
}

// ---------------------------------------------------------------- rythme de la synchro automatique
// De 30 minutes à 12 heures (bornes vérifiées par le serveur, voir sync.py), 3 heures conseillées.
const RHYTHMS = [30, 60, 120, 180, 240, 360, 480, 720];
const DEFAULT_RHYTHM = 180;

/** « 30 minutes », « 1 heure », « 8 heures », « 1 h 30 ». */
function span(minutes) {
  if (minutes < 60) return `${minutes} minutes`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} heure${h > 1 ? "s" : ""}`;
}
const every = (minutes) => (minutes === 60 ? "toutes les heures" : `toutes les ${span(minutes)}`);
const cap = (text) => text.charAt(0).toUpperCase() + text.slice(1);

function rhythmSelect(name, label, minutes) {
  const chosen = Math.min(720, Math.max(30, Math.round(Number(minutes) || DEFAULT_RHYTHM)));
  // un délai réglé ailleurs (par Claude : 90 minutes…) reste proposé, pour ne pas être remplacé à l'enregistrement
  const values = [...new Set([...RHYTHMS, chosen])].sort((a, b) => a - b);
  return `<label class="field"><span>${label}</span><select name="${name}" data-rhythm>${values.map((v) =>
    `<option value="${v}" ${v === chosen ? "selected" : ""}>${cap(every(v))}${v === DEFAULT_RHYTHM ? " (conseillé)" : ""}</option>`).join("")}</select></label>`;
}

/** Un délai par source branchée (Garmin, Withings, Strava), avec le conseil des 3 heures. */
function syncRhythm(s, boot) {
  const chosen = s.synchro_auto || {};
  const where = boot.machine === "serveur" ? "sur le serveur, jour et nuit" : "sur ce PC, tant que Foulée est ouvert (son icône près de l'horloge)";
  return `<h3>Synchro automatique</h3>
    <p class="intro">Foulée récupère tout seul tes nouvelles données, au rythme choisi pour chaque source : ${where}.</p>
    <div class="form-grid rhythm-grid">
      ${boot.cle || !(boot.withings?.connecte || boot.strava?.connecte) ? rhythmSelect("synchro_garmin", "Garmin", chosen.garmin) : ""}
      ${boot.withings?.connecte ? rhythmSelect("synchro_withings", "Withings", chosen.withings) : ""}
      ${boot.strava?.connecte && !boot.demo ? rhythmSelect("synchro_strava", "Strava", chosen.strava) : ""}
      ${boot.calendrier?.lie && !boot.demo ? rhythmSelect("synchro_calendrier", "Calendrier", chosen.calendrier) : ""}
    </div>
    <p class="computed info">${icon("info")}<span><b>3 heures, c'est un bon compromis</b> : tes séances, tes nuits et tes pesées arrivent dans la journée sans solliciter Garmin et Withings pour rien. Plus rapproché, Foulée redemande sans cesse des données qui n'ont pas bougé. Besoin d'une donnée tout de suite (la séance de ce matin) ? «&nbsp;Synchroniser&nbsp;», dans la colonne de gauche, la récupère à l'instant.</span></p>
    <p class="computed" data-rhythm-note hidden></p>`;
}

function syncRhythmValue(form, s) {
  const out = { ...(s.synchro_auto || {}) };
  for (const name of ["garmin", "withings", "strava", "calendrier"]) {
    const value = form.elements[`synchro_${name}`]?.value;
    if (value) out[name] = Number(value);
  }
  return out;
}

/** Sous le choix : ce que coûte un rythme serré (des demandes pour rien) ou lâche (des données en retard). */
function wireSyncRhythm(form) {
  const note = form.querySelector("[data-rhythm-note]");
  if (!note) return;
  const update = () => {
    const values = [...form.querySelectorAll("[data-rhythm]")].map((el) => Number(el.value));
    const fast = Math.min(...values);
    const slow = Math.max(...values);
    let text = "";
    if (fast < DEFAULT_RHYTHM) {
      text = `${icon("warning")}<span>${cap(every(fast))} : environ ${Math.round(1440 / fast)} synchros par jour, la plupart sans rien de nouveau, et les services peuvent limiter les demandes trop fréquentes. Pour une donnée précise, «&nbsp;Synchroniser&nbsp;» au bon moment fait mieux.</span>`;
    } else if (slow > 360) {
      text = `${icon("info")}<span>${cap(every(slow))} : une nouvelle séance ou une pesée peut mettre jusqu'à ${span(slow)} à arriver dans Foulée.</span>`;
    }
    note.innerHTML = text;
    note.className = `computed ${fast < DEFAULT_RHYTHM ? "warn" : "info"}`;
    note.hidden = !text;
  };
  form.querySelectorAll("[data-rhythm]").forEach((el) => el.addEventListener("change", update));
  update();
}

/**
 * Amène une rubrique à l'écran (lien « …?section=maj ») et l'y garde pendant que les panneaux du dessus
 * finissent de se charger (clé, dossier, Claude…), tant que l'utilisateur ne fait pas défiler lui-même.
 */
function keepInView(page, target) {
  const events = ["wheel", "touchmove", "keydown", "mousedown"];
  const stop = () => {
    observer.disconnect();
    events.forEach((name) => removeEventListener(name, stop));
  };
  const jump = () => (target.isConnected ? target.scrollIntoView({ block: "start" }) : stop());
  const observer = new ResizeObserver(() => requestAnimationFrame(jump));
  observer.observe(page);
  events.forEach((name) => addEventListener(name, stop, { passive: true }));
  setTimeout(stop, 4000);
}

// =============================================================== sommaire
const JUMPS = [["profil", "Profil"], ["utilisateurs", "Utilisateurs"], ["club", "Club"], ["coureur", "Coureur"], ["objectif", "Objectif"], ["horaires", "Horaires"],
  ["zones-fc", "Zones FC"], ["zones", "Allures"], ["synchro", "Synchro"], ["sauvegarde", "Sauvegarde"], ["cle", "Clé Garmin"], ["withings", "Withings"], ["strava", "Strava"],
  ["calendrier", "Calendrier"], ["coach", "Coach"],
  ["dossier", "Données"], ["claude", "Claude"], ["app", "Application"], ["lan", "Réseau local"], ["maj", "Mises à jour"],
  ["installation", "Installation"], ["apropos", "À propos"]];

function buildJumps(page) {
  const nav = page.querySelector(".settings-jump");
  const present = JUMPS.filter(([name]) => page.querySelector(`[data-section="${name}"]`));
  nav.innerHTML = present.map(([name, label]) => `<button type="button" data-jump="${name}">${label}</button>`).join("");
  nav.addEventListener("click", (event) => {
    const name = event.target.closest("[data-jump]")?.dataset.jump;
    if (name) page.querySelector(`[data-section="${name}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}
