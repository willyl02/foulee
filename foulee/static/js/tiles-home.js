// Tuiles de la page d'accueil : bonjour, forme du jour, allures selon la VMA (tableau du club),
// semaine, records, journée en détail, mon club.
import * as api from "./api.js";
import * as C from "./charts.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { brandMark } from "./logos.js";
import { message } from "./tiles-data.js";

const STATE_ICON = { bon: "check", moyen: "flat", alerte: "warning" };

function greeting() {
  const h = new Date().getHours();
  return h >= 4 && h < 18 ? "Bonjour" : "Bonsoir";
}

function planText(plan) {
  if (!plan?.actif) return null;
  if (plan.poste) return `${plan.nom}, ${plan.debut}–${plan.fin}`;
  if (plan.conges) return plan.conges === "Congés" ? "En congés" : `Congés : ${plan.conges}`;
  return "Repos";
}

// ------------------------------------------------------------------ bonjour
export const profil = {
  ownHead: true,
  title: () => "Bonjour",
  async render(body, p, ctx) {
    const b = ctx.boot;
    const today = new Date();
    const plan = F.dayPlan(today, ctx.settings);
    const goal = b.objectif || {};
    const chips = [];
    const shift = planText(plan);
    if (shift) {
      const color = F.shiftColor(plan.poste, ctx.settings, ctx.palette);
      chips.push(`<span class="chip"><i class="dot" style="background:${color}"></i>${F.escape(shift)}</span>`);
    }
    if (goal.date && goal.jours_restants >= 0) {
      chips.push(`<span class="chip">${icon("flag")}${F.escape(goal.nom || "Objectif")} : ${goal.jours_restants === 0 ? "c'est le jour J" : `J−${goal.jours_restants}`}</span>`);
    }
    if (b.club) {
      const lic = b.club.licence || {};
      chips.push(`<a class="chip" href="#/vue/club" title="Mon club">${icon("club")}${F.escape(b.club.nom || `Club ${b.club.numero}`)}</a>`);
      if (lic.a_renouveler) {
        chips.push(`<a class="chip chip-warn" href="#/vue/club">${icon("warning")}${lic.expiree ? "Licence expirée" : `Licence à renouveler : J−${lic.jours_restants}`}</a>`);
      }
    }
    const last = b.synchro?.derniere_reussie;
    chips.push(`<span class="chip chip-muted">${icon("sync")}${last ? `Synchro ${F.escape(F.relative(last))}` : "Jamais synchronisé"}</span>`);
    const name = b.profil?.prenom_affiche;
    const avatar = b.profil?.photo
      ? `<img class="hello-photo" src="/api/profil/photo?v=${b.profil.photo_maj || 0}" alt="">`
      : `<span class="hello-logo">${brandMark(b.profil, 52)}</span>`;
    body.innerHTML = `<div class="hello">
      ${avatar}
      <div class="hello-text">
        <h2>${greeting()}${name ? ` ${F.escape(name)}` : ""}</h2>
        <div class="hello-date">${F.escape(F.dateLong(F.isoDate(today), { year: true }))}</div>
      </div>
      <div class="hello-chips">${chips.join("")}</div>
    </div>`;
  },
};

// -------------------------------------------------------------- forme du jour
export const forme = {
  title: () => "Forme du jour",
  async render(body, p, ctx) {
    const d = await api.get("/api/forme");
    if (!d.signaux.length) return message(body, d.resume);
    const today = F.isoDate(new Date());
    ctx.sub(`${d.verdict === "bon" ? "Feu vert" : d.verdict === "moyen" ? "À surveiller" : d.verdict === "alerte" ? "Prudence" : ""} · indicatif`);
    body.classList.add("scroll");
    body.innerHTML = `<div class="form-day">
      <p class="form-verdict ${d.verdict || ""}" title="${F.escape(d.note)}">${icon(STATE_ICON[d.verdict] || "info")}<span>${F.escape(d.resume)}</span></p>
      <div class="signals">${d.signaux.map((s) => `<div class="signal ${s.etat || ""}" title="${F.escape(`${s.label} : ${s.affiche}${s.reference ? ` (${s.reference})` : ""}`)}">
          <span class="signal-label">${F.escape(s.label)}${s.date && s.date !== today ? ` <small>au ${F.escape(F.dateShort(s.date))}</small>` : ""}</span>
          <b class="signal-value">${F.escape(s.affiche)}</b>
          <span class="signal-note">${F.escape(s.explication || s.reference || "")}</span>
        </div>`).join("")}</div>
      <p class="hint form-note">${F.escape(d.note)}</p>
    </div>`;
  },
};

