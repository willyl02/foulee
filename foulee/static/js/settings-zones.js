// Réglages → zones FC et zones d'allure : méthode (Garmin, % FC max, % FC de réserve, % du seuil,
// bornes à la main façon Strava), valeurs, et une barre à cinq couleurs dont on tire les séparations.
// Les couleurs des zones (Garmin par défaut, bleus ou à son goût) se règlent sous les zones FC.
import * as C from "./charts.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { orderZoneProfiles, ZONE_METHODS, zoneNotes, zoneSport } from "./coach-ui.js";

const HR_METHODS = [
  ["garmin", "Zones Garmin (celles de ta montre)"],
  ["pct_max", "% de la FC max"],
  ["pct_reserve", "% de la FC de réserve (Karvonen)"],
  ["pct_seuil", "% de la FC au seuil lactique"],
  ["bornes", "Bornes à la main (comme Strava)"],
];
const HR_DEFAULT = { pct_max: [50, 60, 70, 80, 90], pct_reserve: [50, 60, 70, 80, 90], pct_seuil: [70, 85, 90, 95, 100] };
const PACE_METHODS = [["pct_vma", "% de la VMA"], ["pct_seuil", "% de la vitesse au seuil"], ["bornes", "Allures à la main"]];
const PACE_DEFAULT = { pct_vma: [70, 80, 88, 95], pct_seuil: [75, 85, 95, 102] };
const PACE_NAMES = ["Récup / EF", "Endurance active", "Seuil / semi", "Allure 10 km", "VMA"];

/**
 * Barre de zones : cinq segments entre lo et hi, séparés par quatre poignées qu'on peut tirer.
 * bounds : quatre positions (unités de l'axe, croissantes) ; label(i) : texte d'un segment ;
 * onDrag(i, value) : nouvelle position d'une séparation (arrondie par l'appelant).
 */
function zoneBar(box, { lo, hi, bounds, start, label, onDrag, editable, step = 1 }) {
  const P = C.palette();
  const pct = (v) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));
  const edges = [start ?? lo, ...bounds, hi];
  box.innerHTML = `<div class="zb-track">${[0, 1, 2, 3, 4].map((i) => `<div class="zb-seg" style="left:${pct(edges[i])}%;width:${pct(edges[i + 1]) - pct(edges[i])}%;background:${P.zones[i]};color:${C.inkOn(P.zones[i])}">
      <b>Z${i + 1}</b><span>${F.escape(label(i))}</span></div>`).join("")}
    ${editable ? bounds.map((b, i) => `<button type="button" class="zb-handle" data-handle="${i}" style="left:${pct(b)}%"
        aria-label="Séparation entre les zones ${i + 1} et ${i + 2}" role="slider" aria-valuenow="${b}"></button>`).join("") : ""}</div>`;
  if (!editable) return;
  const track = box.querySelector(".zb-track");
  box.querySelectorAll("[data-handle]").forEach((handle) => {
    const i = Number(handle.dataset.handle);
    const move = (clientX) => {
      const rect = track.getBoundingClientRect();
      const value = lo + ((clientX - rect.left) / rect.width) * (hi - lo);
      const min = (i === 0 ? edges[0] : bounds[i - 1]) + step;
      const max = (i === 3 ? hi : bounds[i + 1]) - step;
      onDrag(i, Math.max(min, Math.min(max, value)));
    };
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      const onMove = (ev) => move(ev.clientX);
      const stop = () => { handle.removeEventListener("pointermove", onMove); handle.removeEventListener("pointerup", stop); };
      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", stop);
    });
    handle.addEventListener("keydown", (e) => {
      const delta = { ArrowLeft: -step, ArrowDown: -step, ArrowRight: step, ArrowUp: step }[e.key];
      if (!delta) return;
      e.preventDefault();
      const min = (i === 0 ? edges[0] : bounds[i - 1]) + step;
      const max = (i === 3 ? hi : bounds[i + 1]) - step;
      onDrag(i, Math.max(min, Math.min(max, bounds[i] + delta)), true);
    });
  });
}

