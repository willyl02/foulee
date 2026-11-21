// Le calendrier des pages coach et élève, à la semaine, au mois ou à l'année (au choix, retenu dans ce
// navigateur), avec des flèches pour passer d'une période à l'autre. Une case par jour : les séances prévues (son
// plan, celles du coach) et leur esquisse, les séances faites (un clic ouvre la séance) et les courses visées. À
// l'année, de simples pastilles : un clic sur un jour ouvre sa semaine, un clic sur un mois ouvre ce mois.
// Les neuf semaines autour d'aujourd'hui arrivent avec la page ; le reste se demande au relais, période par période.
import * as F from "./format.js";
import { icon } from "./icons.js";
import { sketchSVG } from "./sketch.js";

const DOW = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
const DOW1 = ["L", "M", "M", "J", "V", "S", "D"];
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const MONTHS_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
  "novembre", "décembre"];
const VIEWS = [["semaine", "Semaine"], ["mois", "Mois"], ["annee", "Année"]];
const SHARED_DAYS = 28; // les séances faites ne sont partagées que sur quatre semaines

function km(m) { return m ? `${F.dec1(m / 1000)} km` : ""; }
const cap = (text) => text.charAt(0).toUpperCase() + text.slice(1);

// ------------------------------------------------------------------ une case (semaine et mois)
function dayCell(day, ctx, { out = false, week = false } = {}) {
  const { today, races, options } = ctx;
  const d = F.parseDate(day.date);
  const cls = ["cc-day", day.date === today ? "today" : "", day.date < today ? "past" : "", out ? "out" : ""];
  if (out) return `<div class="${cls.filter(Boolean).join(" ")}"><div class="cc-num">${d.getDate()}</div></div>`;
  const race = races.get(day.date);
  const races2 = day.prevu.filter((p) => p.type === "course" && !race);
  const planned = day.prevu.filter((p) => p.type !== "course").map((p) => {
    const state = p.statut === "fait" ? "done" : p.statut === "manque" ? "miss" : "next";
    const who = p.source === "coach" ? (options.coachSide ? "proposée par toi" : "de ton coach") : options.coachSide ? "son plan" : "ton plan";
    return `<div class="cc-pl ${state}${p.source === "coach" ? " coach" : ""}" title="${F.escape(`${p.titre} (${who})`)}">
        <span class="cc-pl-t">${p.statut === "fait" ? icon("check") : p.statut === "manque" ? icon("close") : ""}<span class="cc-txt">${F.escape(p.titre)}</span></span>
        ${p.blocs?.length && p.statut !== "manque" ? sketchSVG(p.blocs, { vma: options.vma, height: week ? 20 : 14, approx: p.esquisse_approchee }) : ""}</div>`;
  }).join("");
  const done = (day.fait || []).map((s) => `<a class="cc-done" href="${options.sessionHref(s)}" title="${F.escape(s.nom || s.sport_label || "Séance")}">
      ${F.escape([km(s.distance_m) || (s.duree_s ? F.duration(s.duree_s, { short: true }) : ""), s.nom || s.sport_label].filter(Boolean).join(" · "))}</a>`).join("");
  if (race || races2.length) cls.push("race");
  const label = week ? `<span class="cc-dname">${DOW[(d.getDay() + 6) % 7]}</span> ${d.getDate()}${d.getDate() === 1 ? ` ${MONTHS[d.getMonth()]}` : ""}`
    : `${d.getDate()}`;
  return `<div class="${cls.filter(Boolean).join(" ")}"><div class="cc-num">${label}</div>
    ${race ? `<div class="cc-race">${icon("flag")}${F.escape(race.nom || "Course")}</div>` : ""}${races2.map((p) => `<div class="cc-race">${icon("flag")}${F.escape(p.titre)}</div>`).join("")}${planned}${done}</div>`;
}

const emptyDay = (iso) => ({ date: iso, prevu: [], fait: [] });

// ------------------------------------------------------------------ les périodes
function bounds(view, anchor) {
  const a = F.parseDate(anchor);
  if (view === "semaine") {
    const start = F.mondayOf(a);
    return { start, end: F.addDays(start, 6) };
  }
  if (view === "mois") {
    const first = new Date(a.getFullYear(), a.getMonth(), 1);
    const last = new Date(a.getFullYear(), a.getMonth() + 1, 0);
    return { start: F.mondayOf(first), end: F.addDays(F.mondayOf(last), 6), first, last };
  }
  const first = new Date(a.getFullYear(), 0, 1);
  const last = new Date(a.getFullYear(), 11, 31);
  return { start: F.mondayOf(first), end: F.addDays(F.mondayOf(last), 6), first, last };
}

