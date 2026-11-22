// La fiche d'un élève (vue du coach) et la page d'une séance partagée, avec son fil (coach et élève).
import * as api from "./api.js";
import * as F from "./format.js";
import { analysisHTML, wireAnalysis } from "./fractions.js";
import { calendarCard, wireCalendar } from "./coach-cal.js";
import { levelChip } from "./coach-reglages.js";
import { icon } from "./icons.js";
import {
  avatar, blocksHtml, dayLabel, dur, km, loading, mountThread, rdel, rget, sessionFigures, sportIcon, statusChip, traceSvg,
  watchLine, watchSummary,
} from "./coach-ui.js";
import { beam, headline, pairs } from "./tiles-renfo.js";

const DOW = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function shareSummary(accord) {
  if (!accord) return "rien encore : il n'a pas choisi ce qu'il partage";
  const items = [accord.seances && "séances", accord.objectif && "objectif et VMA", accord.seances && accord.gps && (accord.masquer ? "tracés (départ et arrivée masqués)" : "tracés"),
    accord.sante && "sommeil et VFC", accord.poids && "poids", accord.zones && "zones cardio"].filter(Boolean);
  return items.length ? items.join(", ") : "rien";
}

// ------------------------------------------------------------------ zones cardio (réglages Garmin)
const ZONE_SPORTS = { DEFAULT: "Général", RUNNING: "Course à pied", CYCLING: "Vélo", SWIMMING: "Natation" };
const ZONE_METHODS = {
  HR_MAX_BASED: ["% de la FC max", "fc_max", "FC max"],
  HRR_BASED: ["% de la FC de réserve", "reserve", "FC de réserve"],
  LACTATE_THRESHOLD: ["% de la FC au seuil", "fc_seuil", "Seuil lactique"],
};

function zonePct(bpm, z) {
  const [, ref] = ZONE_METHODS[z.methode] || [];
  if (ref === "fc_max" && z.fc_max) return Math.round((bpm / z.fc_max) * 100);
  if (ref === "fc_seuil" && z.fc_seuil) return Math.round((bpm / z.fc_seuil) * 100);
  if (ref === "reserve" && z.fc_max && z.fc_repos) return Math.round(((bpm - z.fc_repos) / (z.fc_max - z.fc_repos)) * 100);
  return null;
}

/** Ce qui saute aux yeux d'un coach : pas de zones propres à la course, les mêmes partout, un écart avec Foulée. */
function zoneNotes(list, profil) {
  const notes = [];
  const run = list.find((z) => z.sport === "RUNNING");
  const base = list.find((z) => z.sport === "DEFAULT");
  const same = (a, b) => a && b && a.methode === b.methode && a.bornes.join() === b.bornes.join();
  if (!run) notes.push("Pas de zones propres à la course : la montre prend les zones générales en course à pied.");
  else if (same(run, base)) notes.push("La course utilise exactement les mêmes zones que le profil général.");
  const ref = run || base;
  if (ref && profil?.fc_max && ref.fc_max && Math.abs(profil.fc_max - ref.fc_max) >= 3) {
    notes.push(`FC max dans Foulée : ${F.int(profil.fc_max)}, dans Garmin : ${F.int(ref.fc_max)}.`);
  }
  if (ref && !ref.repos_auto && ref.methode === "HRR_BASED") notes.push("FC au repos fixée à la main (pas mise à jour par la montre).");
  return notes;
}

