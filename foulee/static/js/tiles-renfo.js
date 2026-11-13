// Tuiles « renfo » : muscles travaillés sur la période (carte du corps), équilibre avant / arrière,
// exercices et leur progression, et les exercices de la séance choisie. D'après le résumé de Garmin Connect
// de chaque séance.
import * as api from "./api.js";
import { bodyMap, legend } from "./bodymap.js";
import * as F from "./format.js";
import { message } from "./tiles-data.js";

const NO_SESSION = "Pas encore de séance de renfo. Sur ta montre, lance une activité « Musculation » et choisis "
  + "l'exercice à chaque série (ou suis un entraînement de renfo) : tes exercices arrivent ici avec la synchro.";
const NO_DETAIL = "Pas de détail d'exercices pour cette séance. Sur la montre, choisis l'exercice à chaque série "
  + "(ou suis un entraînement de renfo), ou complète la séance dans l'appli Garmin Connect : la synchro suivante "
  + "le reprendra.";

function figure(label, value, unit = "") {
  return `<div><div class="figure-label">${F.escape(label)}</div><div class="figure-value">${value}${unit ? `<small>${F.escape(unit)}</small>` : ""}</div></div>`;
}

function kg(value) {
  return F.isNum(value) ? `${F.dec1(value).replace(/,0$/, "")} kg` : "";
}

function series(value) {
  return `${F.dec1(value).replace(/,0$/, "")} série${value >= 2 ? "s" : ""}`;
}

/** « 3 × 10 », « 2 × 40 s », « 64 rép. en 10 séries ». */
function setsText(e) {
  const d = e.detail || {};
  if (d.mode === "temps") return `${e.series} × ${F.duration(d.par_serie_s)}`;
  if (d.par_serie) return `${e.series} × ${d.par_serie}`;
  if (e.repetitions) return `${F.int(e.repetitions)} rép. en ${e.series} séries`;
  return series(e.series);
}

function num(v) {
  return F.dec1(v).replace(/,0$/, "");
}

/** La famille de l'exercice dans l'équilibre avant / arrière : « Avant · dominante genou »… */
function chainTag(c) {
  if (!c) return '<span class="chain-tag is-none" title="Ni devant ni derrière : échauffement, cardio ou exercice non précisé">non compté</span>';
  const text = c.chaine === "mixte" ? "Corps entier, ½ devant ½ derrière" : c.chaine === "neutre" ? c.nom
    : `${c.chaine_nom} · ${c.nom.toLowerCase()}`;
  const tip = c.chaine === "neutre" ? "Latéral et rotation : compté à part, ni devant ni derrière"
    : `Équilibre avant / arrière : ${text}`;
  return `<span class="chain-tag is-${c.chaine}" title="${F.escape(tip)}">${F.escape(text)}</span>`;
}

function musclesText(e) {
  if (e.inconnu) return F.escape("Pas choisi sur la montre : compte dans les séries, pas dans les muscles");
  const main = e.muscles.filter((m) => m.role === "principal").map((m) => m.nom);
  const other = e.muscles.filter((m) => m.role !== "principal").map((m) => m.nom.toLowerCase());
  if (!main.length && !other.length) return "";
  return `${main.join(", ")}${other.length ? `${main.length ? " · " : ""}<span>${F.escape(other.join(", "))}</span>` : ""}`;
}

const MUSCLES_SHOWN = 8;  // au-delà, les muscles les moins travaillés tiennent sur une ligne

/** Les muscles du plus au moins travaillé, avec une barre ; puis ceux que la période a laissés de côté. */
function musclesList(scores, names) {
  const worked = Object.entries(scores).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const max = worked.length ? worked[0][1] : 1;
  const cut = worked.length > MUSCLES_SHOWN + 1 ? MUSCLES_SHOWN : worked.length;
  const more = worked.slice(cut).map(([m, v]) => `${(names[m] || m).toLowerCase()} (${series(v)})`);
  const rest = Object.keys(names).filter((k) => !scores[k]).map((k) => names[k].toLowerCase());
  return `<ol class="rf-muscles">${worked.slice(0, cut).map(([m, v]) => `<li><span class="rf-mname">${F.escape(names[m] || m)}</span>
      <span class="rf-bar"><i style="width:${Math.max(4, (v / max) * 100)}%"></i></span><span class="rf-mval">${F.escape(series(v))}</span></li>`).join("")}</ol>
    ${more.length ? `<p class="rf-rest">Aussi : ${F.escape(more.join(", "))}.</p>` : ""}
    ${rest.length && worked.length ? `<p class="rf-rest">Pas travaillés : ${F.escape(rest.join(", "))}.</p>` : ""}`;
}

