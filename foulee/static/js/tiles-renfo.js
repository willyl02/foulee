// Tuiles « renfo » : muscles travaillés sur la période (carte du corps), exercices et leur progression,
// et les exercices de la séance choisie. D'après le résumé de Garmin Connect de chaque séance.
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

function musclesText(e) {
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
    const d = await api.get("/api/renfo", { start, end });
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
    const d = await api.get("/api/renfo", { start, end });
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
          <td class="wrap rf-c-main"><div class="rf-ex">${F.escape(e.nom)}</div><div class="rf-ex-m">${musclesText(e)}</div>
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
        <td class="wrap rf-c-main"><div class="rf-ex">${F.escape(e.nom)}</div><div class="rf-ex-m">${musclesText(e)}</div></td>
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
          <table class="table rf-table rf-cards"><thead><tr><th>Exercice</th><th class="num">Séries</th><th class="num">Charge</th>
            <th class="num">Tonnage</th><th class="num">Effort</th></tr></thead><tbody>${rows}</tbody></table>
        </div>
        <div class="rf-map">${bodyMap(r.muscles, r.noms_muscles)}${legend()}</div>
      </div>`;
  },
};