function zonesCard(list, profil, accord, name) {
  if (!accord?.zones) return "";
  if (!list?.length) {
    return `<section class="coach-card"><h2>${icon("heart")}Zones cardio</h2><p class="co-empty">${F.escape(name)} partage ses zones, mais rien n'est encore arrivé (une synchro Garmin de son côté suffit).</p></section>`;
  }
  const order = ["RUNNING", "DEFAULT"];
  const profiles = [...list].sort((a, b) => ((order.indexOf(a.sport) + 1) || 9) - ((order.indexOf(b.sport) + 1) || 9));
  const cols = profiles.map((z) => `<th>${F.escape(ZONE_SPORTS[z.sport] || z.sport.toLowerCase())}</th>`).join("");
  const cell = (z, i) => {
    const low = z.bornes[i];
    const high = i < 4 ? z.bornes[i + 1] - 1 : z.fc_max;
    const pct = zonePct(low, z);
    return `<td><b>${F.int(low)}${high ? `–${F.int(high)}` : "+"}</b>${pct != null ? `<small>${pct} %</small>` : ""}</td>`;
  };
  const row = (label, fn) => `<tr><th scope="row">${label}</th>${profiles.map((z) => `<td>${fn(z)}</td>`).join("")}</tr>`;
  const notes = zoneNotes(list, profil);
  return `<section class="coach-card co-zones"><h2>${icon("heart")}Zones cardio <span class="co-sub">réglages Garmin Connect</span></h2>
    <div class="co-zones-scroll"><table class="co-zones-table"><thead><tr><th></th>${cols}</tr></thead><tbody>
      ${row("Méthode", (z) => (ZONE_METHODS[z.methode] ? `<span title="Les % des zones : ${F.escape(ZONE_METHODS[z.methode][0])}">${F.escape(ZONE_METHODS[z.methode][2])}</span>` : "–"))}
      ${row("FC max", (z) => (z.fc_max ? F.int(z.fc_max) : "–"))}
      ${row("FC au repos", (z) => (z.fc_repos ? `${F.int(z.fc_repos)}${z.repos_auto ? " <small>auto</small>" : ""}` : "–"))}
      ${row("FC au seuil", (z) => (z.fc_seuil ? F.int(z.fc_seuil) : "–"))}
      ${[0, 1, 2, 3, 4].map((i) => `<tr class="co-zone-row"><th scope="row"><span class="co-zone-dot z${i + 1}"></span>Zone ${i + 1}</th>${profiles.map((z) => cell(z, i)).join("")}</tr>`).join("")}
    </tbody></table></div>
    ${notes.length ? `<ul class="co-zone-notes">${notes.map((n) => `<li>${icon("info")}<span>${F.escape(n)}</span></li>`).join("")}</ul>` : ""}
  </section>`;
}

function goalPace(goal) {
  const parts = String(goal?.temps_cible || "").split(":").map(Number);
  if (!goal?.distance_km || parts.some(Number.isNaN) || !parts.length) return null;
  const secs = parts.reduce((a, v) => a * 60 + v, 0);
  if (!secs) return null;
  const per = secs / goal.distance_km;
  return { pace: `${Math.floor(per / 60)}:${String(Math.round(per % 60)).padStart(2, "0")} /km`, kmh: goal.distance_km / (secs / 3600) };
}

function spark(values, { color = "var(--s1)" } = {}) {
  const pts = values.map((v, i) => [i, v]).filter((p) => F.isNum(p[1]));
  if (pts.length < 2) return "";
  const ys = pts.map((p) => p[1]);
  const [lo, hi] = [Math.min(...ys), Math.max(...ys)];
  const w = 120;
  const h = 30;
  const x = (i) => (i / Math.max(1, values.length - 1)) * (w - 4) + 2;
  const y = (v) => h - 3 - ((v - lo) / (hi - lo || 1)) * (h - 6);
  return `<svg class="co-spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join("")}" style="stroke:${color}"/></svg>`;
}

function dayCell(day, sid) {
  const today = F.isoDate(new Date());
  const d = F.parseDate(day.date);
  const planned = day.prevu.map((p) => {
    const cls = p.source === "coach" ? "coach" : "";
    const state = p.statut === "fait" ? "done-plan" : p.statut === "manque" ? "miss" : "next";
    return `<div class="co-pl ${cls} ${state}" title="${F.escape(`${p.source === "coach" ? "Proposée par toi" : "Son plan"} : ${p.titre}`)}">
      ${p.statut === "fait" ? icon("check") : ""}${F.escape(p.titre)}<small>${p.source === "coach" ? "proposée" : "son plan"}${p.statut === "manque" ? " · manquée" : ""}</small></div>`;
  }).join("");
  const done = day.fait.map((s) => `<a class="co-pl done" href="#/coach/eleve/${sid}/seance/${encodeURIComponent(s.cle)}">${F.escape(s.nom || s.sport_label || "Séance")}
      <small>${F.escape([km(s.distance_m), dur(s.duree_s)].filter(Boolean).join(" · "))}</small></a>`).join("");
  return `<div class="co-day${day.date === today ? " today" : ""}${day.date > today ? " future" : ""}"><h4>${DOW[(d.getDay() + 6) % 7]} ${d.getDate()}</h4>${done}${planned}</div>`;
}