/** Séances de renfo par semaine (12 dernières semaines), avec la ligne d'objectif. */
function weeksChart(weeks, goal) {
  const top = Math.max(goal || 0, 1, ...weeks.map((w) => w.seances));
  const reached = goal ? weeks.filter((w) => w.seances >= goal).length : null;
  const goalText = goal ? `<span><i class="rf-goal-key" aria-hidden="true"></i>Objectif ${goal} par semaine : atteint ${reached} semaine${reached > 1 ? "s" : ""} sur ${weeks.length}</span>` : "";
  const bars = weeks.map((w, i) => {
    const h = (w.seances / top) * 100;
    const ok = goal && w.seances >= goal;
    const label = `Semaine du ${F.dateLong(w.debut, { weekday: false })} : ${w.seances} séance${w.seances > 1 ? "s" : ""}${w.series ? `, ${w.series} séries` : ""}`;
    return `<div class="rf-week${ok ? " ok" : ""}${i === weeks.length - 1 ? " now" : ""}" title="${F.escape(label)}">
        ${w.seances ? `<span class="rf-week-bar" style="height:${Math.max(10, h)}%"><b>${w.seances}</b></span>` : ""}</div>`;
  }).join("");
  const line = goal ? `<span class="rf-goal" style="bottom:${(goal / top) * 100}%" aria-hidden="true"></span>` : "";
  return `<div class="rf-weeks-head"><span>Séances par semaine</span>${goalText}</div>
    <div class="rf-weeks" style="--n:${weeks.length}" role="img" aria-label="${F.escape(`Séances de renfo par semaine, ${weeks.length} dernières semaines : ${weeks.map((w) => w.seances).join(", ")}`)}">
      ${line}${bars}</div>
    <div class="rf-weeks-axis"><span>${F.escape(F.dateShort(weeks[0].debut))}</span><span>cette semaine</span></div>`;
}

