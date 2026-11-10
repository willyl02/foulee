// Réglages → Horaires de travail : bureau, 2x8, 3x8, 5x8 ou cycle personnalisé, heures des postes, congés.
// Même modèle que le serveur (schedule.py) ; l'aperçu utilise les mêmes règles (format.js).
import * as C from "./charts.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const DAYS = ["Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Dim."];
const MODELS = [
  ["bureau", "Bureau", "Mêmes horaires du lundi au vendredi.", "briefcase"],
  ["2x8", "Matin / soir (2x8)", "Une semaine du matin, une du soir, selon la parité des semaines.", "shift"],
  ["3x8", "3x8", "Matin, après-midi, nuit : une semaine chacun.", "clock"],
  ["5x8", "5x8", "Cycle continu en jours (2 matins, 2 après-midi, 2 nuits, 4 repos…).", "calendar"],
  ["perso", "Personnalisé", "Ton propre cycle, en semaines ou en jours.", "edit"],
];

const week = (code, days = 5) => [...Array(days).fill(code), ...Array(7 - days).fill("")];
const MORNING = { id: "matin", nom: "Matin", debut: "05:00", fin: "13:00" };
const AFTERNOON = { id: "apres-midi", nom: "Après-midi", debut: "13:00", fin: "21:00" };
const NIGHT = { id: "nuit", nom: "Nuit", debut: "21:00", fin: "05:00" };

function preset(model) {
  const monday = F.isoDate(F.mondayOf(new Date()));
  const base = { actif: true, modele: model, conges: [], jours_ouvres: true };
  if (model === "bureau") {
    return { ...base, postes: [{ id: "journee", nom: "Journée", debut: "08:30", fin: "17:30" }],
      cycle: { unite: "semaine", semaines: [week("journee")], ancrage: monday } };
  }
  if (model === "3x8") {
    return { ...base, postes: [MORNING, AFTERNOON, NIGHT],
      cycle: { unite: "semaine", semaines: [week("matin"), week("apres-midi"), week("nuit")], ancrage: monday } };
  }
  if (model === "5x8") {
    return { ...base, postes: [MORNING, AFTERNOON, NIGHT],
      cycle: { unite: "jour", jours: ["matin", "matin", "apres-midi", "apres-midi", "nuit", "nuit", "", "", "", ""], debut: F.isoDate(new Date()) } };
  }
  return { ...base, modele: model === "perso" ? "perso" : "2x8", postes: [MORNING, { id: "soir", nom: "Soir", debut: "13:00", fin: "21:00" }],
    cycle: { unite: "semaine", semaines: [week("matin"), week("soir")], ancrage: "parite" } };
}

function slug(text, taken) {
  let id = String(text || "poste").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 20) || "poste";
  let n = 2;
  const base = id;
  while (taken.includes(id) || id === "repos") { id = `${base}-${n}`; n += 1; }
  return id;
}