function sessionRow(s, href) {
  return `<a class="co-sess" href="${href}"><span class="co-ico">${sportIcon(s.sport)}</span>
    <div><b>${F.escape(s.nom || s.sport_label || "Séance")}</b><div class="co-meta">${F.escape([dayLabel(s.date), sessionFigures(s)].filter(Boolean).join(" · "))}</div>
      ${s.note ? `<div class="co-feel">« ${F.escape(s.note)} »</div>` : ""}</div>
    <span class="co-sess-tail">${s.trace ? `<span class="co-chip" title="Tracé GPS partagé">${icon("map")}</span>` : ""}${s.messages ? `<span class="co-chip">${icon("chat")}${s.messages}</span>` : ""}${icon("right")}</span></a>`;
}

/** Le renfo de l'élève : l'équilibre avant / arrière de ses 4 semaines, ce que tu peux lui dire, et sa tendance. */
function renfoCard(r, sid, accord) {
  if (accord?.seances === false) return "";
  if (!r) return `<section class="coach-card"><h2>${icon("balance")}Renfo : avant / arrière</h2><p class="co-empty">Pas de renfo sur les 4 dernières semaines.</p></section>`;
  if (r.zone === "vide") {
    return `<section class="coach-card"><h2>${icon("balance")}Renfo : avant / arrière</h2><p class="co-empty">${r.seances} séance${r.seances > 1 ? "s" : ""} de renfo, mais aucune série rangée devant ou derrière (échauffement, cardio, latéral ou exercice non précisé).</p></section>`;
  }
  const hint = r.conseil;
  const weeks = (r.semaines || []).map((w) => {
    const label = `S${F.isoWeek(F.parseDate(w.lundi)).week}`;
    return `<li class="co-rw${w.zone ? ` z-${w.zone}` : ""}" title="${F.escape(`Semaine du ${F.dateLong(w.lundi, { weekday: false })} : ${w.ratio_texte ? `${w.ratio_texte}, ${w.series} séries` : "pas de renfo"}`)}">
        <small>${label}</small><b>${F.escape(w.ratio_texte ? w.ratio_texte.replace("1 : ", "1:") : "–")}</b></li>`;
  }).join("");
  const draft = hint?.brouillon ? `#/coach/messages?fil=eleve-${sid}&brouillon=${encodeURIComponent(hint.brouillon)}` : null;
  return `<section class="coach-card co-renfo-card"><h2>${icon("balance")}Renfo : avant / arrière <span class="co-count">${r.seances} séance${r.seances > 1 ? "s" : ""}</span></h2>
      ${headline(r, { compact: true })}${beam(r, { compact: true })}
      ${hint ? `<p class="co-renfo-hint z-${F.escape(r.zone)}">${F.escape(hint.texte)}</p>` : ""}
      ${weeks ? `<ol class="co-rweeks" aria-label="Semaine par semaine">${weeks}</ol>` : ""}
      ${r.paires?.length ? `<details class="co-rpairs"><summary>Paire par paire</summary>${pairs(r)}</details>` : ""}
      <div class="inline-actions" style="margin:10px 0 0">${draft ? `<a class="btn btn-small" href="${draft}">${icon("chat")}Lui en parler</a>` : ""}
        <span class="hint">Cible du coureur : 1:1 à 1:2 (séries devant : derrière).</span></div>
    </section>`;
}

