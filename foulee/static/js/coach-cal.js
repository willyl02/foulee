// Le grand calendrier des pages coach et élève : neuf semaines (quatre passées, celle-ci, quatre à venir), une
// case par jour avec les séances prévues (son plan, celles du coach) et leur esquisse, les séances faites
// (un clic ouvre la séance) et les courses visées (objectif principal et secondaires).
import * as F from "./format.js";
import { icon } from "./icons.js";
import { sketchSVG } from "./sketch.js";

const DOW = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

function km(m) { return m ? `${F.dec1(m / 1000)} km` : ""; }

/**
 * mois : {debut, fin, jours: [{date, prevu: [...], fait: [...]}]} (relais) ; goals : [{nom, date}] ;
 * sessionHref(s) : lien d'une séance faite ; coachSide : « proposée par toi » plutôt que « par ton coach ».
 */
export function monthCalendar(mois, { vma = null, goals = [], sessionHref, coachSide = false } = {}) {
  if (!mois?.jours?.length) return "";
  const today = F.isoDate(new Date());
  const races = new Map((goals || []).filter((g) => g?.date).map((g) => [g.date, g]));
  const cells = mois.jours.map((day) => {
    const d = F.parseDate(day.date);
    const race = races.get(day.date);
    const races2 = day.prevu.filter((p) => p.type === "course" && !race);
    const planned = day.prevu.filter((p) => p.type !== "course" || race).filter((p) => !(race && p.type === "course")).map((p) => {
      const state = p.statut === "fait" ? "done" : p.statut === "manque" ? "miss" : "next";
      const who = p.source === "coach" ? (coachSide ? "proposée par toi" : "de ton coach") : coachSide ? "son plan" : "ton plan";
      return `<div class="cc-pl ${state}${p.source === "coach" ? " coach" : ""}" title="${F.escape(`${p.titre} (${who})`)}">
        <span class="cc-pl-t">${p.statut === "fait" ? icon("check") : p.statut === "manque" ? icon("close") : ""}<span class="cc-txt">${F.escape(p.titre)}</span></span>
        ${p.blocs?.length && p.statut !== "manque" ? sketchSVG(p.blocs, { vma, height: 14, approx: p.esquisse_approchee }) : ""}</div>`;
    }).join("");
    const done = day.fait.map((s) => `<a class="cc-done" href="${sessionHref(s)}" title="${F.escape(s.nom || s.sport_label || "Séance")}">
        ${F.escape([km(s.distance_m) || (s.duree_s ? F.duration(s.duree_s, { short: true }) : ""), s.nom || s.sport_label].filter(Boolean).join(" · "))}</a>`).join("");
    const cls = ["cc-day", day.date === today ? "today" : "", day.date < today ? "past" : "", race || races2.length ? "race" : "",
      d.getDate() === 1 ? "first" : ""].filter(Boolean).join(" ");
    const label = d.getDate() === 1 || day === mois.jours[0] ? `${d.getDate()} ${MONTHS[d.getMonth()]}` : `${d.getDate()}`;
    return `<div class="${cls}"><div class="cc-num">${F.escape(label)}</div>
      ${race ? `<div class="cc-race">${icon("flag")}${F.escape(race.nom || "Course")}</div>` : ""}${races2.map((p) => `<div class="cc-race">${icon("flag")}${F.escape(p.titre)}</div>`).join("")}${planned}${done}</div>`;
  }).join("");
  return `<div class="cc">
    <div class="cc-grid">${DOW.map((d) => `<span class="cc-dow">${d}</span>`).join("")}${cells}</div>
    <div class="cc-legend"><span class="cc-pl next coach">${coachSide ? "proposée par toi" : "de ton coach"}</span><span class="cc-pl next">${coachSide ? "son plan" : "ton plan"}</span>
      <span class="cc-pl done">${icon("check")}faite</span><span class="cc-pl miss">${icon("close")}manquée</span><span class="cc-done">séance faite</span>
      <span class="cc-race">${icon("flag")}course visée</span></div>
  </div>`;
}

// Replié ou déplié : retenu dans ce navigateur, pour les deux pages (fiche de l'élève, « Mon coach »)
const FOLD_KEY = "foulee-calendrier-replie";
function folded() {
  try { return localStorage.getItem(FOLD_KEY) === "1"; } catch (e) { return false; }
}
document.addEventListener("toggle", (e) => {
  if (!e.target.matches?.("details.co-cal")) return;
  try { localStorage.setItem(FOLD_KEY, e.target.open ? "0" : "1"); } catch (err) { /* rien à retenir */ }
}, true);

/** La carte entière : titre, chevron pour la replier (état retenu), et le calendrier. */
export function calendarCard(title, sub, mois, options) {
  const body = monthCalendar(mois, options);
  if (!body) return "";
  return `<details class="coach-card co-cal"${folded() ? "" : " open"}><summary><h2>${icon("calendar")}${F.escape(title)}${sub ? ` <span class="co-sub">${F.escape(sub)}</span>` : ""}</h2>
    <span class="co-fold" title="Replier ou déplier le calendrier" aria-hidden="true">${icon("chevron")}</span></summary>${body}</details>`;
}
