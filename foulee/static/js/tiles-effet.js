// Tuile « Séance : effet d'entraînement » : l'effet aérobie et l'effet anaérobie de Garmin (Training Effect,
// de 0 à 5) en deux jauges aux couleurs de Garmin Connect, l'avantage principal de la séance, et sa place
// parmi les séances du même sport des 4 semaines précédentes (les petits traits autour des jauges).
import * as F from "./format.js";
import { message } from "./tiles-data.js";

// Niveaux de Garmin : [début et fin sur la jauge, clé, libellé, valeurs] ; 5,0 (« effort trop soutenu ») est le
// petit bout rouge au bout de l'échelle
const LEVELS = [
  [0, 1, "aucun", "Aucune amélioration", "0 à 0,9"], [1, 2, "faible", "Faible avantage", "1,0 à 1,9"],
  [2, 3, "maintien", "Maintien", "2,0 à 2,9"], [3, 4, "impact", "Impact", "3,0 à 3,9"],
  [4, 4.9, "fort", "Fort impact", "4,0 à 4,9"], [4.9, 5, "surcharge", "Effort trop soutenu", "5,0"],
];
const KINDS = {
  aerobie: { title: "Effet aérobie", adj: "aérobie", help: "Travail de l'endurance : ce que la séance apporte à ta capacité aérobie." },
  anaerobie: { title: "Effet anaérobie", adj: "anaérobie", help: "Efforts brefs et très intenses : ce que la séance apporte à ta vitesse et à ta puissance." },
};

// Géométrie de la jauge : arc de 240° ouvert en bas (angles « horloge », 0° = midi)
const CX = 100;
const CY = 88;
const R = 68;
const SPAN = 240;
const GAP = 0.04;  // petit jour entre deux niveaux (en points d'effet)

const angle = (v) => -SPAN / 2 + (SPAN * Math.max(0, Math.min(5, v))) / 5;
function point(a, r = R) {
  const rad = (a * Math.PI) / 180;
  return [CX + r * Math.sin(rad), CY - r * Math.cos(rad)];
}
function arc(v1, v2, r = R) {
  const a1 = angle(v1);
  const a2 = angle(v2);
  const [x1, y1] = point(a1, r);
  const [x2, y2] = point(a2, r);
  return `M${x1.toFixed(2)} ${y1.toFixed(2)}A${r} ${r} 0 ${a2 - a1 > 180 ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

/** Les petits traits des séances précédentes : leur valeur sur l'échelle (plus foncé là où elles s'accumulent). */
function rug(kind, sessions) {
  return sessions.filter((s) => F.isNum(s[kind])).map((s) => {
    const a = angle(s[kind]);
    const [x1, y1] = point(a, R + 10);
    const [x2, y2] = point(a, R + 17);
    return `<line class="te-rug" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"><title>${F.escape(`${F.dateShort(s.date)} · ${s.nom || "séance"} : ${F.dec1(s[kind])}`)}</title></line>`;
  }).join("");
}

function dial(kind, g, sessions) {
  const value = g ? g.valeur : null;
  const segments = LEVELS.map(([start, end, key, label, values], i) => {
    const s = i ? start + GAP : start;
    const e = i === LEVELS.length - 1 ? end : end - GAP;
    const lit = F.isNum(value) && value > s ? `<path class="te-fill l-${key}" d="${arc(s, Math.min(e, value))}"/>` : "";
    return `<path class="te-seg l-${key}" d="${arc(s, e)}"><title>${F.escape(`${values} : ${label}`)}</title></path>${lit}`;
  }).join("");
  const numbers = [1, 2, 3, 4].map((n) => {
    const [x, y] = point(angle(n), R - 19);
    return `<text class="te-num" x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}">${n}</text>`;
  }).join("");
  const [x0, y0] = point(angle(0), R);
  const [x5, y5] = point(angle(5), R);
  const ends = `<text class="te-num" x="${x0.toFixed(1)}" y="${(y0 + 19).toFixed(1)}">0</text><text class="te-num" x="${x5.toFixed(1)}" y="${(y5 + 19).toFixed(1)}">5</text>`;
  let knob = "";
  if (F.isNum(value)) {
    const [kx, ky] = point(angle(value), R);
    knob = `<circle class="te-knob l-${g.niveau}" cx="${kx.toFixed(2)}" cy="${ky.toFixed(2)}" r="8.5"/>`;
  }
  const label = g ? `${KINDS[kind].title} : ${F.dec1(value)} sur 5, ${g.libelle.toLowerCase()}` : `${KINDS[kind].title} : non mesuré`;
  return `<div class="te-dial${g ? "" : " is-empty"}">
      <svg viewBox="0 0 200 146" role="img" aria-label="${F.escape(label)}">${segments}${rug(kind, sessions)}${numbers}${ends}${knob}</svg>
      <div class="te-center" aria-hidden="true"><div class="te-value">${g ? F.escape(F.dec1(value)) : "–"}</div></div>
    </div>
    ${g ? `<div class="te-level l-${g.niveau}"><i aria-hidden="true"></i>${F.escape(g.libelle)}</div>` : '<div class="te-level is-none">Non mesuré</div>'}`;
}