function otherGoals(list) {
  if (!list?.length) return "";
  return `<div class="co-goals2"><h3>Aussi au programme</h3><ul>${list.map((g) => `<li><span class="co-g2-name"><b>${F.escape(g.nom)}</b>
      <small>${F.escape([F.dateShort(g.date), g.distance_km ? `${F.dec1(g.distance_km).replace(",0", "")} km` : "", g.d_plus_m ? `${F.int(g.d_plus_m)} m D+` : "", g.temps_cible ? `visé ${g.temps_cible}` : ""].filter(Boolean).join(" · "))}</small></span>
      <span class="co-chip blue">J-${g.dans_jours}</span></li>`).join("")}</ul></div>`;
}

export async function renderStudent(ctx, sid) {
  const { page, params, toast } = ctx;
  const semaine = /^\d{4}-\d{2}-\d{2}$/.test(params.get("semaine") || "") ? params.get("semaine") : null;
  page.innerHTML = `${ctx.head(`<h1>…</h1>`)}${ctx.tabs("eleves")}<div class="co-page wide">${loading()}</div>`;
  const data = await rget(`eleves/${sid}/fiche`, semaine ? { semaine } : null);
  const e = data.eleve;
  const goal = data.objectif;
  const gp = goalPace(goal);
  const vma = data.profil?.vma_kmh;
  const testLine = data.suivi?.vma_test ? `${F.dec1(data.suivi.vma_test)} km/h${data.suivi.vma_test_le ? ` (${F.escape(F.dateLong(data.suivi.vma_test_le, { weekday: false }))})` : ""}` : "";
  const canWatch = Boolean(data.montre?.disponible && data.montre.relie && data.montre.coach_peut_envoyer);
  const week = data.semaine;
  const monday = F.parseDate(week.lundi);
  const prev = F.isoDate(F.addDays(monday, -7));
  const next = F.isoDate(F.addDays(monday, 7));
  const thisMonday = F.isoDate(F.mondayOf(new Date()));
  const days = data.jours || [];
  const metric = (key) => days.map((d) => d[key] ?? null);
  const lastOf = (key) => [...days].reverse().find((d) => F.isNum(d[key]))?.[key];
  const health = [["sommeil_h", "Sommeil", (v) => `${F.dec1(v)} h`, "var(--sl-deep)"], ["vfc", "VFC de la nuit", (v) => `${F.int(v)} ms`, "var(--s3)"],
    ["fc_repos", "FC au repos", (v) => `${F.int(v)}`, "var(--s2)"], ["poids_kg", "Poids", (v) => `${F.dec1(v)} kg`, "var(--s4)"]]
    .filter(([key]) => days.some((d) => F.isNum(d[key])));
  const t = data.total_28j;
  const b = week.bilan;

  page.innerHTML = `${ctx.head(`<div class="co-crumb"><a href="#/coach">Mes élèves</a> ›</div><h1 class="co-title">${avatar(e.nom, { size: "lg" })}${F.escape(e.nom)}${levelChip(data.suivi?.niveau)}</h1>`,
    `<span>Partage : ${F.escape(shareSummary(data.accord))}${data.partage_recu_le ? ` · données reçues ${F.escape(F.relative(data.partage_recu_le))}` : ""}</span>`,
    `<a class="btn" href="#/coach/messages?fil=eleve-${sid}">${icon("chat")}Message</a><a class="btn btn-primary" href="#/coach/proposer?eleves=${sid}">${icon("plus")}Proposer une séance</a>`)}
    ${ctx.tabs("eleves")}
    ${data.mois ? calendarCard("Son calendrier", "", data.mois, {
      vma, goals: [goal, ...(data.objectifs || [])].filter(Boolean), coachSide: true,
      sessionHref: (s) => `#/coach/eleve/${sid}/seance/${encodeURIComponent(s.cle)}`,
      fetchRange: (debut, fin) => api.get(`/api/coach/r/eleves/${sid}/calendrier`, { debut, fin }) }) : ""}
    <div class="co-grid2">
      <div class="co-page">
        <section class="coach-card"><div class="co-card-head"><h2>${icon("calendar")}${semaine && week.lundi !== thisMonday ? `Semaine du ${F.escape(F.dateLong(week.lundi, { weekday: false }))}` : "Sa semaine"}${b.prevues ? ` : ${b.faites} faite${b.faites > 1 ? "s" : ""} sur ${b.prevues} prévue${b.prevues > 1 ? "s" : ""}` : b.seances ? ` : ${b.seances} séance${b.seances > 1 ? "s" : ""}` : ""}</h2>
          <div class="co-weeknav"><a class="btn btn-ghost btn-small" href="#/coach/eleve/${sid}?semaine=${prev}" title="Semaine précédente">${icon("left")}</a>
            ${week.lundi !== thisMonday ? `<a class="btn btn-ghost btn-small" href="#/coach/eleve/${sid}">Cette semaine</a>` : ""}
            <a class="btn btn-ghost btn-small" href="#/coach/eleve/${sid}?semaine=${next}" title="Semaine suivante">${icon("right")}</a></div></div>
          <div class="co-week">${week.jours.map((d) => dayCell(d, sid)).join("")}</div>
          <div class="co-legend"><span class="co-pl done">fait</span><span class="co-pl coach next">proposée par toi</span><span class="co-pl next">son plan</span><span class="co-pl miss">manquée</span></div></section>
        <section class="coach-card"><h2>${icon("activity")}Séances reçues <span class="co-count">${data.seances.length}</span></h2>
          ${data.seances.length ? data.seances.map((s) => sessionRow(s, `#/coach/eleve/${sid}/seance/${encodeURIComponent(s.cle)}`)).join("")
            : `<p class="co-empty">${data.accord?.seances === false ? `${F.escape(e.nom)} ne partage pas ses séances.` : data.accord ? "Rien de reçu sur les 4 dernières semaines." : `${F.escape(e.nom)} n'a pas encore choisi ce qu'il partage : rien n'est envoyé avant son accord.`}</p>`}
        </section>
      </div>
      <div class="co-page">
        <section class="coach-card"><h2>${icon("flag")}Objectif</h2>
          ${goal ? `<div class="co-big">${goal.dans_jours != null ? (goal.dans_jours >= 0 ? `J-${goal.dans_jours}` : "passé") : F.escape(goal.nom)}</div>
            <dl class="co-dl"><dt>Course</dt><dd>${F.escape(goal.nom)}</dd>${goal.date ? `<dt>Date</dt><dd>${F.escape(F.dateLong(goal.date, { year: true }))}</dd>` : ""}
            ${goal.distance_km ? `<dt>Distance</dt><dd>${F.escape(F.dec1(goal.distance_km))} km</dd>` : ""}${goal.temps_cible ? `<dt>Temps visé</dt><dd>${F.escape(goal.temps_cible)}</dd>` : ""}
            ${gp ? `<dt>Allure</dt><dd>${F.escape(gp.pace)}${vma ? ` · ${Math.round(gp.kmh / vma * 100)} % VMA` : ""}</dd>` : ""}
            ${goal.d_plus_m ? `<dt>Dénivelé</dt><dd>${F.int(goal.d_plus_m)} m D+</dd>` : ""}
            <dt>VMA</dt><dd>${vma ? `${F.dec1(vma)} km/h` : "–"}</dd>${testLine ? `<dt>Test club</dt><dd>${testLine}</dd>` : ""}</dl>`
            : `<p class="co-empty">${data.accord?.objectif === false ? "Il ne partage pas son objectif." : "Pas d'objectif partagé."}${vma ? ` VMA : <b>${F.dec1(vma)} km/h</b>.` : ""}${testLine ? ` Test du club : <b>${testLine}</b>.` : ""}</p>`}
          <p class="hint" style="margin:8px 0 0">${data.suivi?.niveau ? `Groupe de niveau : <b>${F.escape(data.suivi.niveau.nom)}</b>${data.suivi.niveau_force ? " (placé à la main)" : ""}. ` : data.niveaux?.length ? "Dans aucun de tes groupes. " : ""}<a href="#/coach/reglages">${data.niveaux?.length ? "Groupes et test VMA" : "Créer des groupes de niveau"}</a></p>
          ${otherGoals(data.objectifs)}
        </section>
        ${zonesCard(data.zones_fc, data.profil, data.accord, e.nom)}
        <section class="coach-card"><h2>${icon("gauge")}4 dernières semaines</h2>
          <dl class="co-dl"><dt>Séances</dt><dd>${t.seances}${t.renfo ? ` (dont ${t.renfo} renfo)` : ""}</dd><dt>Distance</dt><dd>${t.distance_m ? km(t.distance_m) : "–"}</dd>
            <dt>Durée</dt><dd>${t.duree_s ? dur(t.duree_s) : "–"}</dd><dt>Charge</dt><dd>${t.charge ? F.int(t.charge) : "–"}</dd></dl></section>
        ${renfoCard(data.renfo, sid, data.accord)}
        <section class="coach-card"><h2>${icon("layers")}Séances proposées</h2><div data-props>
          ${data.propositions.length ? data.propositions.map((p) => `<div class="co-prop"><div><b>${F.escape(p.titre)}</b><span>${F.escape(dayLabel(p.date))}${p.sport_label ? ` · ${F.escape(p.sport_label)}` : ""}</span></div>
            ${statusChip(p.statut)}<span class="co-prop-tools">${p.montre ? `<i class="co-watchmark${p.montre.a_jour ? "" : " warn"}" title="${p.montre.a_jour ? `Sur sa montre (${p.montre.par === "coach" ? "envoyée par toi" : "envoyée par lui"}, ${F.escape(F.relative(p.montre.envoye_le))})` : F.escape(p.montre.erreur || "À renvoyer")}">${icon("watch")}</i>` : ""}
            ${p.seance ? `<a class="co-mini" href="#/coach/eleve/${sid}/seance/${encodeURIComponent(p.seance.cle)}" title="Voir la séance faite">${icon("right")}</a>` : ""}
            ${canWatch && p.statut !== "fait" && p.statut !== "manque" ? `<button type="button" class="co-mini" data-watch="${p.id}" title="${p.montre ? "La renvoyer sur sa montre" : "L'envoyer sur sa montre (calendrier Garmin Connect)"}">${icon("watch")}</button>` : ""}
            <a class="co-mini" href="/api/coach/eleves/${sid}/seances/${p.id}.fit" download title="Le fichier pour sa montre (.fit), avec ses allures">${icon("download")}</a>
            <a class="co-mini" href="#/coach/proposer?id=${p.id}&eleve=${sid}" title="Modifier">${icon("edit")}</a>
            <button type="button" class="co-mini" data-drop="${p.id}" title="Supprimer">${icon("trash")}</button></span></div>`).join("")
            : `<p class="co-empty">Aucune séance proposée.</p>`}</div>
          ${watchLine(data.montre, e.nom)}
          <div class="inline-actions" style="margin:10px 0 0"><a class="btn btn-small" href="#/coach/proposer?eleves=${sid}">${icon("plus")}Proposer une séance</a></div></section>
        ${health.length ? `<section class="coach-card"><h2>${icon("heart")}Forme</h2><div class="co-health">${health.map(([key, label, fmt, color]) => `<div>
            <small>${label}</small><b>${fmt(lastOf(key))}</b>${spark(metric(key), { color })}</div>`).join("")}</div>
          <p class="hint" style="margin:8px 0 0">Les 4 dernières semaines, telles qu'il les partage.</p></section>` : ""}
      </div>
    </div>`;

  wireCalendar(page);
  page.querySelectorAll("[data-watch]").forEach((btn) => btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const res = await api.post("/api/coach/montres", { propositions: [Number(btn.dataset.watch)] });
      toast(watchSummary(res));
      renderStudent(ctx, sid);
    } catch (err) { toast(err.message); btn.disabled = false; }
  }));
  page.querySelectorAll("[data-drop]").forEach((btn) => btn.addEventListener("click", async () => {
    if (!window.confirm("Supprimer cette séance proposée ? Elle disparaît aussi du calendrier de l'élève.")) return;
    try { await rdel(`propositions/${btn.dataset.drop}`); toast("Séance supprimée."); renderStudent(ctx, sid); }
    catch (err) { toast(err.message); }
  }));
}

function lapsTable(laps, running) {
  const speeds = laps.map((l) => l.vitesse_kmh || 0);
  const top = Math.max(...speeds, 1);
  const low = Math.min(...speeds.filter(Boolean), top);
  return `<div class="co-table-wrap"><table class="co-tbl co-laps"><thead><tr><th>#</th><th>Durée</th><th>Distance</th><th>${running ? "Allure" : "Vitesse"}</th><th class="co-bar-col"></th><th>FC</th><th>D+</th></tr></thead><tbody>
    ${laps.map((l, i) => `<tr class="${l.intensite === "rest" || l.intensite === "recovery" ? "rest" : ""}"><td>${i + 1}</td><td>${F.escape(F.chrono(l.duree_s))}</td><td>${F.escape(km(l.distance_m) || "–")}</td>
      <td><b>${F.escape(running ? l.allure || "–" : l.vitesse_kmh ? `${F.dec1(l.vitesse_kmh)} km/h` : "–")}</b></td>
      <td class="co-bar-col"><span class="co-lapbar" style="width:${l.vitesse_kmh ? Math.max(8, ((l.vitesse_kmh - low * 0.85) / (top - low * 0.85)) * 100) : 0}%"></span></td>
      <td>${l.fc_moy ? F.int(l.fc_moy) : "–"}</td><td>${l.denivele_m ? `${F.int(l.denivele_m)} m` : "–"}</td></tr>`).join("")}
    </tbody></table></div>`;
}

export async function renderSession(ctx, sid, key) {
  const { page, role, toast } = ctx;
  const coachSide = role === "coach";
  page.innerHTML = `${ctx.head(`<h1>…</h1>`)}${ctx.tabs(coachSide ? "eleves" : "coach")}<div class="co-page wide">${loading()}</div>`;
  const [data, who] = await Promise.all([
    rget(coachSide ? `eleves/${sid}/seances/${encodeURIComponent(key)}` : `moi/seances/${encodeURIComponent(key)}`),
    coachSide ? rget(`eleves/${sid}/fiche`).then((f) => f.eleve).catch(() => null) : Promise.resolve(null),
  ]);
  const s = data.seance;
  const running = ["course", "trail"].includes(s.sport);
  const stats = [
    ["Distance", km(s.distance_m)], ["Durée", dur(s.duree_s)], [running ? "Allure" : "Vitesse", running ? s.allure : s.vitesse_kmh ? `${F.dec1(s.vitesse_kmh)} km/h` : ""],
    ["FC moyenne", s.fc_moy ? F.int(s.fc_moy) : ""], ["FC max", s.fc_max ? F.int(s.fc_max) : ""], ["Dénivelé", s.denivele_m ? `${F.int(s.denivele_m)} m` : ""],
    ["Cadence", s.cadence ? F.int(s.cadence) : ""], ["Puissance", s.puissance ? `${F.int(s.puissance)} W` : ""],
    ["Effet aérobie", s.effet_aerobie ? F.dec1(s.effet_aerobie) : ""], ["Effet anaérobie", s.effet_anaerobie ? F.dec1(s.effet_anaerobie) : ""],
    ["Charge", s.charge ? F.int(s.charge) : ""], ["Calories", s.calories ? F.int(s.calories) : ""],
  ].filter(([, v]) => v);
  const prop = data.proposition;
  const name = who?.nom || "";
  const crumb = coachSide ? `<a href="#/coach">Mes élèves</a> › <a href="#/coach/eleve/${sid}">${F.escape(name || "Élève")}</a> ›` : `<a href="#/coach">Mon coach</a> ›`;
  const when = s.debut ? F.whenActivity(s.debut) : F.dateLong(s.date, { year: true });
  const analysis = s.tours?.length > 1 ? analysisHTML(s.tours, s.courbe, { running }) : "";

  page.innerHTML = `${ctx.head(`<div class="co-crumb">${crumb}</div><h1 class="co-title"><span class="co-ico lg">${sportIcon(s.sport)}</span>${F.escape(s.nom || s.sport_label || "Séance")}</h1>`,
    `<span>${F.escape(when)}${s.sport_label ? ` · ${F.escape(s.sport_label.toLowerCase())}` : ""}${s.avantage ? ` · ${F.escape(s.avantage)}` : ""}</span>
     ${prop ? `<span class="co-chip blue">${icon("layers")}${coachSide ? "proposée par toi" : "proposée par ton coach"}</span>${statusChip(prop.statut)}` : data.prevue ? `<span class="co-chip">${icon("calendar")}prévue : ${F.escape(data.prevue.titre)}</span>` : ""}`,
    coachSide ? `<a class="btn" href="#/coach/messages?fil=eleve-${sid}">${icon("chat")}Conversation</a>` : "")}
    ${ctx.tabs(coachSide ? "eleves" : "coach")}
    ${analysis ? `<section class="coach-card co-analyse"><h2>${icon("wave")}Analyse fraction par fraction <span class="co-count">${s.tours.length}</span></h2>${analysis}</section>` : ""}
    <div class="co-grid2">
      <div class="co-page">
        <section class="coach-card"><div class="co-stats">${stats.map(([k, v]) => `<div><small>${k}</small><b>${F.escape(v)}</b></div>`).join("")}</div>
          ${s.description ? `<blockquote class="co-quote">${F.escape(s.description)}</blockquote>` : ""}</section>
        ${prop ? `<section class="coach-card"><h2>${icon("layers")}Ce qui était proposé : ${F.escape(prop.titre)}</h2>${blocksHtml(prop.blocs, data.vma_kmh)}
          ${prop.consigne ? `<p class="co-consigne">« ${F.escape(prop.consigne)} »</p>` : ""}</section>` : ""}
        ${s.tours?.length ? `<section class="coach-card"><h2>${icon("list")}Tours <span class="co-count">${s.tours.length}</span></h2>${lapsTable(s.tours, running)}</section>` : ""}
        ${s.renfo?.length ? `<section class="coach-card"><h2>${icon("dumbbell")}Renforcement</h2><div class="co-table-wrap"><table class="co-tbl"><thead><tr><th>Exercice</th><th>Séries</th><th>Répétitions</th><th>Charge</th><th>Chaîne</th></tr></thead><tbody>
          ${s.renfo.map((r) => `<tr><td><b>${F.escape(r.exercice)}</b></td><td>${r.series ?? "–"}</td><td>${r.reps ?? "–"}</td><td>${r.kg ? `${F.dec1(r.kg)} kg` : "–"}</td><td>${F.escape(r.chaine || "–")}</td></tr>`).join("")}
          </tbody></table></div></section>` : ""}
      </div>
      <div class="co-page">
        ${s.trace ? `<section class="coach-card"><h2>${icon("map")}Tracé</h2>${traceSvg(s.trace)}<p class="hint" style="margin:6px 0 0">Tracé simplifié, sans fond de carte. Si l'élève l'a choisi, le départ et l'arrivée sont masqués.</p></section>` : ""}
        <section class="coach-card"><h2>${icon("chat")}Fil de la séance</h2><div data-thread></div></section>
      </div>
    </div>`;

  wireAnalysis(page);
  mountThread(page.querySelector("[data-thread]"), {
    fil: data.fil, role, style: "comments", toast, onRead: () => ctx.poke(),
    placeholder: coachSide ? `Un mot à ${name || "l'élève"} sur cette séance…` : "Un mot à ton coach sur cette séance…",
    empty: coachSide ? "Pas encore de commentaire. Écris le premier : il le retrouvera dans ses messages, sous la séance." : "Pas encore de commentaire sur cette séance.",
  });
}

