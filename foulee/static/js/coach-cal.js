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
        <span class="cc-pl-t">${p.statut === "fait" ? icon("check") : p.statut === "manque" ? icon("close") : ""}${F.escape(p.titre)}</span>
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