// ------------------------------------------------------------- muscles travaillés
export const renfo = {
  title: () => "Renfo : muscles travaillés",
  async render(body, p, ctx) {
    const { start, end, days } = ctx.period(p);
    const d = await ctx.get("/api/renfo", { start, end });
    ctx.sub(`${days} derniers jours`);
    if (!d.nb_seances && !d.semaines.some((w) => w.seances)) return message(body, NO_SESSION);
    const goal = Number(p.objectif) || 0;
    const perWeek = d.nb_seances / Math.max(1, days / 7);
    body.classList.add("scroll");
    body.innerHTML = `<div class="rf">
        <div class="rf-side">
          <div class="figures rf-figures">
            ${figure("Séances", F.int(d.nb_seances))}
            ${days >= 14 ? figure("Par semaine", F.dec1(perWeek).replace(/,0$/, "")) : ""}
            ${figure("Séries", F.int(d.series))}
            ${d.tonnage_kg ? figure("Tonnage", F.int(d.tonnage_kg), "kg") : figure("Répétitions", F.int(d.repetitions))}
            ${d.effort_s ? figure("Temps d'effort", F.escape(F.duration(d.effort_s))) : ""}
          </div>
          <div class="rf-block">${weeksChart(d.semaines, goal)}</div>
          <div class="rf-block">
            <h3 class="rf-h">Séries par muscle</h3>
            ${Object.keys(d.muscles).length ? musclesList(d.muscles, d.noms_muscles)
              : `<p class="rf-rest">Aucun exercice détaillé sur la période : choisis l'exercice à chaque série sur ta montre.</p>`}
            <p class="rf-note">Une série compte pour 1 sur un muscle principal, pour ½ sur un muscle secondaire.</p>
          </div>
        </div>
        <div class="rf-map">${bodyMap(d.muscles, d.noms_muscles)}${legend()}</div>
      </div>`;
  },
};

// ------------------------------------------------------------- équilibre avant / arrière
// Échelle : la part des séries faites « derrière » (rapport 1:x ↔ x / (1 + x)), de tout à l'avant à tout à
// l'arrière. Cible du coureur : de 1:1 (50 %) à 1:2 (67 %).
const ZONES = [["avant", 0, 4 / 9], ["proche", 4 / 9, 0.5], ["cible", 0.5, 2 / 3], ["arriere", 2 / 3, 0.8],
  ["arriere_fort", 0.8, 1]];
const TICKS = [[1 / 3, "1:0,5"], [0.5, "1:1"], [2 / 3, "1:2"], [0.8, "1:4"]];

function beam(b, { compact = false } = {}) {
  const share = b.part_arriere;
  const zones = ZONES.map(([z, from, to]) => `<span class="eq-z z-${z}" style="left:${(from * 100).toFixed(2)}%;width:${((to - from) * 100).toFixed(2)}%">${z === "cible" && !compact ? "<em>cible</em>" : ""}</span>`).join("");
  const ticks = TICKS.map(([v, label]) => `<span class="eq-tick" style="left:${(v * 100).toFixed(2)}%"><b>${label}</b></span>`).join("");
  const knob = F.isNum(share) ? `<i class="eq-knob z-${b.zone}" style="left:${(share * 100).toFixed(2)}%"></i>` : "";
  const aria = `Équilibre ${b.ratio_texte} : ${num(b.avant)} séries devant, ${num(b.arriere)} derrière, ${b.verdict.toLowerCase()}. Cible du coureur : de 1:1 à 1:2.`;
  return `<div class="eq-beam${compact ? " compact" : ""}" role="img" aria-label="${F.escape(aria)}">
      <div class="eq-track">${zones}<span class="eq-ticklines">${ticks}</span>${knob}</div>
      <div class="eq-ends"><span>‹ plus d'avant</span><span>plus d'arrière ›</span></div>
    </div>`;
}

function headline(b, { compact = false } = {}) {
  return `<div class="eq-head${compact ? " compact" : ""}">
      <span class="eq-ratio" title="${F.escape(`Rapport avant : arrière, en séries. ${b.explication}`)}">${F.escape(b.ratio_texte || "–")}</span>
      <span class="eq-pill z-${b.zone}" title="${F.escape(b.explication)}">${F.escape(b.verdict)}</span>
    </div>
    <div class="eq-counts"><b>${num(b.avant)}</b> série${b.avant >= 2 ? "s" : ""} devant · <b>${num(b.arriere)}</b> derrière${b.neutre ? ` · <span title="Latéral et rotation : comptées à part">${num(b.neutre)} sur le côté</span>` : ""}</div>`;
}

/** Les paires du repère 1:1 (genou / hanche, poussée / tirage…), en ailes de papillon autour de l'axe. */
function pairs(b) {
  const rows = [...b.paires];
  if (b.mixte) {
    rows.push({ cle: "mixte", nom: "Corps entier", penche: null, avant: { nom: "½ devant", court: "½ devant", series: b.mixte / 2 },
      arriere: { nom: "½ derrière", court: "½ derrière", series: b.mixte / 2 } });
  }
  const max = Math.max(1, ...rows.flatMap((r) => [r.avant.series, r.arriere.series]));
  // la barre, à l'échelle de la plus longue, laisse toujours la place de son étiquette
  const side = (cls, v, name) => `<div class="eq-side ${cls}${v ? "" : " is-zero"}">
      ${v ? `<span class="eq-bar" style="--k:${Math.max(0.02, v / max).toFixed(3)}"></span>` : ""}
      <span class="eq-lab"><b>${num(v)}</b><i> ${F.escape(name.toLowerCase())}</i></span></div>`;
  const tip = (r) => {
    if (r.cle === "mixte") return "Exercices « corps entier » : ½ série devant, ½ série derrière";
    const lean = { avant: "penche vers l'avant", arriere: "penche vers l'arrière", equilibre: "équilibré" }[r.penche] || "trop peu de séries pour juger";
    return `${r.nom} : ${num(r.avant.series)} ${r.avant.nom.toLowerCase()}, ${num(r.arriere.series)} ${r.arriere.nom.toLowerCase()}${r.ratio_texte ? ` (${r.ratio_texte})` : ""}, ${lean}`;
  };
  return `<div class="eq-pairs">
      <div class="eq-row eq-pairs-head"><span></span><span class="eq-front">Avant</span><span class="eq-back">Arrière</span></div>
      ${rows.map((r) => `<div class="eq-row${r.penche === "avant" ? " leans" : ""}" title="${F.escape(tip(r))}">
          <div class="eq-pname">${F.escape(r.nom)}<small class="eq-pfam">${F.escape(`${r.avant.court} / ${r.arriere.court}`)}</small>${r.penche === "avant" ? '<em>penche vers l\'avant</em>' : ""}</div>
          ${side("eq-front", r.avant.series, r.avant.court)}
          ${side("eq-back", r.arriere.series, r.arriere.court)}
        </div>`).join("")}
    </div>`;
}

function balanceNotes(b, exercises = []) {
  const names = (family) => [...new Set(exercises.filter((e) => e.chaine?.famille === family).map((e) => e.nom.toLowerCase()))];
  const lateral = names("lateral");
  const out = [];
  if (b.neutre) {
    out.push(`<b>${num(b.neutre)} série${b.neutre >= 2 ? "s" : ""} sur le côté</b>, comptées à part, ni devant ni derrière${lateral.length ? ` : ${F.escape(lateral.slice(0, 3).join(", "))}${lateral.length > 3 ? "…" : ""}` : ""}.`);
  }
  if (b.non_comptees) out.push(`${num(b.non_comptees)} série${b.non_comptees >= 2 ? "s" : ""} pas comptée${b.non_comptees >= 2 ? "s" : ""} : échauffement, cardio ou exercice non précisé.`);
  return out.length ? `<p class="eq-notes">${out.join(" ")}</p>` : "";
}

/** Semaine après semaine : la part des séries faites derrière, face à la bande de la cible (1:1 à 1:2). */
function weeksBalance(weeks) {
  const lo = 0.2;
  const hi = 0.9;  // de 1:0,25 à 1:9 ; au-delà, le point reste au bord
  const y = (v) => ((hi - Math.max(lo, Math.min(hi, v))) / (hi - lo)) * 100;
  const counted = weeks.filter((w) => F.isNum(w.equilibre?.part_arriere));
  const inside = counted.filter((w) => w.equilibre.zone === "cible").length;
  const dots = weeks.map((w, i) => {
    const e = w.equilibre;
    if (!e || !F.isNum(e.part_arriere)) return "";
    const tip = `Semaine du ${F.dateLong(w.debut, { weekday: false })} : ${e.ratio_texte}, ${num(e.avant)} série${e.avant >= 2 ? "s" : ""} devant, ${num(e.arriere)} derrière (${e.verdict.toLowerCase()})`;
    return `<i class="eq-wdot z-${e.zone}${i === weeks.length - 1 ? " now" : ""}" style="left:${(((i + 0.5) / weeks.length) * 100).toFixed(2)}%;top:${y(e.part_arriere).toFixed(2)}%" title="${F.escape(tip)}"></i>`;
  }).join("");
  const labels = [[0.8, "1:4"], [2 / 3, "1:2"], [0.5, "1:1"], [1 / 3, "1:0,5"]]
    .map(([v, t]) => `<span style="top:${y(v).toFixed(2)}%">${t}</span>`).join("");
  return `<div class="eq-weeks-head"><span>Semaine après semaine</span>${counted.length ? `<span>dans la cible ${inside} semaine${inside > 1 ? "s" : ""} sur ${counted.length}</span>` : ""}</div>
    <div class="eq-weeks">
      <div class="eq-wlabels" aria-hidden="true">${labels}</div>
      <div class="eq-wplot" role="img" aria-label="${F.escape(`Équilibre avant / arrière par semaine, ${weeks.length} dernières semaines : ${weeks.map((w) => w.equilibre?.ratio_texte || "pas de série comptée").join(", ")}`)}">
        <span class="eq-wband" style="top:${y(2 / 3).toFixed(2)}%;height:${(y(0.5) - y(2 / 3)).toFixed(2)}%"></span>
        <span class="eq-wline" style="top:${y(0.5).toFixed(2)}%"></span>
        ${dots}
      </div>
    </div>
    <div class="rf-weeks-axis eq-waxis"><span>${F.escape(F.dateShort(weeks[0].debut))}</span><span>cette semaine</span></div>`;
}

function balanceBlock(b) {
  if (!b || b.zone === "vide") return "";
  return `<div class="rf-block eq-mini">
      <h3 class="rf-h">Équilibre avant / arrière de la séance</h3>
      ${headline(b, { compact: true })}
      ${beam(b, { compact: true })}
      ${b.conseil ? `<p class="eq-advice">${F.escape(b.conseil)}</p>` : ""}
    </div>`;
}

export const renfo_equilibre = {
  title: () => "Renfo : équilibre avant / arrière",
  async render(body, p, ctx) {
    const { start, end, days } = ctx.period(p);
    const d = await ctx.get("/api/renfo", { start, end });
    ctx.sub(`${days} derniers jours · cible du coureur : 1:1 à 1:2`);
    if (!d.nb_seances && !d.semaines.some((w) => w.seances)) return message(body, NO_SESSION);
    const b = d.equilibre;
    body.classList.add("scroll", "eq-body");
    const main = b.zone === "vide"
      ? `<p class="eq-empty">${F.escape(d.exercices.length ? "Aucune série à ranger devant ou derrière sur la période : seulement de l'échauffement, du cardio, du latéral ou des exercices non précisés." : NO_DETAIL)}</p>`
      : `${headline(b)}${beam(b)}${b.conseil_court ? `<p class="eq-advice">${F.escape(b.conseil_court)}</p>` : ""}`;
    body.innerHTML = `<div class="eq">
        <section class="eq-main">${main}</section>
        <section class="eq-detail">${b.zone === "vide" ? "" : pairs(b)}${balanceNotes(b, d.exercices)}</section>
        <section class="eq-trend">${weeksBalance(d.semaines)}</section>
      </div>`;
  },
};

// ------------------------------------------------------------- exercices et progression
/** Ce qui progresse : la charge si l'exercice en a, sinon les répétitions ou la durée par série. */
function trackOf(e) {
  const h = e.historique;
  if (h.some((x) => x.charge_kg)) return { key: "charge_kg", fmt: kg, label: "charge" };
  if (h.some((x) => x.par_serie)) return { key: "par_serie", fmt: (v) => `${F.int(v)} rép.`, label: "répétitions par série" };
  if (h.some((x) => x.par_serie_s)) return { key: "par_serie_s", fmt: (v) => F.duration(v), label: "durée par série" };
  return null;
}

function sparkline(points) {
  const values = points.filter(F.isNum);
  if (values.length < 2) return "";
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const w = 96;
  const h = 26;
  const xs = points.map((_, i) => 3 + (i / (points.length - 1)) * (w - 6));
  const y = (v) => (hi === lo ? h / 2 : h - 4 - ((v - lo) / (hi - lo)) * (h - 8));
  const path = points.map((v, i) => (F.isNum(v) ? `${xs[i].toFixed(1)},${y(v).toFixed(1)}` : null)).filter(Boolean).join(" ");
  const last = points.length - 1;
  return `<svg class="rf-spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
      <polyline points="${path}"/><circle cx="${xs[last].toFixed(1)}" cy="${y(points[last]).toFixed(1)}" r="2.6"/></svg>`;
}

export const renfo_exercices = {
  title: () => "Renfo : exercices et progression",
  async render(body, p, ctx) {
    const { start, end, days } = ctx.period(p);
    const d = await ctx.get("/api/renfo", { start, end });
    ctx.sub(`${days} derniers jours`);
    if (!d.exercices.length) return message(body, d.nb_seances ? NO_DETAIL : NO_SESSION);
    body.classList.add("scroll");
    const rows = d.exercices.map((e) => {
      const track = trackOf(e);
      const values = track ? e.historique.map((x) => x[track.key] ?? null) : [];
      const first = values.find(F.isNum);
      const last = [...values].reverse().find(F.isNum);
      const lastSession = e.historique[e.historique.length - 1];
      let change = "";
      if (track && F.isNum(first) && F.isNum(last) && values.filter(F.isNum).length > 1) {
        change = first === last ? `<span class="rf-same">${F.escape(track.fmt(last))}</span>`
          : `<span class="${last > first ? "rf-up" : "rf-down"}">${F.escape(track.fmt(first))} → ${F.escape(track.fmt(last))}</span>`;
      } else if (track && F.isNum(last)) {
        change = `<span class="rf-same">${F.escape(track.fmt(last))}</span>`;
      }
      const lastText = `${setsText({ ...e, series: lastSession.series, repetitions: lastSession.repetitions, detail: { mode: lastSession.par_serie_s ? "temps" : "reps", par_serie: lastSession.par_serie, par_serie_s: lastSession.par_serie_s } })}${lastSession.charge_kg ? ` · ${kg(lastSession.charge_kg)}` : ""}`;
      const counts = `${F.int(e.seances)} séance${e.seances > 1 ? "s" : ""} · ${series(e.series)}`;
      return `<tr class="clickable" tabindex="0" data-id="${F.escape(lastSession.seance_id)}" title="Ouvrir la dernière séance avec cet exercice">
          <td class="wrap rf-c-main"><div class="rf-ex">${F.escape(e.nom)}</div><div class="rf-ex-m">${chainTag(e.chaine)} ${musclesText(e)}</div>
            <div class="rf-ex-m rf-narrow">${F.escape(counts)}</div></td>
          <td class="num rf-c-hide">${F.int(e.seances)}</td>
          <td class="num rf-c-hide">${F.int(e.series)}</td>
          <td class="num rf-c-top"><div>${F.escape(lastText)}</div><div class="rf-ex-m">${F.escape(F.dateShort(e.derniere))}</div></td>
          <td class="rf-c-bottom">${track ? `<div class="rf-evo" title="${F.escape(`Évolution : ${track.label}`)}">${sparkline(values)}<span>${change}</span></div>` : "–"}</td>
        </tr>`;
    }).join("");
    body.innerHTML = `<table class="table rf-table rf-cards"><thead><tr><th>Exercice</th><th class="num">Séances</th><th class="num">Séries</th>
        <th class="num">Dernière séance</th><th>Évolution</th></tr></thead><tbody>${rows}</tbody></table>`;
    body.querySelectorAll("tr[data-id]").forEach((tr) => {
      const open = () => ctx.openActivity(tr.dataset.id);
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", (ev) => { if (ev.key === "Enter") open(); });
    });
  },
};

// ------------------------------------------------------------- séance : exercices
export const seance_renfo = {
  title: () => "Exercices de renfo",
  async render(body, p, ctx) {
    const a = await ctx.activityDetail();
    if (!a) return message(body, "Choisis une séance en haut de la vue.");
    const r = a.renfo;
    if (!r) {
      ctx.hide?.();  // séance sans renfo : la tuile s'efface (elle reste visible en modification de la vue)
      return message(body, "Pas d'exercices de renfo pour cette séance.");
    }
    if (!r.exercices.length) return message(body, NO_DETAIL);
    ctx.sub(`${r.exercices.length} exercice${r.exercices.length > 1 ? "s" : ""}`);
    body.classList.add("scroll");
    const rows = r.exercices.map((e) => `<tr>
        <td class="wrap rf-c-main"><div class="rf-ex">${F.escape(e.nom)}</div><div class="rf-ex-m">${chainTag(e.chaine)} ${musclesText(e)}</div></td>
        <td class="num rf-c-top">${F.escape(setsText(e))}</td>
        <td class="num rf-c-bottom">${e.charge_max_kg ? F.escape(kg(e.charge_max_kg)) : `<span class="rf-muted">poids du corps</span>`}</td>
        <td class="num rf-c-hide">${e.tonnage_kg ? F.escape(`${F.int(e.tonnage_kg)} kg`) : "–"}</td>
        <td class="num rf-c-hide">${F.escape(F.duration(e.duree_s))}</td></tr>`).join("");
    body.innerHTML = `<div class="rf rf--seance">
        <div class="rf-side">
          <div class="figures rf-figures">
            ${figure("Séries", F.int(r.series))}
            ${figure("Répétitions", F.int(r.repetitions))}
            ${r.tonnage_kg ? figure("Tonnage", F.int(r.tonnage_kg), "kg") : ""}
            ${r.effort_s ? figure("Temps d'effort", F.escape(F.duration(r.effort_s))) : ""}
          </div>
          ${balanceBlock(r.equilibre)}
          <table class="table rf-table rf-cards"><thead><tr><th>Exercice</th><th class="num">Séries</th><th class="num">Charge</th>
            <th class="num">Tonnage</th><th class="num">Effort</th></tr></thead><tbody>${rows}</tbody></table>
        </div>
        <div class="rf-map">${bodyMap(r.muscles, r.noms_muscles)}${legend()}</div>
      </div>`;
  },
};