function periodLabel(view, anchor) {
  const a = F.parseDate(anchor);
  if (view === "annee") return String(a.getFullYear());
  if (view === "mois") return `${cap(MONTHS_LONG[a.getMonth()])} ${a.getFullYear()}`;
  const start = F.mondayOf(a);
  const end = F.addDays(start, 6);
  const left = start.getMonth() === end.getMonth() ? `${start.getDate()}` : `${start.getDate()} ${MONTHS[start.getMonth()]}${start.getFullYear() !== end.getFullYear() ? ` ${start.getFullYear()}` : ""}`;
  return `${left} – ${end.getDate()} ${MONTHS[end.getMonth()]} ${end.getFullYear()}`;
}

function shift(view, anchor, step) {
  const a = F.parseDate(anchor);
  if (view === "semaine") return F.isoDate(F.addDays(a, 7 * step));
  if (view === "mois") return F.isoDate(new Date(a.getFullYear(), a.getMonth() + step, 1));
  return F.isoDate(new Date(a.getFullYear() + step, 0, 1));
}

function samePeriod(view, a, b) {
  if (view === "semaine") return F.isoDate(F.mondayOf(F.parseDate(a))) === F.isoDate(F.mondayOf(F.parseDate(b)));
  const x = F.parseDate(a); const y = F.parseDate(b);
  return x.getFullYear() === y.getFullYear() && (view === "annee" || x.getMonth() === y.getMonth());
}

// ------------------------------------------------------------------ les trois vues
function weekView(days, ctx) {
  return `<div class="cc-grid is-week">${days.map((d) => dayCell(d, ctx, { week: true })).join("")}</div>`;
}

function monthView(days, ctx, month) {
  return `<div class="cc-grid">${DOW.map((d) => `<span class="cc-dow">${d}</span>`).join("")}${days.map((d) => dayCell(d, ctx, {
    out: F.parseDate(d.date).getMonth() !== month })).join("")}</div>`;
}

/** À l'année : douze petits mois, une pastille par jour où il y a quelque chose. */
function yearView(byDate, ctx, year) {
  const { today, races, options } = ctx;
  const months = [];
  for (let m = 0; m < 12; m += 1) {
    const first = new Date(year, m, 1);
    const last = new Date(year, m + 1, 0);
    const cells = [];
    for (let k = 0; k < (first.getDay() + 6) % 7; k += 1) cells.push(`<span class="cy-day out"></span>`);
    let count = 0;
    for (let d = 1; d <= last.getDate(); d += 1) {
      const iso = F.isoDate(new Date(year, m, d));
      const day = byDate.get(iso) || emptyDay(iso);
      const marks = [];
      const titles = [];
      if (races.has(iso) || day.prevu.some((p) => p.type === "course")) {
        marks.push("race");
        titles.push(`Course : ${races.get(iso)?.nom || day.prevu.find((p) => p.type === "course")?.titre || ""}`);
      }
      day.prevu.filter((p) => p.type !== "course").forEach((p) => {
        marks.push(p.statut === "fait" ? "done" : p.statut === "manque" ? "miss" : p.source === "coach" ? "coach" : "plan");
        titles.push(`${p.titre}${p.statut === "fait" ? " (faite)" : p.statut === "manque" ? " (manquée)" : ""}`);
      });
      const linked = day.prevu.some((p) => p.statut === "fait");
      if ((day.fait || []).length && !linked) {
        marks.push("extra");
        day.fait.forEach((s) => titles.push(`Faite : ${s.nom || s.sport_label || "séance"}`));
      }
      if (marks.length) count += 1;
      const unique = [...new Set(marks)].slice(0, 3);
      cells.push(`<button type="button" class="cy-day${iso === today ? " today" : ""}${marks.length ? " has" : ""}${iso < today ? " past" : ""}" data-cal-day="${iso}"
          title="${F.escape([F.dateLong(iso), ...titles].join("\n"))}"><span class="cy-n">${d}</span>
          <span class="cy-dots">${unique.map((k) => `<i class="cy-dot ${k}"></i>`).join("")}</span></button>`);
    }
    months.push(`<section class="cy-month${today.startsWith(`${year}-${String(m + 1).padStart(2, "0")}`) ? " now" : ""}">
      <button type="button" class="cy-title" data-cal-month="${F.isoDate(first)}" title="Ouvrir ${MONTHS_LONG[m]} ${year}">${cap(MONTHS_LONG[m])}${count ? `<small>${count} jour${count > 1 ? "s" : ""}</small>` : ""}</button>
      <div class="cy-grid">${DOW1.map((d) => `<span class="cy-dow">${d}</span>`).join("")}${cells.join("")}</div></section>`);
  }
  return `<div class="cy">${months.join("")}</div>`;
}