function gauge(kind, g, sessions) {
  return `<figure class="te-gauge">
      <figcaption class="te-kind" title="${F.escape(KINDS[kind].help)}">${F.escape(KINDS[kind].title)}</figcaption>
      ${dial(kind, g, sessions)}
      <p class="te-text">${F.escape(g ? g.texte : "Pas mesuré par ta montre pour cette séance.")}</p>
    </figure>`;
}

/** « au-dessus de 9 de tes 14 séances de course et trail des 4 semaines précédentes (de 1,9 à 4,1) ». */
function rankText(s, sport) {
  const n = s.nombre;
  const range = s.min === s.max ? `toutes à ${F.dec1(s.min)}` : `de ${F.dec1(s.min)} à ${F.dec1(s.max)}`;
  const same = n - s.en_dessous - s.au_dessus;
  if (n === 1) return `une seule séance ${sport} les 4 semaines précédentes, à ${F.dec1(s.min)}.`;
  const yours = `tes ${n} séances ${sport} des 4 semaines précédentes`;
  if (s.en_dessous === n) return `au-dessus de toutes ${yours} (${range}).`;
  if (s.au_dessus === n) return `en dessous de toutes ${yours} (${range}).`;
  if (same === n) return `comme toutes ${yours} (${range}).`;
  if (s.au_dessus === 0) return `au plus haut de ${yours}, à égalité avec ${same} d'entre elles (${range}).`;
  if (s.en_dessous === 0) return `au plus bas de ${yours}, comme ${same} d'entre elles (${range}).`;
  return `au-dessus de ${s.en_dessous} de ${yours}${same ? `, au niveau de ${same}` : ""} (${range}).`;
}

function side(e) {
  const b = e.avantage;
  const ctx = e.contexte;
  const benefit = b ? `<div class="te-benefit fam-${b.famille}">
      <div class="te-side-h">Avantage principal</div>
      <div class="te-benefit-name"><i aria-hidden="true"></i><b>${F.escape(b.libelle)}</b><span>${F.escape(b.famille_libelle)}</span></div>
      <p>${F.escape(b.texte)}</p>
    </div>` : "";
  const ranks = ctx ? ["aerobie", "anaerobie"].filter((k) => ctx[k]).map((k) => `<li><b>${F.escape(KINDS[k].adj.charAt(0).toUpperCase() + KINDS[k].adj.slice(1))} :</b> ${F.escape(rankText(ctx[k], ctx.sport))}</li>`).join("") : "";
  const compare = ranks ? `<div class="te-compare">
      <div class="te-side-h">Par rapport à tes séances <span class="te-rug-key" aria-hidden="true"></span></div>
      <ul>${ranks}</ul>
    </div>` : `<p class="te-alone">Pas d'autre séance ${F.escape(ctx?.sport || "du même sport")} les 4 semaines précédentes pour comparer.</p>`;
  const load = F.isNum(e.charge_garmin) ? `<div class="te-load"><span>Charge d'entraînement Garmin</span><b>${F.int(e.charge_garmin)}</b></div>` : "";
  return `<div class="te-side">${benefit}${compare}${load}</div>`;
}

export const seance_effet = {
  title: () => "Effet d'entraînement",
  async render(body, p, ctx) {
    const a = await ctx.activityDetail();
    if (!a) return message(body, "Choisis une séance en haut de la vue.");
    const e = a.effet;
    if (!e) {
      ctx.hide?.();  // pas d'effet d'entraînement (séance Strava, montre sans cardio…) : la tuile s'efface
      return message(body, a.source === "strava"
        ? "Séance venue de Strava : l'effet d'entraînement n'existe que pour les séances enregistrées par une montre Garmin."
        : "Pas d'effet d'entraînement pour cette séance : Garmin le calcule à partir de la fréquence cardiaque enregistrée par ta montre.");
    }
    ctx.sub("Training Effect de Garmin, de 0 à 5");
    body.classList.add("te-body");
    const sessions = e.contexte?.seances || [];
    body.innerHTML = `<div class="te">
        ${gauge("aerobie", e.aerobie, sessions)}
        ${gauge("anaerobie", e.anaerobie, sessions)}
        ${side(e)}
      </div>`;
  },
};
