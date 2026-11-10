// Page « Réglages » : profil coureur, objectif, postes, zones, synchro, carte.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const SEMI = 21.0975;
const DISTANCES = [["5", "5 km"], ["10", "10 km"], [String(SEMI), "Semi-marathon"], ["42.195", "Marathon"], ["autre", "Autre distance"]];

function hms(text) {
  const parts = String(text || "").split(":").map(Number);
  if (parts.some((n) => !Number.isFinite(n))) return null;
  while (parts.length < 3) parts.unshift(0);
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

export function renderSettings(page, boot, { onSaved, toast, resetViews }) {
  const s = structuredClone(boot.reglages);
  const goal = s.objectif || {};
  const postes = s.postes || {};
  const preset = DISTANCES.find(([v]) => Number(v) === Number(goal.distance_km));
  const hr = boot.profil_fc || {};
  page.innerHTML = `
    <header class="head"><div><h1>Réglages</h1>
      <div class="head-sub">Ils servent aux calculs de l'interface et de Claude.</div></div></header>
    <form class="settings" id="settings-form" novalidate>
      <section>
        <h2>Profil de coureur</h2>
        <p class="intro">La VMA cale tes zones d'allure et tes fractions rapides. Laisse les fréquences cardiaques vides pour utiliser tes zones Garmin et ta FC de repos mesurée.</p>
        <div class="form-grid">
          <label class="field"><span>VMA (km/h)</span><input type="number" step="0.1" min="8" max="30" name="vma_kmh" value="${F.escape(s.vma_kmh)}"></label>
          <label class="field"><span>FC max (bpm)</span><input type="number" min="120" max="230" name="fc_max" value="${F.escape(s.fc_max ?? "")}" placeholder="${F.int(hr.max)} (${F.escape(hr.source_max || "auto")})"></label>
          <label class="field"><span>FC de repos (bpm)</span><input type="number" min="30" max="100" name="fc_repos" value="${F.escape(s.fc_repos ?? "")}" placeholder="${F.int(hr.rest)} (${F.escape(hr.source_rest || "auto")})"></label>
          <label class="field"><span>Formule du TRIMP</span><select name="sexe"><option value="H" ${s.sexe !== "F" ? "selected" : ""}>Homme (coefficient 1,92)</option><option value="F" ${s.sexe === "F" ? "selected" : ""}>Femme (coefficient 1,67)</option></select></label>
        </div>
      </section>

      <section>
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

      <section>
        <h2>Postes alternés</h2>
        <p class="intro">Foulée colore tes jours selon la parité de la semaine ISO, pour comparer semaines du matin et semaines du soir. Exclus tes semaines de congés pour ne pas fausser la comparaison.</p>
        <label class="check"><input type="checkbox" name="postes_actif" ${postes.actif !== false ? "checked" : ""}>Comparer mes postes</label>
        <div class="form-grid">
          <label class="field"><span>Semaines impaires</span><select name="postes_impaires"><option value="matin" ${postes.impaires !== "soir" ? "selected" : ""}>Poste du matin</option><option value="soir" ${postes.impaires === "soir" ? "selected" : ""}>Poste du soir</option></select></label>
          <label class="field"><span>Semaines à exclure</span><input type="text" name="postes_exclues" value="${F.escape((postes.semaines_exclues || []).join(", "))}" placeholder="2026-W32, 2026-W33"></label>
        </div>
        <label class="check"><input type="checkbox" name="postes_ouvres" ${postes.jours_ouvres !== false ? "checked" : ""}>Ne comparer que les jours ouvrés (lundi à vendredi)</label>
        <p class="computed" data-week-now></p>
      </section>

      <section>
        <h2>Zones d'allure et fractions</h2>
        <p class="intro">Les quatre seuils découpent tes allures en cinq zones, en pourcentage de VMA. Le seuil des fractions décide quels tours comptent comme rapides.</p>
        <div class="form-grid" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr))">
          ${(s.zones_allure_pct_vma || [70, 80, 88, 95]).map((v, i) => `<label class="field"><span>Seuil ${i + 1} (% VMA)</span><input type="number" min="40" max="130" step="1" name="zone_${i}" value="${v}"></label>`).join("")}
          <label class="field"><span>Fractions rapides (% VMA)</span><input type="number" min="60" max="120" step="1" name="fractions" value="${F.escape(s.fractions_seuil_pct_vma)}"></label>
        </div>
        <p class="computed" data-zones-computed></p>
      </section>

      <section>
        <h2>Synchro et calculs</h2>
        <div class="form-grid">
          <label class="field"><span>Fichiers FIT téléchargés d'office</span><select name="fit_auto_jours">${[[0, "Aucun (à la demande)"], [90, "3 derniers mois"], [180, "6 derniers mois"], [365, "Dernière année"], [730, "Deux dernières années"]].map(([v, l]) => `<option value="${v}" ${Number(s.fit_auto_jours) === v ? "selected" : ""}>${l}</option>`).join("")}</select>
            <span class="hint">Les plus anciens se téléchargent quand tu ouvres la séance.</span></label>
          <label class="field"><span>Charge d'une séance</span><select name="charge_source"><option value="garmin" ${s.charge_source !== "trimp" ? "selected" : ""}>Charge Garmin (TRIMP si absente)</option><option value="trimp" ${s.charge_source === "trimp" ? "selected" : ""}>TRIMP calculé par Foulée</option></select></label>
          <label class="field"><span>Fond de carte</span><select name="carte_fond">${[["osm", "OpenStreetMap"], ["ign", "Plan IGN"], ["aucun", "Aucun (tracé seul, rien ne sort du PC)"]].map(([v, l]) => `<option value="${v}" ${s.carte_fond === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        </div>
      </section>

      <section>
        <h2>Vues</h2>
        <p class="intro">Restaure les cinq vues d'origine si tu les as trop modifiées. Tes vues personnelles sont conservées.</p>
        <button class="btn" type="button" data-reset-views>${icon("reset")}Restaurer les vues d'origine</button>
      </section>

      <section>
        <h2>À propos</h2>
        <dl class="about">
          <dt>Version</dt><dd>Foulée ${F.escape(boot.version)}${boot.demo ? " (mode démo)" : ""}</dd>
          <dt>Clé API Garmin</dt><dd>${boot.demo ? "Inutile en mode démo" : boot.cle ? "Enregistrée sur ce PC" : "Absente : lance « foulee setup » dans un terminal"}</dd>
          <dt>Données</dt><dd>${F.escape(boot.dossier_donnees || "")}</dd>
          <dt>Contenu</dt><dd>${F.int(boot.volumes.activities)} séances, ${F.int(boot.volumes.daily)} valeurs quotidiennes, ${F.int(boot.volumes.streams)} séances avec courbes</dd>
          <dt>Depuis le</dt><dd>${boot.premiere_date ? F.dateLong(boot.premiere_date, { year: true }) : "–"}</dd>
        </dl>
      </section>

      <div class="settings-foot"><button class="btn btn-primary" type="submit">${icon("check")}Enregistrer les réglages</button><span class="hint" data-status></span></div>
    </form>`;

  const form = page.querySelector("#settings-form");
  const val = (name) => form.elements[name]?.value;
  const num = (name) => { const v = val(name); return v === "" || v === undefined ? null : Number(v); };

  const refresh = () => {
    const vma = num("vma_kmh") || 16;
    const distance = val("goal_preset") === "autre" ? num("goal_distance") : Number(val("goal_preset"));
    const secs = hms(val("goal_temps"));
    const goalOut = form.querySelector("[data-goal-computed]");
    if (distance && secs) {
      const speed = (distance * 1000) / secs;
      goalOut.innerHTML = `Allure cible <b>${F.pace(speed)} /km</b>, soit <b>${F.dec1(speed * 3.6)} km/h</b> et <b>${Math.round((speed * 3.6 / vma) * 100)} %</b> de ta VMA.`;
    } else {
      goalOut.textContent = "Renseigne une distance et un temps visé (h:mm:ss) pour voir l'allure cible.";
    }
    const pcts = [0, 1, 2, 3].map((i) => num(`zone_${i}`));
    const speeds = pcts.map((p) => (vma * p) / 100 / 3.6);
    const names = ["Récup / EF", "Endurance active", "Seuil / semi", "Allure 10 km", "VMA"];
    const bounds = [`plus lent que ${F.pace(speeds[0])}`, ...[0, 1, 2].map((i) => `${F.pace(speeds[i])} à ${F.pace(speeds[i + 1])}`), `plus rapide que ${F.pace(speeds[3])}`];
    form.querySelector("[data-zones-computed]").innerHTML = names.map((n, i) => `${n} : <b>${bounds[i]}</b>`).join(" ; ") +
      `. Fractions rapides : plus rapide que <b>${F.pace((vma * (num("fractions") || 85)) / 100 / 3.6)} /km</b>.`;
    const now = new Date();
    const { week } = F.isoWeek(now);
    const label = (week % 2 === 1) === (val("postes_impaires") === "matin") ? "du matin" : "du soir";
    form.querySelector("[data-week-now]").innerHTML = `Cette semaine (S${week}, ${week % 2 ? "impaire" : "paire"}) compte comme semaine <b>${label}</b>.`;
    form.querySelector("[data-custom-distance]").hidden = val("goal_preset") !== "autre";
  };
  form.addEventListener("input", refresh);
  refresh();

  form.querySelector("[data-reset-views]").addEventListener("click", resetViews);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = form.querySelector("[data-status]");
    const exclues = (val("postes_exclues") || "").split(/[,;\s]+/).map((w) => w.trim().toUpperCase()).filter(Boolean);
    const bad = exclues.filter((w) => !/^\d{4}-W\d{2}$/.test(w));
    if (bad.length) { status.textContent = `Semaine illisible : ${bad.join(", ")} (format attendu : 2026-W32).`; return; }
    const secs = hms(val("goal_temps"));
    if (val("goal_temps") && !secs) { status.textContent = "Temps visé illisible : utilise h:mm:ss, par exemple 1:25:00."; return; }
    const impaires = val("postes_impaires");
    const payload = {
      vma_kmh: num("vma_kmh") || 16,
      fc_max: num("fc_max"),
      fc_repos: num("fc_repos"),
      sexe: val("sexe"),
      objectif: {
        nom: val("goal_nom"), date: val("goal_date"),
        distance_km: val("goal_preset") === "autre" ? num("goal_distance") : Number(val("goal_preset")),
        temps_cible: val("goal_temps"),
      },
      postes: {
        actif: form.elements.postes_actif.checked, impaires, paires: impaires === "matin" ? "soir" : "matin",
        jours_ouvres: form.elements.postes_ouvres.checked, semaines_exclues: exclues,
      },
      zones_allure_pct_vma: [0, 1, 2, 3].map((i) => num(`zone_${i}`)).sort((a, b) => a - b),
      fractions_seuil_pct_vma: num("fractions") || 85,
      fit_auto_jours: Number(val("fit_auto_jours")),
      charge_source: val("charge_source"),
      carte_fond: val("carte_fond"),
    };
    status.textContent = "Enregistrement…";
    try {
      const res = await api.put("/api/settings", payload);
      status.textContent = "";
      toast(res.recalcul ? "Réglages enregistrés. Zones et charge sont en cours de recalcul." : "Réglages enregistrés.");
      onSaved(res.reglages);
    } catch (err) {
      status.textContent = `Enregistrement impossible : ${err.message}`;
    }
  });
}