function legend(view, options) {
  if (view === "annee") {
    return `<div class="cc-legend cy-legend"><span><i class="cy-dot coach"></i>${options.coachSide ? "proposée par toi" : "de ton coach"}</span>
      <span><i class="cy-dot plan"></i>${options.coachSide ? "son plan" : "ton plan"}</span><span><i class="cy-dot done"></i>faite</span>
      <span><i class="cy-dot miss"></i>manquée</span><span><i class="cy-dot extra"></i>séance faite hors plan</span><span><i class="cy-dot race"></i>course</span></div>`;
  }
  return `<div class="cc-legend"><span class="cc-pl next coach">${options.coachSide ? "proposée par toi" : "de ton coach"}</span><span class="cc-pl next">${options.coachSide ? "son plan" : "ton plan"}</span>
      <span class="cc-pl done">${icon("check")}faite</span><span class="cc-pl miss">${icon("close")}manquée</span><span class="cc-done">séance faite</span>
      <span class="cc-race">${icon("flag")}course visée</span></div>`;
}

// ------------------------------------------------------------------ la carte
// Replié ou déplié, et la vue choisie : retenus dans ce navigateur, pour les deux pages (fiche de l'élève, « Mon coach »)
const FOLD_KEY = "foulee-calendrier-replie";
const VIEW_KEY = "foulee-calendrier-vue";
function stored(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch (e) { return fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, value); } catch (e) { /* rien à retenir */ }
}
document.addEventListener("toggle", (e) => {
  if (!e.target.matches?.("details.co-cal")) return;
  store(FOLD_KEY, e.target.open ? "0" : "1");
}, true);

const CARDS = new Map();
let nextId = 1;

/**
 * La carte entière : titre, chevron pour la replier (état retenu), et le calendrier, à brancher avec
 * wireCalendar() une fois dans la page. mois : {debut, fin, jours: [{date, prevu, fait}]} (relais) ; options :
 * vma, goals [{nom, date}], sessionHref(s), coachSide, fetchRange(debut, fin) (le calendrier d'une autre période).
 */
export function calendarCard(title, sub, mois, options) {
  if (!mois?.jours?.length) return "";
  const id = `cal${nextId++}`;
  CARDS.set(id, { mois, options });
  return `<details class="coach-card co-cal" data-cal="${id}"${stored(FOLD_KEY, "0") === "1" ? "" : " open"}><summary><h2>${icon("calendar")}${F.escape(title)}${sub ? ` <span class="co-sub">${F.escape(sub)}</span>` : ""}</h2>
    <span class="co-fold" title="Replier ou déplier le calendrier" aria-hidden="true">${icon("chevron")}</span></summary><div class="cc" aria-live="polite"></div></details>`;
}