// ---------------------------------------------------- allures selon la VMA
const TABS = [["tableau", "Allures et piste"], ["vameval", "Test VAMEVAL"]];

function bandOf(bands, pct) {
  return bands.find((b) => b.pct.includes(pct))?.id || "";
}

function pacesTable(d) {
  return `<table class="vma-table">
    <thead>
      <tr><th rowspan="2" class="ref">Allure au km<br><small>et vitesse</small></th><th rowspan="2" class="num">VMA<br><small>km/h</small></th>
        ${d.bandes.map((b) => `<th colspan="${b.pct.length}" class="band band-${b.id}" title="${F.escape(`${b.pct[0]}${b.pct.length > 1 ? `–${b.pct[b.pct.length - 1]}` : ""} % : ${b.usage}`)}">${F.escape(b.nom)}</th>`).join("")}</tr>
      <tr>${d.pct.map((p) => `<th class="pct band-${bandOf(d.bandes, p)}">${p} %</th>`).join("")}</tr>
    </thead>
    <tbody>${d.lignes.map((row, i) => `<tr class="${i === 0 ? "mine" : ""}"><th class="ref">${F.escape(row.libelle)}</th>
      <td class="num vma">${F.dec2(row.vma)}</td>
      ${row.allures.map((pace, j) => `<td class="band-cell band-${bandOf(d.bandes, d.pct[j])}"><b>${F.escape(pace)}</b><small>${F.dec1(row.vitesses[j])}</small></td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
}

function trackTable(d) {
  const t = d.piste;
  return `<table class="vma-table track">
    <thead><tr><th class="ref">Piste<br><small>VMA ${F.dec1(t.vma)} km/h</small></th>${t.pct.map((p) => `<th class="pct band-${bandOf(d.bandes, p)}">${p} %</th>`).join("")}</tr></thead>
    <tbody>${t.distances.map((row) => `<tr><th class="ref">${row.m} m</th>${row.temps.map((c, j) => `<td class="band-cell band-${bandOf(d.bandes, t.pct[j])}">${F.escape(c)}</td>`).join("")}</tr>`).join("")}</tbody>
  </table>`;
}

export const allures = {
  ownHead: true,
  title: () => "Allures selon ta VMA",
  async render(body, p, ctx, tile) {
    let tab = p.onglet === "vameval" ? "vameval" : "tableau";
    let compare = Number(p.comparer) || null;
    let test = null;  // temps saisi dans l'onglet du test, pas encore gardé
    let data = null;
    const title = tile.titre || "Allures selon ta VMA";

    const load = async () => {
      data = await api.get("/api/allures", { comparer: compare || "", test: test || "" }, { fresh: true });
    };

    const vamevalPanel = () => {
      const t = data.test;
      const saved = ctx.settings.vameval;
      return `<div class="vameval">
        <p class="computed">Échauffement à 8 km/h, puis +0,5 km/h par minute. Saisis le temps total couru ; Foulée lit le barème du club.</p>
        <div class="inline-actions">
          <label class="inline-field"><span>Temps du test</span><input type="text" data-test inputmode="numeric" placeholder="12:40" value="${F.escape(test || saved || "")}" size="6" aria-label="Temps du test VAMEVAL (minutes:secondes)"></label>
          <button class="btn" type="button" data-read>${icon("check")}Lire le barème</button>
        </div>
        ${t ? `<dl class="vam-result">
            <div><dt>Palier atteint</dt><dd>${t.palier}</dd></div>
            <div><dt>Vitesse courue</dt><dd>${F.dec1(t.vitesse_courue)} km/h</dd></div>
            <div><dt>VMA palier validé</dt><dd>${F.dec1(t.vma_palier)} km/h</dd></div>
            <div><dt>VMA interpolée</dt><dd><b>${F.dec2(t.vma_interpolee)} km/h</b></dd></div>
          </dl>
          <p class="hint">${F.escape(t.lecture)}</p>
          <div class="inline-actions">
            <button class="btn btn-primary" type="button" data-use="${t.vma_interpolee}">${icon("run")}Prendre ${F.dec2(t.vma_interpolee)} km/h comme VMA</button>
            <button class="btn" type="button" data-keep>${icon("flag")}Afficher ce test dans le tableau</button>
            ${saved ? `<button class="btn btn-ghost" type="button" data-forget>${icon("trash")}Retirer le test du tableau</button>` : ""}
          </div>` : `<p class="hint">Format minutes:secondes, de 2:00 à 59:59.</p>`}
      </div>`;
    };

    const draw = () => {
      const sub = tab === "vameval" ? "Barème VAMEVAL du club" : `Ta VMA : ${F.dec1(data.vma)} km/h`;
      body.innerHTML = `<div class="tile-head tile-head-tools"><h2 class="tile-title">${F.escape(title)}</h2><span class="tile-sub">${F.escape(sub)}</span>
          <div class="segmented small" role="tablist">${TABS.map(([k, l]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${k === tab}" aria-pressed="${k === tab}">${l}</button>`).join("")}</div></div>
        <div class="vma-scroll">${tab === "vameval" ? vamevalPanel() : `${pacesTable(data)}${trackTable(data)}`}</div>
        ${tab === "tableau" ? `<div class="vma-foot">
          <label class="inline-field"><span>Comparer avec une VMA de</span><input type="number" step="0.1" min="6" max="30" data-compare value="${compare || ""}" placeholder="—" aria-label="Autre VMA à comparer (km/h)"><span>km/h</span></label>
          <span class="hint">Survole une bande pour savoir à quoi elle sert.</span>
        </div>` : ""}`;
      body.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.tab; draw(); }));
      body.querySelector("[data-compare]")?.addEventListener("change", async (e) => {
        const v = Number(e.target.value);
        compare = v >= 6 && v <= 30 ? v : null;
        await load();
        draw();
      });
      const testInput = body.querySelector("[data-test]");
      const read = async () => {
        test = testInput.value.trim();
        try {
          await load();
        } catch (err) {
          test = null;
          await load();
          draw();
          ctx.toast(err.message, { error: true });
          return;
        }
        draw();
      };
      body.querySelector("[data-read]")?.addEventListener("click", read);
      testInput?.addEventListener("keydown", (e) => { if (e.key === "Enter") read(); });
      body.querySelector("[data-use]")?.addEventListener("click", async (e) => {
        const vma = Number(e.currentTarget.dataset.use);
        await ctx.saveSettings({ vma_kmh: vma }, `VMA réglée à ${F.dec2(vma)} km/h : zones et allures recalculées.`);
      });
      body.querySelector("[data-keep]")?.addEventListener("click", async () => {
        await ctx.saveSettings({ vameval: data.test.temps }, "Test gardé : ses deux VMA s'affichent dans le tableau.");
      });
      body.querySelector("[data-forget]")?.addEventListener("click", async () => {
        test = null;
        await ctx.saveSettings({ vameval: null }, "Test retiré du tableau.");
      });
    };

    await load();
    draw();
  },
};

// ---------------------------------------------------------------- semaine
const SPORT_ICON = { course: "run", trail: "run", velo: "activity", natation: "wave", marche: "map", rando: "map" };

export const semaine = {
  title: () => "Ta semaine",
  async render(body, p, ctx) {
    const d = await api.get("/api/semaine");
    const today = F.isoDate(new Date());
    ctx.sub(`Semaine ${d.semaine_iso}`);
    const t = d.totaux;
    const m = d.moyenne_4_semaines;
    const compare = (now, avg, fmt = F.dec1) => `<b>${fmt(now)}</b><small> / moy. ${fmt(avg)}</small>`;
    body.classList.add("scroll");
    body.innerHTML = `<div class="week">
      <div class="week-days">${d.jours.map((day) => {
        const plan = day.planning;
        const color = F.shiftColor(plan.poste, ctx.settings, ctx.palette);
        const label = plan.actif ? (plan.poste ? `${plan.nom} ${plan.debut}` : plan.nom) : "";
        return `<div class="wday${day.date === today ? " today" : ""}${day.passe ? "" : " future"}">
          <div class="wday-head"><b>${F.escape(day.jour.slice(0, 3))}.</b><span>${F.parseDate(day.date).getDate()}</span></div>
          ${label ? `<div class="wday-shift" style="--c:${color}">${F.escape(label)}</div>` : ""}
          ${day.seances.map((s) => `<button type="button" class="wday-act" data-act="${F.escape(s.id)}" title="${F.escape(`${s.nom || s.sport_label} : ${s.duree}`)}">
            ${icon(SPORT_ICON[s.sport] || "activity")}<span>${s.distance_km ? `${F.dec1(s.distance_km)} km` : F.escape(s.duree)}</span></button>`).join("")}
        </div>`;
      }).join("")}</div>
      <div class="week-totals">
        <span>Séances ${compare(t.seances, m.seances, F.int)}</span>
        <span>Course ${compare(t.km_course, m.km_course)} km</span>
        <span>Durée <b>${F.escape(t.duree)}</b><small> / moy. ${F.escape(m.duree)}</small></span>
        <span>D+ ${compare(t.d_plus, m.d_plus, F.int)} m</span>
        <span>Charge ${compare(t.charge, m.charge, F.int)}</span>
      </div>
    </div>`;
    body.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => ctx.openActivity(b.dataset.act)));
  },
};

// ---------------------------------------------------------------- records
export const records = {
  title: () => "Records",
  async render(body, p, ctx) {
    const { start, end, days } = ctx.period(p);
    const d = await api.get("/api/records", { start, end, sport: p.sport });
    if (!d.records.length) return message(body, "Pas encore de meilleurs temps : Garmin les calcule pour chaque sortie de course.");
    ctx.sub(`Sur ${days >= 365 ? `${Math.round(days / 365)} an${days >= 730 ? "s" : ""}` : `${days} jours`}, face à tes records`);
    body.classList.add("scroll");
    const cell = (r) => (r ? `<button type="button" class="rec" data-act="${F.escape(r.seance_id)}" title="${F.escape(r.seance_nom || "")}">
        <b>${F.escape(r.temps)}</b><small>${F.escape(r.allure)} · ${F.escape(F.dateShort(r.date))}${F.parseDate(r.date).getFullYear() !== new Date().getFullYear() ? ` ${F.parseDate(r.date).getFullYear()}` : ""}</small></button>` : `<span class="muted">–</span>`);
    body.innerHTML = `<table class="records">
      <thead><tr><th>Distance</th><th>Sur la période</th><th>Record</th></tr></thead>
      <tbody>${d.records.map((r) => `<tr class="${r.egale_record ? "is-record" : ""}">
        <th>${F.escape(r.nom)}${r.egale_record ? ` <span class="rec-badge" title="Record battu ou égalé sur la période">${icon("trophy")}</span>` : ""}</th>
        <td>${cell(r.periode)}</td><td>${cell(r.record)}</td></tr>`).join("")}</tbody>
    </table>`;
    body.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => ctx.openActivity(b.dataset.act)));
  },
};

// ------------------------------------------------------ journée en détail
const DAY_KINDS = [["body_battery", "Body Battery"], ["fc", "FC"], ["sommeil", "Sommeil"], ["vfc", "VFC de la nuit"]];
const PHASES = ["profond", "léger", "paradoxal", "éveil"];
const PHASE_LABELS = { profond: "Profond", "léger": "Léger", paradoxal: "Paradoxal", "éveil": "Éveil" };

function timeAxis(P) {
  return {
    type: "time", axisLine: { lineStyle: { color: P.base } }, axisTick: { show: false }, splitLine: { show: false },
    axisLabel: { color: P.muted, fontSize: 12, hideOverlap: true, formatter: (v) => { const d = new Date(v); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; } },
  };
}

const hhmm = (t) => { const d = new Date(t); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };

function lineChart(P, d, kind) {
  const color = kind === "body_battery" ? P.series[2] : kind === "fc" ? P.bad : P.series[0];
  const name = { body_battery: "Body Battery", fc: "FC", vfc: "VFC" }[kind];
  const unit = { body_battery: "", fc: " bpm", vfc: " ms" }[kind];
  const data = d.points.map(([t, v]) => [new Date(t).getTime(), v]);
  return {
    ...C.baseOption(P),
    tooltip: { ...C.tooltipBase(P), formatter: (items) => C.tooltipHTML(hhmm(items[0].value[0]), [{ label: name, color, value: `${Math.round(items[0].value[1])}${unit}` }]) },
    xAxis: timeAxis(P),
    yAxis: C.valueAxis(P, { fmt: "int" }, kind === "body_battery" ? { min: 0, max: 100, scale: false } : {}),
    series: [{
      ...C.line(P, color, data, { name, area: kind === "body_battery" }),
      symbol: kind === "vfc" ? "circle" : "none", symbolSize: 4,
      markLine: kind === "fc" && d.repos ? { silent: true, symbol: "none", lineStyle: { color: P.ink2, type: "dashed", width: 1 },
        label: { formatter: `repos ${d.repos}`, color: P.muted, fontSize: 11 }, data: [{ yAxis: d.repos }] } : undefined,
    }],
  };
}

function sleepChart(P, d, w, h) {
  const colors = { profond: C.css("--sl-deep"), "léger": C.css("--sl-light"), paradoxal: C.css("--sl-rem"), "éveil": C.css("--sl-awake") };
  const blocks = d.phases.map((ph) => ({ value: [new Date(ph.debut).getTime(), new Date(ph.fin).getTime(), PHASES.indexOf(ph.phase)], itemStyle: { color: colors[ph.phase] } }));
  const hr = (d.fc || []).map(([t, v]) => [new Date(t).getTime(), v]);
  const { grids } = C.gridStack(hr.length ? 2 : 1, h, { top: 8, bottom: 24, gap: 18, weights: hr.length ? [3, 2] : [1] });
  const xAxes = grids.map((_, i) => ({ ...timeAxis(P), gridIndex: i, axisLabel: { ...timeAxis(P).axisLabel, show: i === grids.length - 1 } }));
  const min = blocks.length ? Math.min(...blocks.map((b) => b.value[0])) : undefined;
  const max = blocks.length ? Math.max(...blocks.map((b) => b.value[1])) : undefined;
  xAxes.forEach((a) => { a.min = min; a.max = max; });
  return {
    ...C.baseOption(P),
    grid: grids,
    tooltip: { ...C.tooltipBase(P, "item"), formatter: (it) => (it.seriesName === "FC"
      ? C.tooltipHTML(hhmm(it.value[0]), [{ label: "FC", value: `${Math.round(it.value[1])} bpm` }])
      : C.tooltipHTML(`${hhmm(it.value[0])} – ${hhmm(it.value[1])}`, [{ label: PHASE_LABELS[PHASES[it.value[2]]], color: it.color, value: F.duration((it.value[1] - it.value[0]) / 1000) }])) },
    xAxis: xAxes,
    yAxis: [
      { type: "category", gridIndex: 0, data: PHASES.map((x) => PHASE_LABELS[x]), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: P.muted, fontSize: 12 } },
      ...(hr.length ? [{ ...C.valueAxis(P, { fmt: "int" }, { gridIndex: 1, splitNumber: 2 }) }] : []),
    ],
    series: [
      {
        type: "custom", name: "Phases", xAxisIndex: 0, yAxisIndex: 0, data: blocks, encode: { x: [0, 1], y: 2 },
        renderItem: (params, api) => {
          const a = api.coord([api.value(0), api.value(2)]);
          const b = api.coord([api.value(1), api.value(2)]);
          const height = api.size([0, 1])[1] * 0.72;
          return { type: "rect", shape: { x: a[0], y: a[1] - height / 2, width: Math.max(1, b[0] - a[0]), height, r: 2 }, style: { fill: api.visual("color") } };
        },
      },
      ...(hr.length ? [{ ...C.line(P, P.bad, hr, { name: "FC", xAxisIndex: 1, yAxisIndex: 1 }), lineStyle: { width: 1.5, color: P.bad } }] : []),
    ],
  };
}

export const journee = {
  ownHead: true,
  title: (p) => DAY_KINDS.find(([k]) => k === p.donnee)?.[1] || "Journée en détail",
  async render(body, p, ctx, tile, keep) {
    let kind = p.donnee || "body_battery";
    let day = p.jour === "hier" ? F.addDays(new Date(), -1) : new Date();
    let chart = null;
    const title = () => tile.titre || `${DAY_KINDS.find(([k]) => k === kind)[1]}${kind === "sommeil" || kind === "vfc" ? "" : " de la journée"}`;

    const draw = async () => {
      chart?.dispose();
      chart = null;
      const iso = F.isoDate(day);
      const isToday = iso === F.isoDate(new Date());
      body.innerHTML = `<div class="tile-head tile-head-tools"><h2 class="tile-title">${F.escape(title())}</h2><span class="tile-sub" data-sub></span>
          <div class="day-nav">
            <select data-kind aria-label="Donnée affichée">${DAY_KINDS.map(([k, l]) => `<option value="${k}" ${k === kind ? "selected" : ""}>${l}</option>`).join("")}</select>
            <button class="btn btn-ghost icon-btn" type="button" data-day="-1" aria-label="Jour précédent">${icon("left")}</button>
            <span class="day-label">${isToday ? "Aujourd'hui" : F.escape(F.dateLong(iso))}</span>
            <button class="btn btn-ghost icon-btn" type="button" data-day="1" aria-label="Jour suivant" ${isToday ? "disabled" : ""}>${icon("right")}</button>
          </div></div>
        <div class="tile-body-inner"><div class="tile-msg">Chargement…</div></div>`;
      body.querySelector("[data-kind]").addEventListener("change", (e) => { kind = e.target.value; draw(); });
      body.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => { day = F.addDays(day, Number(b.dataset.day)); draw(); }));
      const inner = body.querySelector(".tile-body-inner");
      let d;
      try {
        d = await api.get("/api/journee", { donnee: kind, day: iso }, { fresh: isToday });
      } catch (err) {
        inner.innerHTML = `<div class="tile-msg">${F.escape(err.message)}</div>`;
        return;
      }
      if (!inner.isConnected) return;
      if (d.vide) {
        inner.innerHTML = `<div class="tile-msg">${F.escape(d.message || "Pas de donnée pour ce jour.")}</div>`;
        return;
      }
      const sub = body.querySelector("[data-sub]");
      const P = ctx.palette;
      let legend = "";
      if (kind === "sommeil") {
        const r = d.resume || {};
        sub.textContent = d.debut && d.fin ? `${hhmm(d.debut)} → ${hhmm(d.fin)}` : "";
        legend = C.legendHTML([
          { label: `Profond ${F.duration(r.sleep_deep_s)}`, color: C.css("--sl-deep"), kind: "square" },
          { label: `Léger ${F.duration(r.sleep_light_s)}`, color: C.css("--sl-light"), kind: "square" },
          { label: `Paradoxal ${F.duration(r.sleep_rem_s)}`, color: C.css("--sl-rem"), kind: "square" },
          { label: `Éveil ${F.duration(r.sleep_awake_s)}`, color: C.css("--sl-awake"), kind: "square" },
        ]);
      } else if (kind === "fc") {
        sub.textContent = [d.repos ? `repos ${d.repos} bpm` : null, d.max ? `max ${d.max} bpm` : null].filter(Boolean).join(", ");
      } else if (kind === "body_battery") {
        const last = d.points[d.points.length - 1];
        sub.textContent = last ? `${Math.round(last[1])} à ${hhmm(last[0])}${F.isNum(d.rechargee) ? `, +${d.rechargee} / −${d.depensee}` : ""}` : "";
      } else if (kind === "vfc") {
        sub.textContent = d.resume?.hrv_night ? `moyenne de la nuit ${d.resume.hrv_night} ms` : "";
      }
      if (d.message) sub.textContent = `${sub.textContent}${sub.textContent ? " · " : ""}${d.message}`;
      inner.innerHTML = `<div class="stack">${legend}<div class="chart-wrap"><div class="chart"></div></div></div>`;
      const el = inner.querySelector(".chart");
      chart = kind === "sommeil" ? C.mountSized(el, (w, h) => sleepChart(P, d, w, h)) : C.mount(el, lineChart(P, d, kind));
      keep(chart);
    };
    await draw();
  },
};

// ------------------------------------------------------------------ mon club
const ext = (href, label, cls = "btn", title = "") => `<a class="${cls}" href="${F.escape(href)}" target="_blank" rel="noopener"${title ? ` title="${F.escape(title)}"` : ""}>${label}${icon("external")}</a>`;

function licenceBlock(lic) {
  if (!lic?.renseignee) {
    return `<div class="club-licence">
        <h3>${icon("star")}Ma licence</h3>
        <p class="club-muted">Ajoute ta licence dans <a href="#/reglages?section=club">Réglages → Mon club</a> : Foulée te rappellera de la renouveler.</p>
      </div>`;
  }
  const until = F.dateLong(lic.expire, { year: true, weekday: false });
  const state = lic.expiree ? "bad" : lic.a_renouveler ? "warn" : "";
  const when = lic.expiree ? `Expirée depuis le ${until}` : `Valable jusqu'au ${until}`;
  return `<div class="club-licence ${state}">
      <h3>${icon("star")}Ma licence</h3>
      ${lic.type ? `<p class="club-licence-type">${F.escape(lic.type)}</p>` : ""}
      ${lic.numero ? `<p>N° <b>${F.escape(lic.numero)}</b></p>` : ""}
      <p>${when}${lic.expiree ? "" : ` <span class="club-muted">(${lic.jours_restants === 0 ? "aujourd'hui" : `dans ${F.int(lic.jours_restants)} jour${lic.jours_restants > 1 ? "s" : ""}`})</span>`}</p>
      ${state ? `<p class="club-licence-alert">${icon("warning")}${lic.expiree ? "Pense à la renouveler auprès de ton club." : "À renouveler bientôt, auprès de ton club."}</p>` : ""}
    </div>`;
}

export const club = {
  ownHead: true,
  title: () => "Mon club",
  async render(body, p, ctx) {
    const c = ctx.boot.club;
    if (!c) {
      body.innerHTML = `<div class="club club-empty">
          <span class="club-badge">${icon("club")}</span>
          <div><h2>Mon club</h2>
          <p>Indique ton club FFA dans <a href="#/reglages?section=club">Réglages → Mon club</a> : il te faut seulement le numéro de club inscrit sur ta licence.</p></div>
        </div>`;
      return;
    }
    const l = c.liens;
    const rows = [
      ["Président(e)", c.president && F.escape(c.president)],
      ["Siège", c.adresse_complete && `${F.escape(c.adresse_complete)}${l.carte ? ` · ${ext(l.carte, "Carte", "club-link")}` : ""}`],
      ["Téléphone", c.telephone && (l.telephone ? `<a class="club-link" href="${F.escape(l.telephone)}">${F.escape(c.telephone)}</a>` : F.escape(c.telephone))],
      ["E-mail", c.email && `<a class="club-link" href="${F.escape(l.email)}">${F.escape(c.email)}</a>`],
      ["Site", l.site && ext(l.site, F.escape(l.site.replace(/^https?:\/\/(www\.)?/i, "").replace(/\/$/, "")), "club-link")],
    ].filter(([, value]) => value);
    body.classList.add("scroll");
    body.innerHTML = `<div class="club">
        <header class="club-head">
          <span class="club-badge">${icon("club")}</span>
          <div class="club-title">
            <h2>${F.escape(c.nom || "Mon club")}</h2>
            <p><span class="nw">N° de club <b>${F.escape(c.numero)}</b></span> · <span class="nw">Saison ${F.escape(c.saison_label)}</span>${c.ville ? ` · <span class="nw">${F.escape(c.ville)}</span>` : ""}</p>
          </div>
          <a class="btn btn-ghost icon-btn club-edit" href="#/reglages?section=club" title="Modifier mon club" aria-label="Modifier mon club">${icon("edit")}</a>
        </header>
        <div class="club-actions">
          ${ext(l.classement, `${icon("trophy")}Classement ${F.escape(c.saison_label)}`, "btn btn-primary", "Classement du club sur athle.fr, saison en cours")}
          ${ext(l.classement_precedent, `Saison ${F.escape(l.saison_precedente)}`, "btn", `Classement du club sur athle.fr, saison ${l.saison_precedente}`)}
          ${l.page ? ext(l.page, "Page du club sur athle.fr") : ext(l.trouver, "Trouver le club sur athle.fr")}
          ${l.site ? ext(l.site, "Site du club") : ""}
        </div>
        <div class="club-cols">
          <div class="club-contact">
            <h3>${icon("info")}Coordonnées</h3>
            ${rows.length ? `<dl>${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>`
              : `<p class="club-muted">Colle la fiche du club dans <a href="#/reglages?section=club">Réglages → Mon club</a> : Foulée en tire le président, l'adresse, le téléphone et le site.</p>`}
          </div>
          ${licenceBlock(c.licence)}
        </div>
        <p class="club-note">${icon("info")}<span>Le classement et la page du club s'ouvrent sur athle.fr, le site de la FFA : toujours à jour.</span></p>
      </div>`;
  },
};
