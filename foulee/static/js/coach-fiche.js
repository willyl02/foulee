// La fiche d'un élève (vue du coach) et la page d'une séance partagée, avec son fil (coach et élève).
import * as F from "./format.js";
import { icon } from "./icons.js";
import {
  avatar, blocksHtml, dayLabel, dur, km, loading, mountThread, rdel, rget, sessionFigures, sportIcon, statusChip, traceSvg,
} from "./coach-ui.js";

const DOW = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

function shareSummary(accord) {
  if (!accord) return "rien encore : il n'a pas choisi ce qu'il partage";
  const items = [accord.seances && "séances", accord.objectif && "objectif et VMA", accord.seances && accord.gps && (accord.masquer ? "tracés (départ et arrivée masqués)" : "tracés"),
    accord.sante && "sommeil et VFC", accord.poids && "poids"].filter(Boolean);
  return items.length ? items.join(", ") : "rien";
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

export async function renderStudent(ctx, sid) {
  const { page, params, toast } = ctx;
  const semaine = /^\d{4}-\d{2}-\d{2}$/.test(params.get("semaine") || "") ? params.get("semaine") : null;
  page.innerHTML = `${ctx.head(`<h1>…</h1>`)}${ctx.tabs("eleves")}<div class="co-page wide">${loading()}</div>`;
  const data = await rget(`eleves/${sid}/fiche`, semaine ? { semaine } : null);
  const e = data.eleve;
  const goal = data.objectif;
  const gp = goalPace(goal);
  const vma = data.profil?.vma_kmh;
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

  page.innerHTML = `${ctx.head(`<div class="co-crumb"><a href="#/coach">Mes élèves</a> ›</div><h1 class="co-title">${avatar(e.nom, { size: "lg" })}${F.escape(e.nom)}</h1>`,
    `<span>Partage : ${F.escape(shareSummary(data.accord))}${data.partage_recu_le ? ` · données reçues ${F.escape(F.relative(data.partage_recu_le))}` : ""}</span>`,
    `<a class="btn" href="#/coach/messages?fil=eleve-${sid}">${icon("chat")}Message</a><a class="btn btn-primary" href="#/coach/proposer?eleves=${sid}">${icon("plus")}Proposer une séance</a>`)}
    ${ctx.tabs("eleves")}
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
            <dt>VMA</dt><dd>${vma ? `${F.dec1(vma)} km/h` : "–"}</dd></dl>`
            : `<p class="co-empty">${data.accord?.objectif === false ? "Il ne partage pas son objectif." : "Pas d'objectif partagé."}${vma ? ` VMA : <b>${F.dec1(vma)} km/h</b>.` : ""}</p>`}
        </section>
        <section class="coach-card"><h2>${icon("gauge")}4 dernières semaines</h2>
          <dl class="co-dl"><dt>Séances</dt><dd>${t.seances}${t.renfo ? ` (dont ${t.renfo} renfo)` : ""}</dd><dt>Distance</dt><dd>${t.distance_m ? km(t.distance_m) : "–"}</dd>
            <dt>Durée</dt><dd>${t.duree_s ? dur(t.duree_s) : "–"}</dd><dt>Charge</dt><dd>${t.charge ? F.int(t.charge) : "–"}</dd></dl></section>
        <section class="coach-card"><h2>${icon("layers")}Séances proposées</h2><div data-props>
          ${data.propositions.length ? data.propositions.map((p) => `<div class="co-prop"><div><b>${F.escape(p.titre)}</b><span>${F.escape(dayLabel(p.date))}${p.sport_label ? ` · ${F.escape(p.sport_label)}` : ""}</span></div>
            ${statusChip(p.statut)}<span class="co-prop-tools">${p.seance ? `<a class="co-mini" href="#/coach/eleve/${sid}/seance/${encodeURIComponent(p.seance.cle)}" title="Voir la séance faite">${icon("right")}</a>` : ""}
            <a class="co-mini" href="/api/coach/eleves/${sid}/seances/${p.id}.fit" download title="Le fichier pour sa montre (.fit), avec ses allures">${icon("download")}</a>
            <a class="co-mini" href="#/coach/proposer?id=${p.id}&eleve=${sid}" title="Modifier">${icon("edit")}</a>
            <button type="button" class="co-mini" data-drop="${p.id}" title="Supprimer">${icon("trash")}</button></span></div>`).join("")
            : `<p class="co-empty">Aucune séance proposée.</p>`}</div>
          <div class="inline-actions" style="margin:10px 0 0"><a class="btn btn-small" href="#/coach/proposer?eleves=${sid}">${icon("plus")}Proposer une séance</a></div></section>
        ${health.length ? `<section class="coach-card"><h2>${icon("heart")}Forme</h2><div class="co-health">${health.map(([key, label, fmt, color]) => `<div>
            <small>${label}</small><b>${fmt(lastOf(key))}</b>${spark(metric(key), { color })}</div>`).join("")}</div>
          <p class="hint" style="margin:8px 0 0">Les 4 dernières semaines, telles qu'il les partage.</p></section>` : ""}
      </div>
    </div>`;

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

  page.innerHTML = `${ctx.head(`<div class="co-crumb">${crumb}</div><h1 class="co-title"><span class="co-ico lg">${sportIcon(s.sport)}</span>${F.escape(s.nom || s.sport_label || "Séance")}</h1>`,
    `<span>${F.escape(when)}${s.sport_label ? ` · ${F.escape(s.sport_label.toLowerCase())}` : ""}${s.avantage ? ` · ${F.escape(s.avantage)}` : ""}</span>
     ${prop ? `<span class="co-chip blue">${icon("layers")}${coachSide ? "proposée par toi" : "proposée par ton coach"}</span>${statusChip(prop.statut)}` : data.prevue ? `<span class="co-chip">${icon("calendar")}prévue : ${F.escape(data.prevue.titre)}</span>` : ""}`,
    coachSide ? `<a class="btn" href="#/coach/messages?fil=eleve-${sid}">${icon("chat")}Conversation</a>` : "")}
    ${ctx.tabs(coachSide ? "eleves" : "coach")}
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

  mountThread(page.querySelector("[data-thread]"), {
    fil: data.fil, role, style: "comments", toast, onRead: () => ctx.poke(),
    placeholder: coachSide ? `Un mot à ${name || "l'élève"} sur cette séance…` : "Un mot à ton coach sur cette séance…",
    empty: coachSide ? "Pas encore de commentaire. Écris le premier : il le retrouvera dans ses messages, sous la séance." : "Pas encore de commentaire sur cette séance.",
  });
}