/** Éditeur d'horaires. Renvoie { value() } : les horaires prêts à enregistrer. */
export function scheduleEditor(box, initial) {
  let h = structuredClone(initial);
  const palette = () => C.palette();
  const settingsLike = () => ({ horaires: h });

  const color = (id) => F.shiftColor(id, settingsLike(), palette());
  const options = (value) => `<option value="" ${value ? "" : "selected"}>Repos</option>${h.postes.map((p) => `<option value="${F.escape(p.id)}" ${p.id === value ? "selected" : ""}>${F.escape(p.nom)}</option>`).join("")}`;

  function render() {
    const c = h.cycle;
    const isWeek = c.unite === "semaine";
    const today = new Date();
    let anchorUI = "";
    if (isWeek) {
      if (c.semaines.length === 2) {
        anchorUI += `<label class="check"><input type="checkbox" data-parity ${c.ancrage === "parite" ? "checked" : ""}>Suivre la parité des semaines (1re ligne = semaines impaires)</label>`;
      }
      if (c.ancrage === "parite") {
        anchorUI += `<button class="btn btn-ghost" type="button" data-swap>${icon("shift")}Inverser semaines paires et impaires</button>`;
      } else {
        const index = F.cycleWeekIndex(today, h);
        anchorUI += `<label class="inline-field"><span>Cette semaine (S${F.isoWeek(today).week}) correspond à la</span>
          <select data-current-week>${c.semaines.map((_, i) => `<option value="${i}" ${i === index ? "selected" : ""}>semaine ${i + 1}</option>`).join("")}</select><span>du cycle</span></label>`;
      }
    } else {
      const start = F.parseDate(c.debut);
      const diff = Math.round((Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) - Date.UTC(start.getFullYear(), start.getMonth(), start.getDate())) / 86400000);
      const current = ((diff % c.jours.length) + c.jours.length) % c.jours.length;
      anchorUI = `<label class="inline-field"><span>Aujourd'hui correspond au</span>
        <select data-current-day>${c.jours.map((_, i) => `<option value="${i}" ${i === current ? "selected" : ""}>jour ${i + 1}</option>`).join("")}</select><span>du cycle</span></label>`;
    }
    const weekRows = isWeek ? c.semaines.map((row, i) => `<tr><th>${c.ancrage === "parite" ? (i === 0 ? "Semaines impaires" : "Semaines paires") : `Semaine ${i + 1}`}</th>
        ${row.map((code, j) => `<td><select class="cell-select" data-week="${i}" data-day="${j}" style="--c:${code ? color(code) : "transparent"}" aria-label="${F.escape(`${DAYS[j]} : semaine ${i + 1}`)}">${options(code)}</select></td>`).join("")}</tr>`).join("") : "";
    const dayCells = !isWeek ? c.jours.map((code, i) => `<label class="day-cell"><span>Jour ${i + 1}</span>
        <select class="cell-select" data-cycle-day="${i}" style="--c:${code ? color(code) : "transparent"}">${options(code)}</select></label>`).join("") : "";
    box.innerHTML = `
      <label class="check"><input type="checkbox" data-actif ${h.actif !== false ? "checked" : ""}>Tenir compte de mes horaires de travail</label>
      <div class="model-pick" role="radiogroup" aria-label="Type d'horaires">${MODELS.map(([id, label, desc, ic]) => `
        <button type="button" role="radio" aria-checked="${h.modele === id}" data-model="${id}">${icon(ic)}<b>${label}</b><span>${desc}</span></button>`).join("")}</div>
      <div class="sched-part">
        <h3>Postes et heures</h3>
        <div class="postes-list">${h.postes.map((p, i) => `<div class="poste-row">
            <i class="dot" style="background:${color(p.id)}"></i>
            <input type="text" data-poste-name="${i}" value="${F.escape(p.nom)}" maxlength="30" aria-label="Nom du poste">
            <label class="inline-field"><span>de</span><input type="time" data-poste-start="${i}" value="${F.escape(p.debut)}" aria-label="Début du poste ${F.escape(p.nom)}"></label>
            <label class="inline-field"><span>à</span><input type="time" data-poste-end="${i}" value="${F.escape(p.fin)}" aria-label="Fin du poste ${F.escape(p.nom)}"></label>
            ${h.postes.length > 1 ? `<button class="btn btn-ghost icon-btn" type="button" data-remove-poste="${i}" aria-label="Retirer le poste ${F.escape(p.nom)}">${icon("close")}</button>` : ""}
          </div>`).join("")}</div>
        ${h.postes.length < 8 ? `<button class="btn btn-ghost" type="button" data-add-poste>${icon("plus")}Ajouter un poste</button>` : ""}
      </div>
      <div class="sched-part">
        <h3>Cycle</h3>
        ${h.modele === "perso" ? `<div class="segmented small" role="group" aria-label="Le cycle se compte">
            <button type="button" data-unit="semaine" aria-pressed="${isWeek}">En semaines</button>
            <button type="button" data-unit="jour" aria-pressed="${!isWeek}">En jours</button></div>` : ""}
        ${isWeek ? `<div class="cycle-scroll"><table class="cycle-table"><thead><tr><th></th>${DAYS.map((d) => `<th>${d}</th>`).join("")}</tr></thead><tbody>${weekRows}</tbody></table></div>
          <div class="inline-actions">${["3x8", "perso"].includes(h.modele) || c.semaines.length > 2 ? `
            ${c.semaines.length < 8 ? `<button class="btn btn-ghost" type="button" data-add-week>${icon("plus")}Ajouter une semaine</button>` : ""}
            ${c.semaines.length > 1 ? `<button class="btn btn-ghost" type="button" data-remove-week>${icon("close")}Retirer la dernière</button>` : ""}` : ""}</div>`
          : `<div class="day-cycle">${dayCells}</div>
          <div class="inline-actions">${c.jours.length < 42 ? `<button class="btn btn-ghost" type="button" data-add-day>${icon("plus")}Ajouter un jour</button>` : ""}
            ${c.jours.length > 1 ? `<button class="btn btn-ghost" type="button" data-remove-day>${icon("close")}Retirer le dernier</button>` : ""}</div>`}
        <div class="inline-actions">${anchorUI}</div>
      </div>
      <div class="sched-part">
        <h3>Congés</h3>
        <p class="hint">Ces jours sont mis de côté dans les comparaisons entre postes.</p>
        <div class="leaves">${(h.conges || []).map((l, i) => `<div class="leave-row">
            <label class="inline-field"><span>du</span><input type="date" data-leave-start="${i}" value="${F.escape(l.du)}"></label>
            <label class="inline-field"><span>au</span><input type="date" data-leave-end="${i}" value="${F.escape(l.au)}"></label>
            <input type="text" data-leave-name="${i}" value="${F.escape(l.nom || "")}" placeholder="Été, Noël…" maxlength="40" aria-label="Nom des congés">
            <button class="btn btn-ghost icon-btn" type="button" data-remove-leave="${i}" aria-label="Retirer ces congés">${icon("close")}</button>
          </div>`).join("")}</div>
        <button class="btn btn-ghost" type="button" data-add-leave>${icon("plus")}Ajouter des congés</button>
      </div>
      <label class="check"><input type="checkbox" data-ouvres ${h.jours_ouvres !== false ? "checked" : ""}>Ne comparer que les jours travaillés (sinon les jours de repos comptent avec le poste de leur semaine)</label>
      <div class="sched-preview" data-preview></div>`;
    preview();
  }

  function preview() {
    const out = box.querySelector("[data-preview]");
    if (!out) return;
    const settings = settingsLike();
    const start = F.mondayOf(new Date());
    const today = F.isoDate(new Date());
    const cells = [];
    for (let i = 0; i < 28; i += 1) {
      const day = F.addDays(start, i);
      const plan = F.dayPlan(day, settings);
      const label = plan.poste ? plan.nom : plan.conges ? "Congés" : plan.repos ? "Repos" : "";
      const letter = plan.poste ? plan.nom.charAt(0) : plan.conges ? "C" : "·";
      cells.push(`<span class="pv-day${F.isoDate(day) === today ? " today" : ""}${plan.poste ? "" : " off"}" style="--c:${plan.poste ? color(plan.poste) : "transparent"}" title="${F.escape(`${F.dateLong(F.isoDate(day))} : ${label}${plan.debut ? ` ${plan.debut}–${plan.fin}` : ""}`)}">${F.escape(letter)}</span>`);
    }
    const now = F.dayPlan(new Date(), settings);
    const text = !now.actif ? "Horaires désactivés : pas de coloration ni de comparaison par poste."
      : now.poste ? `Aujourd'hui : <b>${F.escape(now.nom)}</b>, ${now.debut}–${now.fin}.` : `Aujourd'hui : <b>${F.escape(now.conges || now.nom)}</b>.`;
    out.innerHTML = `<p class="computed">${text}</p>
      <div class="pv-grid" aria-label="Aperçu des quatre semaines à partir de ce lundi">${DAYS.map((d) => `<span class="pv-head">${d.charAt(0)}</span>`).join("")}${cells.join("")}</div>`;
  }

  box.addEventListener("click", (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    const c = h.cycle;
    if (t.dataset.model) {
      const keep = { actif: h.actif, conges: h.conges, jours_ouvres: h.jours_ouvres };
      h = t.dataset.model === "perso" ? { ...h, modele: "perso" } : { ...preset(t.dataset.model), ...keep };
    } else if (t.dataset.unit) {
      if (t.dataset.unit === c.unite) return;
      h.cycle = t.dataset.unit === "jour"
        ? { unite: "jour", jours: (c.semaines || [[""]]).flat().slice(0, 42), debut: F.isoDate(F.mondayOf(new Date())) }
        : { unite: "semaine", semaines: [week(h.postes[0].id)], ancrage: F.isoDate(F.mondayOf(new Date())) };
    } else if ("addPoste" in t.dataset) {
      const name = `Poste ${h.postes.length + 1}`;
      h.postes.push({ id: slug(name, h.postes.map((p) => p.id)), nom: name, debut: "08:00", fin: "16:00" });
    } else if (t.dataset.removePoste !== undefined) {
      const [gone] = h.postes.splice(Number(t.dataset.removePoste), 1);
      const clear = (code) => (code === gone.id ? "" : code);
      if (c.unite === "jour") c.jours = c.jours.map(clear); else c.semaines = c.semaines.map((r) => r.map(clear));
    } else if ("addWeek" in t.dataset) {
      if (c.ancrage === "parite") c.ancrage = F.isoDate(F.mondayOf(new Date()));
      c.semaines.push(week(h.postes[c.semaines.length % h.postes.length].id));
    } else if ("removeWeek" in t.dataset) {
      c.semaines.pop();
      if (c.semaines.length !== 2 && c.ancrage === "parite") c.ancrage = F.isoDate(F.mondayOf(new Date()));
    } else if ("addDay" in t.dataset) {
      c.jours.push("");
    } else if ("removeDay" in t.dataset) {
      c.jours.pop();
    } else if ("swap" in t.dataset) {
      c.semaines.reverse();
    } else if ("addLeave" in t.dataset) {
      const day = F.isoDate(new Date());
      (h.conges ||= []).push({ du: day, au: F.isoDate(F.addDays(new Date(), 6)), nom: "" });
    } else if (t.dataset.removeLeave !== undefined) {
      h.conges.splice(Number(t.dataset.removeLeave), 1);
    } else return;
    render();
  });

  box.addEventListener("change", (e) => {
    const t = e.target;
    const c = h.cycle;
    const d = t.dataset;
    if ("actif" in d) h.actif = t.checked;
    else if ("ouvres" in d) h.jours_ouvres = t.checked;
    else if (d.week !== undefined) c.semaines[Number(d.week)][Number(d.day)] = t.value;
    else if (d.cycleDay !== undefined) c.jours[Number(d.cycleDay)] = t.value;
    else if (d.posteName !== undefined) h.postes[Number(d.posteName)].nom = t.value.trim() || h.postes[Number(d.posteName)].nom;
    else if (d.posteStart !== undefined) h.postes[Number(d.posteStart)].debut = t.value;
    else if (d.posteEnd !== undefined) h.postes[Number(d.posteEnd)].fin = t.value;
    else if ("parity" in d) c.ancrage = t.checked ? "parite" : F.isoDate(F.mondayOf(new Date()));
    else if (d.currentWeek !== undefined) {
      c.ancrage = F.isoDate(F.addDays(F.mondayOf(new Date()), -7 * Number(t.value)));
    } else if (d.currentDay !== undefined) {
      c.debut = F.isoDate(F.addDays(new Date(), -Number(t.value)));
    } else if (d.leaveStart !== undefined) h.conges[Number(d.leaveStart)].du = t.value;
    else if (d.leaveEnd !== undefined) h.conges[Number(d.leaveEnd)].au = t.value;
    else if (d.leaveName !== undefined) h.conges[Number(d.leaveName)].nom = t.value;
    else return;
    render();
  });

  render();
  return { value: () => structuredClone(h) };
}