// =================================================================== FC
// Deux sources, l'une OU l'autre : les zones de la montre (un profil Garmin : course à pied, trail, général…,
// en lecture seule, avec sa FC max et sa FC au repos), ou des zones réglées dans Foulée (une méthode, une barre
// dont on tire les séparations). Jamais un mélange des deux.
const FOULEE_HR_METHODS = HR_METHODS.filter(([k]) => k !== "garmin");

export function hrZonesEditor(box, boot, profile) {
  const profiles = orderZoneProfiles(boot.garmin_profil?.profils || []);
  const legacy = boot.garmin_profil?.zones_fc || null;  // ancien format : un seul profil, sans le détail
  const saved = boot.reglages.zones_fc || {};
  const start = !saved.methode || saved.methode === "auto" ? (boot.profil_fc?.methode || "pct_max") : saved.methode;
  const z = {
    methode: start,
    last: start === "garmin" ? "pct_max" : start,  // la méthode Foulée à retrouver en revenant de la montre
    profil: saved.profil_garmin || (profiles.find((p) => p.sport === "RUNNING") || profiles[0])?.sport || null,
    pct: saved.pct ? [...saved.pct] : null,
    seuil: saved.seuil || null,
    bornes: saved.bornes ? [...saved.bornes] : null,
  };
  let focusHandle = null;

  const watch = () => profiles.find((p) => p.sport === z.profil) || profiles[0] || null;
  const lthr = () => z.seuil || watch()?.fc_seuil || legacy?.lthr || boot.garmin_profil?.profil?.seuil_fc || null;
  const pctOf = () => z.pct || HR_DEFAULT[z.methode] || HR_DEFAULT.pct_max;

  function floors() {
    const { max, rest } = profile();
    if (z.methode === "garmin") return watch()?.bornes?.map(Number) || legacy?.floors?.map(Number) || null;
    if (z.methode === "bornes") return [0, ...(z.bornes || current().slice(1))];
    const pct = pctOf();
    if (z.methode === "pct_reserve") return pct.map((p) => Math.round(rest + ((max - rest) * p) / 100));
    if (z.methode === "pct_seuil") return lthr() ? pct.map((p) => Math.round((lthr() * p) / 100)) : null;
    return pct.map((p) => Math.round((max * p) / 100));
  }
  function current() {
    // Zones en vigueur (celles du serveur), point de départ d'un passage aux bornes à la main
    return (boot.profil_fc?.floors || [0, 120, 140, 155, 170]).map(Number);
  }

  function watchPart() {
    if (!profiles.length && !legacy) {
      return `<p class="computed warn">${icon("warning")}<span>Garmin n'a pas encore donné tes zones : lance une synchro, ou règle-les dans Foulée.</span></p>`;
    }
    const w = watch();
    const facts = w ? [ZONE_METHODS[w.methode]?.[2], w.fc_max && `FC max ${F.int(w.fc_max)}`,
      w.fc_repos && `au repos ${F.int(w.fc_repos)}${w.repos_auto ? " (mise à jour par la montre)" : ""}`, w.fc_seuil && `au seuil ${F.int(w.fc_seuil)}`].filter(Boolean) : [];
    const notes = profiles.length ? zoneNotes(profiles) : [];
    return `${profiles.length > 1 ? `<div class="hz-profiles" role="radiogroup" aria-label="Profil de la montre"><span>Profil de la montre</span>
        <div class="segmented small">${profiles.map((p) => `<button type="button" role="radio" data-profile="${F.escape(p.sport)}" aria-checked="${p.sport === z.profil}" aria-pressed="${p.sport === z.profil}">${F.escape(zoneSport(p.sport))}</button>`).join("")}</div></div>` : ""}
      ${facts.length ? `<p class="hz-facts">${facts.map((t) => `<span>${F.escape(t)}</span>`).join("")}</p>` : ""}
      ${notes.length ? `<ul class="co-zone-notes">${notes.map((n) => `<li>${icon("info")}<span>${F.escape(n)}</span></li>`).join("")}</ul>` : ""}
      <p class="hint">Foulée suit ta montre : zones, FC max et FC au repos viennent d'elle, relues à chaque synchro. Pour les changer : Garmin Connect (zones de fréquence cardiaque) ou la montre.</p>`;
  }

  function fouleePart() {
    const { max, rest } = profile();
    const pct = pctOf();
    let inputs;
    if (z.methode === "bornes") {
      const f = floors();
      inputs = `<div class="zone-inputs">${[1, 2, 3, 4].map((i) => `<label class="field"><span>Z${i + 1} dès (bpm)</span>
        <input type="number" min="60" max="230" data-bound="${i - 1}" value="${f[i]}"></label>`).join("")}</div>
        <p class="hint">Comme sur Strava : la zone 1 compte tout ce qui est sous la zone 2.</p>`;
    } else {
      inputs = `${z.methode === "pct_seuil" ? `<label class="field narrow"><span>FC au seuil lactique (bpm)</span><input type="number" min="100" max="220" data-lthr value="${F.escape(z.seuil ?? "")}" placeholder="${F.escape(lthr() || "")}"></label>` : ""}
        <div class="zone-inputs">${pct.map((p, i) => `<label class="field"><span>Z${i + 1} dès (%)</span>
        <input type="number" min="20" max="130" step="1" data-pct="${i}" value="${p}"></label>`).join("")}</div>
        <p class="hint">${z.methode === "pct_max" ? `De ta FC max (${Math.round(max)} bpm, réglée dans « Coureur »).` : z.methode === "pct_reserve" ? `FC de repos + % × (FC max − FC de repos) : ${Math.round(rest)} + % × ${Math.round(max - rest)} bpm.` : lthr() ? `De ta FC au seuil (${lthr()} bpm${z.seuil ? "" : ", lue chez Garmin"}).` : "Renseigne ta FC au seuil (Garmin la donne si ta montre l'a mesurée)."}</p>`;
    }
    return `<div class="form-grid method-row"><label class="field"><span>Méthode</span><select data-method>${FOULEE_HR_METHODS.map(([k, l]) => `<option value="${k}" ${k === z.methode ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
      ${inputs}
      ${profiles.length || legacy ? `<p class="hint">Ta montre a ses propres zones : réglées ici, tes temps par zone peuvent différer de ceux de Garmin Connect.</p>` : ""}`;
  }

  function render() {
    const onWatch = z.methode === "garmin";
    const w = onWatch ? watch() : null;
    const { max, rest } = profile();
    const top = w?.fc_max || max;
    box.innerHTML = `<div class="hz-source" role="radiogroup" aria-label="D'où viennent tes zones FC">
        <button type="button" role="radio" class="hz-choice" data-source="montre" aria-checked="${onWatch}">${icon("watch")}<span><b>Celles de ma montre</b><small>réglées dans Garmin Connect</small></span></button>
        <button type="button" role="radio" class="hz-choice" data-source="foulee" aria-checked="${!onWatch}">${icon("settings")}<span><b>Réglées dans Foulée</b><small>% de la FC max, de réserve, du seuil ou à la main</small></span></button>
      </div>
      ${onWatch ? watchPart() : fouleePart()}
      <div class="zone-bar" data-bar></div>
      <p class="computed" data-text></p>
      ${onWatch && (w || legacy) ? `<button class="btn btn-ghost btn-small" type="button" data-adjust>${icon("edit")}Les reprendre dans Foulée pour les ajuster</button>` : ""}`;
    const f = floors();
    if (!f) {
      box.querySelector("[data-text]").textContent = onWatch ? "" : "Zones indisponibles pour l'instant avec cette méthode.";
      return;
    }
    const lo = f[0] > 0 ? Math.max(30, f[0] - 4) : Math.max(30, Math.min(f[1] - 25, rest - 5));
    const hi = Math.max(top + 4, f[4] + 10);
    const label = (i) => (i === 0 ? (f[0] > 0 ? `${f[0]}–${f[1] - 1}` : `< ${f[1]}`) : i === 4 ? `≥ ${f[4]}` : `${f[i]}–${f[i + 1] - 1}`);
    zoneBar(box.querySelector("[data-bar]"), {
      lo, hi, start: f[0] > 0 ? f[0] : lo, bounds: f.slice(1), label, editable: !onWatch,
      onDrag: (i, value, keyboard) => {
        const bpm = Math.round(value);
        if (z.methode === "bornes") {
          z.bornes = f.slice(1);
          z.bornes[i] = bpm;
        } else {
          const p = z.methode === "pct_reserve" ? ((bpm - rest) / (max - rest)) * 100 : z.methode === "pct_seuil" ? (bpm / lthr()) * 100 : (bpm / max) * 100;
          z.pct = [...pctOf()];
          z.pct[i + 1] = Math.round(p);
        }
        focusHandle = keyboard ? i : null;
        render();
      },
    });
    if (focusHandle !== null) box.querySelector(`[data-handle="${focusHandle}"]`)?.focus();
    box.querySelector("[data-text]").innerHTML = ["Échauffement", "Facile", "Aérobie", "Seuil", "Maximum"].map((n, i) => `Z${i + 1} ${n} : <b>${label(i)} bpm</b>`).join(" ; ");
  }

  box.addEventListener("change", (e) => {
    const t = e.target;
    if ("method" in t.dataset) {
      z.methode = t.value;
      z.last = t.value;
      z.pct = null;
      if (z.methode === "bornes" && !z.bornes) z.bornes = (floors() || current()).slice(1);
    } else if (t.dataset.pct !== undefined) {
      z.pct = [...pctOf()];
      z.pct[Number(t.dataset.pct)] = Number(t.value);
    } else if (t.dataset.bound !== undefined) {
      z.bornes = (z.bornes || floors().slice(1)).slice();
      z.bornes[Number(t.dataset.bound)] = Number(t.value);
    } else if ("lthr" in t.dataset) {
      z.seuil = t.value ? Number(t.value) : null;
    } else return;
    render();
  });
  box.addEventListener("click", (e) => {
    const source = e.target.closest("[data-source]");
    const prof = e.target.closest("[data-profile]");
    if (source) {
      const want = source.dataset.source === "montre" ? "garmin" : z.last;
      if (want === z.methode) return;
      z.methode = want;
      if (want === "bornes" && !z.bornes) z.bornes = current().slice(1);
    } else if (prof) {
      z.profil = prof.dataset.profile;
    } else if (e.target.closest("[data-adjust]")) {
      z.bornes = (floors() || current()).slice(1).map(Math.round);
      z.methode = "bornes";
      z.last = "bornes";
    } else return;
    render();
  });

  render();
  return {
    refresh: render,
    value: () => (z.methode === "garmin"
      ? { methode: "garmin", profil_garmin: watch()?.sport || null, pct: null, seuil: null, bornes: null }
      : { methode: z.methode, pct: z.methode.startsWith("pct") ? pctOf() : null, seuil: z.seuil || null,
        bornes: z.methode === "bornes" ? (z.bornes || floors().slice(1)) : null }),
  };
}

// ================================================================ allure
export function paceZonesEditor(box, boot, getVma) {
  const garminSpeed = boot.garmin_profil?.profil?.seuil_vitesse || null;
  const saved = boot.reglages.zones_allure || {};
  const z = {
    methode: saved.methode || "pct_vma",
    pct: saved.pct ? [...saved.pct] : saved.methode && saved.methode !== "pct_vma" ? null : [...(boot.reglages.zones_allure_pct_vma || PACE_DEFAULT.pct_vma)],
    seuil: saved.seuil || null,
    bornes: saved.bornes ? [...saved.bornes] : null,
  };
  let focusHandle = null;
  const threshold = () => (z.seuil ? 1000 / z.seuil : garminSpeed);
  const pctOf = () => z.pct || PACE_DEFAULT[z.methode] || PACE_DEFAULT.pct_vma;

  function speeds() {
    if (z.methode === "bornes") return (z.bornes || []).length === 4 ? z.bornes.map((s) => 1000 / s) : null;
    if (z.methode === "pct_seuil") return threshold() ? pctOf().map((p) => (threshold() * p) / 100) : null;
    return pctOf().map((p) => (getVma() * p) / 100 / 3.6);
  }

  function render() {
    const s = speeds();
    const pct = pctOf();
    let inputs;
    if (z.methode === "bornes") {
      const b = z.bornes || (speeds() || []).map((v) => Math.round(1000 / v));
      inputs = `<div class="zone-inputs">${[0, 1, 2, 3].map((i) => `<label class="field"><span>Z${i + 2} dès (min/km)</span>
        <input type="text" inputmode="numeric" data-pace="${i}" value="${F.escape(F.paceSecs(b[i]))}" placeholder="4:30"></label>`).join("")}</div>`;
    } else {
      inputs = `${z.methode === "pct_seuil" ? `<label class="field narrow"><span>Allure au seuil (min/km)</span><input type="text" inputmode="numeric" data-threshold value="${F.escape(z.seuil ? F.paceSecs(z.seuil) : "")}" placeholder="${garminSpeed ? F.pace(garminSpeed) : "4:10"}"></label>` : ""}
        <div class="zone-inputs">${pct.map((p, i) => `<label class="field"><span>Z${i + 2} dès (%)</span>
        <input type="number" min="30" max="140" step="1" data-pct="${i}" value="${p}"></label>`).join("")}</div>
        <p class="hint">${z.methode === "pct_vma" ? `De ta VMA (${F.dec1(getVma())} km/h).` : threshold() ? `De ta vitesse au seuil (${F.pace(threshold())} /km${z.seuil ? "" : ", lue chez Garmin"}).` : "Renseigne ton allure au seuil (Garmin la donne si ta montre l'a mesurée)."}</p>`;
    }
    box.innerHTML = `<div class="form-grid method-row"><label class="field"><span>Méthode</span><select data-method>${PACE_METHODS.map(([k, l]) => `<option value="${k}" ${k === z.methode ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
      ${inputs}<div class="zone-bar" data-bar></div><p class="computed" data-text></p>`;
    if (!s) {
      box.querySelector("[data-text]").textContent = "Zones indisponibles pour l'instant avec cette méthode.";
      return;
    }
    const lo = s[0] * 0.82;
    const hi = s[3] * 1.15;
    const label = (i) => (i === 0 ? `> ${F.pace(s[0])}` : i === 4 ? `< ${F.pace(s[3])}` : `${F.pace(s[i - 1])}–${F.pace(s[i])}`);
    zoneBar(box.querySelector("[data-bar]"), {
      lo, hi, bounds: s, label, editable: true, step: 0.01,
      onDrag: (i, speed, keyboard) => {
        if (z.methode === "bornes") {
          z.bornes = s.map((v) => Math.round(1000 / v));
          z.bornes[i] = Math.round(1000 / speed);
        } else {
          const base = z.methode === "pct_seuil" ? threshold() : getVma() / 3.6;
          z.pct = [...pctOf()];
          z.pct[i] = Math.round((speed / base) * 100);
        }
        focusHandle = keyboard ? i : null;
        render();
      },
    });
    if (focusHandle !== null) box.querySelector(`[data-handle="${focusHandle}"]`)?.focus();
    box.querySelector("[data-text]").innerHTML = PACE_NAMES.map((n, i) => `${n} : <b>${label(i)} /km</b>`).join(" ; ");
  }

  box.addEventListener("change", (e) => {
    const t = e.target;
    if ("method" in t.dataset) {
      const before = speeds();
      z.methode = t.value;
      z.pct = null;
      if (z.methode === "bornes" && before) z.bornes = before.map((v) => Math.round(1000 / v));
    } else if (t.dataset.pct !== undefined) {
      z.pct = [...pctOf()];
      z.pct[Number(t.dataset.pct)] = Number(t.value);
    } else if (t.dataset.pace !== undefined) {
      const secs = F.parsePace(t.value);
      if (!secs) { t.setCustomValidity("Format 4:30"); t.reportValidity(); return; }
      z.bornes = (z.bornes || (speeds() || []).map((v) => Math.round(1000 / v))).slice();
      z.bornes[Number(t.dataset.pace)] = secs;
    } else if ("threshold" in t.dataset) {
      z.seuil = F.parsePace(t.value);
    } else return;
    render();
  });

  render();
  return {
    refresh: render,
    value: () => ({ methode: z.methode, pct: z.methode === "bornes" ? null : pctOf(), seuil: z.seuil || null,
      bornes: z.methode === "bornes" ? z.bornes : null }),
  };
}

// ================================================================ couleurs
const ZONE_LABELS = ["Échauffement", "Facile", "Aérobie", "Seuil", "Maximum"];

/**
 * Couleurs des zones, les mêmes pour la FC et l'allure : comme Garmin (par défaut), dégradé de bleus, ou à son goût.
 * Chaque choix s'applique tout de suite à toute l'interface ; onApply repeint les barres des zones.
 */
export function zoneColorsEditor(box, boot, { onApply } = {}) {
  const saved = boot.reglages.couleurs_zones || {};
  const z = { style: saved.style || "garmin", perso: saved.perso ? [...saved.perso] : null };
  const value = () => (z.style === "garmin" && !z.perso ? null : { style: z.style, perso: z.perso });
  // Les couleurs d'un style dans le thème affiché (clair ou sombre) : appliquées un instant, lues, puis rendues
  const colorsOf = (style) => {
    C.applyZoneColors({ style, perso: z.perso });
    const colors = C.palette().zones;
    C.applyZoneColors(value());
    return colors;
  };
  const hex = (c) => (/^#[0-9a-f]{6}$/i.test(c) ? c.toLowerCase() : C.GARMIN_ZONE_COLORS[0]);
  const strip = (colors) => `<span class="zc-strip" aria-hidden="true">${colors.map((c) => `<i style="background:${c}"></i>`).join("")}</span>`;

  function render() {
    const perso = z.style === "perso";
    box.innerHTML = `<div class="zc-choices" role="radiogroup" aria-label="Couleurs des zones">
        ${C.ZONE_STYLES.map(([id, label, hint]) => `<button type="button" role="radio" class="zc-choice" data-style="${id}" aria-checked="${z.style === id}">
          ${strip(id === "perso" && !z.perso ? C.GARMIN_ZONE_COLORS.map(() => "var(--surface-2)") : colorsOf(id))}
          <span><b>${F.escape(label)}</b><small>${F.escape(hint)}</small></span></button>`).join("")}
      </div>
      ${perso ? `<div class="zc-picks">${z.perso.map((c, i) => `<label class="zc-pick"><input type="color" data-color="${i}" value="${hex(c)}">
          <span><b>Z${i + 1}</b> ${ZONE_LABELS[i]}</span></label>`).join("")}
        <button class="btn btn-ghost btn-small" type="button" data-from-garmin>${icon("reset")}Repartir des couleurs Garmin</button></div>` : ""}
      <p class="hint">Les mêmes couleurs pour les zones FC et les zones d'allure : graphiques, barres ci-dessus et ci-dessous, fiche du coach.</p>`;
  }
  const apply = () => { C.applyZoneColors(value()); onApply?.(); };

  box.addEventListener("click", (e) => {
    const choice = e.target.closest("[data-style]");
    if (choice) {
      if (choice.dataset.style === z.style) return;
      // « À mon goût » part des couleurs affichées (celles de Garmin ou les bleus), à retoucher zone par zone
      if (choice.dataset.style === "perso" && !z.perso) z.perso = C.palette().zones.map(hex);
      z.style = choice.dataset.style;
    } else if (e.target.closest("[data-from-garmin]")) {
      z.perso = [...C.GARMIN_ZONE_COLORS];
    } else return;
    apply();
    render();
  });
  box.addEventListener("input", (e) => {
    const i = e.target.dataset?.color;
    if (i === undefined) return;
    z.perso[Number(i)] = e.target.value.toLowerCase();
    apply();
    box.querySelector('[data-style="perso"] .zc-strip').innerHTML = z.perso.map((c) => `<i style="background:${c}"></i>`).join("");
  });

  render();
  return { value };
}