/** Branche les calendriers posés par calendarCard() dans root. */
export function wireCalendar(root) {
  root.querySelectorAll("details.co-cal[data-cal]").forEach((card) => {
    const entry = CARDS.get(card.dataset.cal);
    if (!entry || card.dataset.wired) return;
    CARDS.delete(card.dataset.cal);
    card.dataset.wired = "1";
    const { mois, options } = entry;
    const box = card.querySelector(".cc");
    const today = F.isoDate(new Date());
    const races = new Map((options.goals || []).filter((g) => g?.date).map((g) => [g.date, g]));
    const ctx = { today, races, options };
    // ce qu'on a déjà : jour par jour, avec ou sans les esquisses (à l'année, le relais ne les envoie pas)
    const known = new Map();
    const keep = (data, light) => (data?.jours || []).forEach((d) => {
      const had = known.get(d.date);
      if (!light || !had || had.light) known.set(d.date, { day: d, light });
    });
    keep(mois, false);
    let view = VIEWS.some(([k]) => k === stored(VIEW_KEY, "mois")) ? stored(VIEW_KEY, "mois") : "mois";
    let anchor = today;
    let note = "";
    let ticket = 0;

    const covered = (start, end, full) => {
      for (let d = new Date(start); d <= end; d = F.addDays(d, 1)) {
        const k = known.get(F.isoDate(d));
        if (!k || (full && k.light)) return false;
      }
      return true;
    };

    const draw = () => {
      const { start, end } = bounds(view, anchor);
      const days = [];
      for (let d = new Date(start); d <= end; d = F.addDays(d, 1)) {
        const iso = F.isoDate(d);
        days.push(known.get(iso)?.day || emptyDay(iso));
      }
      const a = F.parseDate(anchor);
      const body = view === "semaine" ? weekView(days, ctx) : view === "mois" ? monthView(days, ctx, a.getMonth())
        : yearView(new Map(days.map((d) => [d.date, d])), ctx, a.getFullYear());
      const sharedFrom = F.isoDate(F.addDays(F.parseDate(today), -SHARED_DAYS));
      const { first } = bounds(view, anchor);
      const old = F.isoDate(first || start) < sharedFrom; // une partie de la période est plus vieille que le partage
      box.innerHTML = `<div class="cc-bar">
          <div class="segmented small" role="group" aria-label="Afficher le calendrier">${VIEWS.map(([k, label]) => `<button type="button" data-cal-view="${k}" aria-pressed="${k === view}">${label}</button>`).join("")}</div>
          <div class="cc-nav">
            <button class="btn btn-ghost icon-btn" type="button" data-cal-step="-1" title="${view === "semaine" ? "Semaine" : view === "mois" ? "Mois" : "Année"} précédente" aria-label="Période précédente">${icon("left")}</button>
            <h3 class="cc-period">${F.escape(periodLabel(view, anchor))}</h3>
            <button class="btn btn-ghost icon-btn" type="button" data-cal-step="1" title="${view === "semaine" ? "Semaine" : view === "mois" ? "Mois" : "Année"} suivante" aria-label="Période suivante">${icon("right")}</button>
          </div>
          ${samePeriod(view, anchor, today) ? "" : `<button class="btn btn-ghost btn-small" type="button" data-cal-today>Aujourd'hui</button>`}
        </div>
        ${note ? `<p class="cc-note">${icon("info")}<span>${F.escape(note)}</span></p>` : ""}
        ${body}
        ${old ? `<p class="cc-note muted">${icon("info")}<span>Les séances faites ne sont partagées que sur quatre semaines : avant le ${F.escape(F.dateLong(sharedFrom, { weekday: false }))}, seules les séances prévues s'affichent.</span></p>` : ""}
        ${legend(view, options)}`;
    };

    const show = async () => {
      const mine = ++ticket;
      note = "";
      box.classList.remove("is-loading");
      const { start, end } = bounds(view, anchor);
      const full = view !== "annee";
      if (!covered(start, end, full) && options.fetchRange) {
        draw();
        box.classList.add("is-loading");
        try {
          const data = await options.fetchRange(F.isoDate(start), F.isoDate(end));
          keep(data, !full && (end - start) / 86400000 + 1 > 63);
        } catch (err) {
          note = /not found|inconnue|ne répond pas comme un relais/i.test(err.message || "") // relais d'avant la 0.8.3b5
            ? "Ce relais ne donne que les neuf semaines autour d'aujourd'hui : il faut le mettre à jour pour voir les autres périodes."
            : `Lecture du relais impossible : ${err.message}`;
        }
        if (mine !== ticket) return;
        box.classList.remove("is-loading");
      }
      draw();
    };

    box.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-cal-view], [data-cal-step], [data-cal-today], [data-cal-day], [data-cal-month]");
      if (!btn) return;
      if (btn.dataset.calView) {
        view = btn.dataset.calView;
        store(VIEW_KEY, view);
      } else if (btn.dataset.calStep) anchor = shift(view, anchor, Number(btn.dataset.calStep));
      else if (btn.hasAttribute("data-cal-today")) anchor = today;
      else if (btn.dataset.calDay) { view = "semaine"; anchor = btn.dataset.calDay; store(VIEW_KEY, view); }
      else if (btn.dataset.calMonth) { view = "mois"; anchor = btn.dataset.calMonth; store(VIEW_KEY, view); }
      show();
    });
    show();
  });
}
