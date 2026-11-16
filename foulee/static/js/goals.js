// Objectifs : la tuile « Objectifs » de l'Accueil (le principal, et dessous les secondaires à venir), le centre de
// gestion (tuile « Mes objectifs » de la vue Objectifs, et Réglages → Objectifs) et la fiche d'un objectif.
import * as api from "./api.js";
import { openDialog } from "./editor.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

export const SEMI = 21.0975;
export const DISTANCES = [["5", "5 km"], ["10", "10 km"], [String(SEMI), "Semi-marathon"], ["42.195", "Marathon"], ["autre", "Autre distance"]];

/** « 1:25:00 » ou « 38:30 » → secondes (null si illisible). */
export function hms(text) {
  const value = String(text || "").trim();
  if (!/^\d{1,3}(:\d{1,2}){1,2}$/.test(value)) return null;
  const parts = value.split(":").map(Number);
  while (parts.length < 3) parts.unshift(0);
  const total = parts[0] * 3600 + parts[1] * 60 + parts[2];
  return total > 0 ? total : null;
}

/** Comme côté serveur : deux nombres se lisent mm:ss, sauf si l'allure devient impossible (« 1:25 » sur un semi : 1 h 25). */
export function targetSecs(text, km) {
  const secs = hms(text);
  if (!secs) return null;
  return String(text).trim().split(":").length === 2 && km && (km * 3600) / secs > 26 ? secs * 60 : secs;
}

const plural = (n, word) => `${n} ${word}${Math.abs(n) > 1 ? "s" : ""}`;

/** « 21,1 km » ou « Semi-marathon », avec le dénivelé s'il y en a. */
function distanceText(g, { long = false } = {}) {
  const parts = [];
  if (F.isNum(g.distance_km) && g.distance_km > 0) {
    const named = DISTANCES.find(([v]) => v !== "autre" && Math.abs(Number(v) - g.distance_km) < 0.01);
    parts.push(named && (long || named[1].length < 10) ? named[1] : `${F.dec1(g.distance_km).replace(",0", "")} km`);
  }
  if (F.isNum(g.d_plus_m) && g.d_plus_m > 0) parts.push(`${F.int(g.d_plus_m)} m D+`);
  return parts.join(" · ");
}

/** Le compte à rebours en toutes lettres : « dans 12 jours », « demain », « aujourd'hui ». */
function whenText(g) {
  const left = g.jours_restants;
  if (!F.isNum(left)) return "";
  if (left === 0) return "aujourd'hui";
  if (left === 1) return "demain";
  if (left < 0) return left === -1 ? "hier" : `il y a ${plural(-left, "jour")}`;
  if (left < 21) return `dans ${plural(left, "jour")}`;
  return `dans ${F.dec1(left / 7).replace(",0", "")} semaines`;
}

const jMinus = (g) => (F.isNum(g.jours_restants) ? (g.jours_restants === 0 ? "Jour J" : g.jours_restants > 0 ? `J−${g.jours_restants}` : "Passé") : "");

/** Écart de temps signé : « −25 s », « +1:05 ». */
function gapText(seconds) {
  if (!F.isNum(seconds)) return "";
  const sign = seconds > 0 ? "+" : seconds < 0 ? "−" : "±";
  const s = Math.abs(Math.round(seconds));
  return `${sign}${s < 60 ? `${s} s` : F.chrono(s)}`;
}

function gapClass(seconds, tolerance = 15) {
  if (!F.isNum(seconds)) return "";
  return seconds <= tolerance ? "gm-good" : seconds <= 90 ? "gm-warn" : "gm-bad";
}

function dateBlock(g) {
  if (!g.date) return `<span class="gm-date gm-date--none">${icon("flag")}</span>`;
  const d = F.parseDate(g.date);
  const month = new Intl.DateTimeFormat("fr-FR", { month: "short" }).format(d).replace(".", "");
  return `<span class="gm-date"><b>${d.getDate()}</b><small>${F.escape(month)}${d.getFullYear() !== new Date().getFullYear() ? ` ${String(d.getFullYear()).slice(2)}` : ""}</small></span>`;
}

// ================================================================ tuile « Objectifs » de l'Accueil
function homeRow(g) {
  const facts = [distanceText(g), g.temps_cible].filter(Boolean).join(" · ");
  return `<li class="goal-item">${dateBlock(g)}
      <span class="goal-item-text"><b title="${F.escape(g.nom)}">${F.escape(g.nom)}</b>${facts ? `<small>${F.escape(facts)}</small>` : ""}</span>
      <span class="goal-item-j">${F.escape(jMinus(g))}</span></li>`;
}

export const objectif = {
  title: () => "Objectifs",
  async render(body, p, ctx) {
    const o = await ctx.get("/api/objective");
    const next = (o.secondaires || []).filter((g) => g.statut !== "passe")
      .sort((a, b) => String(a.date || "9999").localeCompare(String(b.date || "9999")));
    const manage = ctx.viewWith?.("objectifs");
    const link = `<a class="goal-manage" href="${manage ? `#/vue/${encodeURIComponent(manage)}` : "#/reglages?section=objectif"}">${icon("edit")}Gérer</a>`;
    const hasMain = Boolean(o.nom) && (!o.date || o.jours_restants >= 0);
    if (!hasMain && !next.length) {
      body.innerHTML = `<div class="goal goal-empty"><p>${o.nom && o.jours_restants < 0 ? `« ${F.escape(o.nom)} » est passé. Choisis ton prochain objectif.` : "Pas encore d'objectif. Une course en vue ?"}</p>${link.replace("Gérer", "Choisir un objectif")}</div>`;
      return;
    }
    const left = o.jours_restants;
    const counter = !hasMain || !o.date ? "" : left > 0 ? `${left}<small>jour${left > 1 ? "s" : ""}</small>` : "Jour J";
    const pct = F.isNum(o.pct_vma) ? `${Math.round(o.pct_vma)} %` : "–";
    const main = hasMain ? `<div class="goal-top">
        <div class="goal-id"><div class="goal-name" title="${F.escape(o.nom)}">${F.escape(o.nom)}</div>
          <div class="goal-meta">${F.escape([o.date ? F.dateLong(o.date, { year: true, weekday: false }) : "Date à préciser", distanceText(o)].filter(Boolean).join(" · "))}</div></div>
        ${next.length && counter ? `<div class="goal-count">${counter}</div>` : ""}
      </div>` : `<div class="goal-top"><div class="goal-id"><div class="goal-name">Objectif principal</div><div class="goal-meta">${o.nom ? `« ${F.escape(o.nom)} » est passé : choisis le suivant.` : "Pas encore choisi."}</div></div></div>`;
    if (!next.length) {  // pas de secondaire : la présentation d'origine, en grand
      body.innerHTML = `<div class="goal">
        ${main}
        ${counter ? `<div class="goal-count">${counter}</div>` : ""}
        <dl class="goal-rows">
          <dt>Temps visé</dt><dd>${F.escape(o.temps_cible || "–")}</dd>
          <dt>Allure cible</dt><dd>${F.escape(o.allure_cible || "–")}</dd>
          <dt>Vitesse</dt><dd>${F.isNum(o.vitesse_cible_kmh) ? `${F.dec1(o.vitesse_cible_kmh)} km/h` : "–"}</dd>
          <dt>Part de ta VMA</dt><dd>${F.isNum(o.pct_vma) ? `${Math.round(o.pct_vma)} % de ${F.dec1(ctx.settings.vma_kmh)} km/h` : "–"}</dd>
        </dl>
        ${link}
      </div>`;
      return;
    }
    body.innerHTML = `<div class="goal goal--compact">
      ${main}
      ${hasMain ? `<dl class="goal-mini">
        <div><dt>Visé</dt><dd>${F.escape(o.temps_cible || "–")}</dd></div>
        <div><dt>Allure</dt><dd>${F.escape((o.allure_cible || "–").replace(" /km", ""))}</dd></div>
        <div><dt>VMA</dt><dd>${pct}</dd></div>
      </dl>` : ""}
      <div class="goal-next">
        <div class="goal-next-head"><span>Ensuite</span><span class="goal-next-n">${next.length}</span>${link}</div>
        <ul class="goal-list">${next.map(homeRow).join("")}</ul>
      </div>
    </div>`;
  },
};

// ================================================================ fiche d'un objectif
/** Ajout ou modification d'un objectif. Résout avec le contenu à envoyer, ou null. */
export function editGoal(goal = null, { vma = 16, canPrincipal = false, isPrincipal = false } = {}) {
  const g = goal || {};
  const preset = DISTANCES.find(([v]) => v !== "autre" && Math.abs(Number(v) - Number(g.distance_km)) < 0.001);
  const presetValue = g.distance_km ? (preset ? preset[0] : "autre") : (goal ? "autre" : "10");
  return new Promise((resolve) => {
    const dialog = openDialog(`<form class="dlg dlg-goal" method="dialog" novalidate>
      <div class="dlg-head"><h2>${goal ? (isPrincipal ? "Objectif principal" : "Modifier l'objectif") : "Nouvel objectif"}</h2>
        <p>${isPrincipal ? "Le compte à rebours, l'allure cible et les fractions rapides s'y rapportent." : "Une course de préparation, une autre épreuve, un rendez-vous à ne pas manquer."}</p></div>
      <div class="dlg-body">
        <div class="form-grid">
          <label class="field gm-wide"><span>Nom</span><input type="text" name="nom" maxlength="80" required value="${F.escape(g.nom || "")}" placeholder="10 km de Reims"></label>
          <label class="field"><span>Date</span><input type="date" name="date" value="${F.escape(g.date || "")}"></label>
          <label class="field"><span>Distance</span><select name="preset">${DISTANCES.map(([v, l]) => `<option value="${v}" ${presetValue === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          <label class="field" data-custom ${presetValue === "autre" ? "" : "hidden"}><span>Distance (km)</span><input type="number" step="0.001" min="0.1" max="1000" name="distance" value="${F.escape(g.distance_km ?? "")}" placeholder="25"></label>
          <label class="field"><span>Dénivelé positif (m)</span><input type="number" step="10" min="0" max="30000" name="dplus" value="${F.escape(g.d_plus_m ?? "")}" placeholder="facultatif"></label>
          <label class="field"><span>Temps visé (h:mm:ss)</span><input type="text" name="temps" inputmode="numeric" value="${F.escape(g.temps_cible || "")}" placeholder="1:25:00 ou 38:30"></label>
          <label class="field gm-wide"><span>Note</span><input type="text" name="note" maxlength="200" value="${F.escape(g.note || "")}" placeholder="facultatif : dossard, objectif de chrono, partir prudemment…"></label>
        </div>
        ${canPrincipal ? `<label class="check gm-principal"><input type="checkbox" name="principal">En faire mon objectif principal <small>(l'actuel rejoint les objectifs secondaires)</small></label>` : ""}
        <p class="computed" data-computed></p>
        <p class="form-error" data-error hidden></p>
      </div>
      <div class="dlg-foot"><button class="btn" value="cancel" type="submit" formnovalidate>Annuler</button><button class="btn btn-primary" value="ok" type="submit">${goal ? "Enregistrer" : "Ajouter"}</button></div>
    </form>`);
    const form = dialog.querySelector("form");
    const field = (name) => form.elements[name];
    const distance = () => (field("preset").value === "autre" ? Number(String(field("distance").value).replace(",", ".")) || null : Number(field("preset").value));
    const refresh = () => {
      form.querySelector("[data-custom]").hidden = field("preset").value !== "autre";
      const km = distance();
      const secs = targetSecs(field("temps").value, km);
      const out = form.querySelector("[data-computed]");
      if (km && secs) {
        const speed = (km * 1000) / secs;
        out.innerHTML = `Allure cible <b>${F.pace(speed)} /km</b>, soit <b>${F.dec1(speed * 3.6)} km/h</b> et <b>${Math.round((speed * 3.6 / (vma || 16)) * 100)} %</b> de ta VMA.`;
      } else {
        out.textContent = "Avec une distance et un temps visé, Foulée calcule l'allure cible.";
      }
    };
    form.addEventListener("input", refresh);
    refresh();
    setTimeout(() => field("nom").focus(), 30);
    form.addEventListener("submit", (e) => {
      const ok = e.submitter?.value === "ok";
      if (!ok) return;
      const error = form.querySelector("[data-error]");
      const fail = (text, name) => { e.preventDefault(); error.textContent = text; error.hidden = false; field(name)?.focus(); };
      if (!field("nom").value.trim()) return fail("Donne un nom à l'objectif (la course, l'épreuve…).", "nom");
      if (field("temps").value.trim() && !hms(field("temps").value)) return fail("Temps visé illisible : h:mm:ss, par exemple 1:25:00 (ou 38:30).", "temps");
      if (field("preset").value === "autre" && field("distance").value && !distance()) return fail("Distance illisible : un nombre de kilomètres.", "distance");
      error.hidden = true;
    });
    dialog.addEventListener("close", () => {
      if (dialog.returnValue !== "ok") return resolve(null);
      resolve({
        nom: field("nom").value.trim(), date: field("date").value || "",
        distance_km: distance(), d_plus_m: field("dplus").value === "" ? null : Number(field("dplus").value),
        temps_cible: field("temps").value.trim(), note: field("note").value.trim(),
        principal: canPrincipal ? field("principal").checked : undefined,
      });
    });
  });
}

// ================================================================ centre de gestion
function facts(g, vma) {
  const items = [
    ["Distance", distanceText(g, { long: true }) || "–"],
    ["Temps visé", g.temps_cible || "–"],
    ["Allure cible", g.allure_cible || "–"],
    ["Part de ta VMA", F.isNum(g.pct_vma) ? `${Math.round(g.pct_vma)} %${vma ? ` de ${F.dec1(vma)} km/h` : ""}` : "–"],
  ];
  return `<dl class="gm-facts">${items.map(([k, v]) => `<div><dt>${k}</dt><dd>${F.escape(v)}</dd></div>`).join("")}</dl>`;
}

function principalCard(d) {
  const p = d.principal;
  const past = d.principal_passe;
  if (!p) {
    const next = d.secondaires.find((g) => g.id === d.suivant);
    const res = past?.resultat;
    return `<div class="gm-main gm-main--empty">
      <span class="gm-kicker">${icon("flag")}Objectif principal</span>
      ${past ? `<h3>${F.escape(past.nom)} : c'est passé</h3>
        <p class="gm-lead">${F.escape(F.dateLong(past.date, { year: true }))}${res ? ` · réalisé en <b>${F.escape(res.temps || "–")}</b>${F.isNum(res.ecart_s) && past.temps_cible ? ` <span class="${gapClass(res.ecart_s)}">(${gapText(res.ecart_s)} sur le temps visé)</span>` : ""}` : ""}.</p>`
        : `<h3>Pas encore d'objectif principal</h3><p class="gm-lead">Le compte à rebours de l'Accueil, l'allure cible et les fractions rapides s'y rapportent.</p>`}
      <div class="gm-actions">
        ${next ? `<button type="button" class="btn btn-primary" data-act="promote" data-id="${F.escape(next.id)}">${icon("star")}En faire l'objectif principal : ${F.escape(next.nom)}</button>` : ""}
        <button type="button" class="btn ${next ? "" : "btn-primary"}" data-act="add-principal">${icon("plus")}${past ? "Nouvel objectif principal" : "Choisir mon objectif principal"}</button>
      </div>
    </div>`;
  }
  const left = p.jours_restants;
  const big = !F.isNum(left) ? "" : left === 0 ? `<b>Jour J</b>` : `<b>${left}</b><small>jour${left > 1 ? "s" : ""}</small>`;
  return `<div class="gm-main">
    <div class="gm-main-head">
      <div><span class="gm-kicker">${icon("flag")}Objectif principal</span>
        <h3 title="${F.escape(p.nom)}">${F.escape(p.nom)}</h3>
        <p class="gm-lead">${p.date ? F.escape(F.dateLong(p.date, { year: true })) : "Date à préciser"}${p.date && left > 0 ? ` · ${F.escape(whenText(p))}` : ""}</p></div>
      ${big ? `<div class="gm-count">${big}</div>` : ""}
    </div>
    ${facts(p, d.vma_kmh)}
    ${p.note ? `<p class="gm-note">${F.escape(p.note)}</p>` : ""}
    <div class="gm-actions"><button type="button" class="btn btn-small" data-act="edit" data-id="principal">${icon("edit")}Modifier</button>
      <button type="button" class="btn btn-small btn-ghost" data-act="delete" data-id="principal">${icon("trash")}Retirer</button></div>
  </div>`;
}

/** « au semi », « au marathon », « sur 10 km » : la distance de l'objectif principal, en deux mots. */
function overDistance(principal) {
  const km = principal?.distance_km;
  if (!F.isNum(km)) return "";
  if (Math.abs(km - SEMI) < 0.01) return "au semi";
  if (Math.abs(km - 42.195) < 0.01) return "au marathon";
  return `sur ${F.dec1(km).replace(",0", "")} km`;
}

function equivalenceText(eq, principal) {
  if (!eq) return "";
  const target = principal?.temps_cible;
  const tip = `Équivalence de Riegel : ce temps ramené à la distance de « ${eq.vers} ». Une estimation à distance égale, pas une prédiction.`;
  const gap = F.isNum(eq.ecart_s) && target ? ` <span class="${gapClass(eq.ecart_s, 0)}">(${gapText(eq.ecart_s)} sur le ${F.escape(target)} visé)</span>` : "";
  return `<small class="gm-eq" title="${F.escape(tip)}">≈ ${F.escape(eq.temps)} ${F.escape(overDistance(principal))}${gap}</small>`;
}

function secondaryRow(g, d) {
  const bits = [distanceText(g), g.temps_cible && `visé ${g.temps_cible}`, g.allure_cible].filter(Boolean);
  const weeks = g.avant_principal_jours;
  const before = F.isNum(weeks) && d.principal
    ? `<small class="gm-before" title="${F.escape(`${plural(weeks, "jour")} avant ${d.principal.nom}`)}">${weeks < 14 ? `J−${weeks}` : `${Math.round(weeks / 7)} sem.`} avant le principal</small>` : "";
  return `<li class="gm-row">
    ${dateBlock(g)}
    <div class="gm-row-text"><b title="${F.escape(g.nom)}">${F.escape(g.nom)}</b>
      <small>${F.escape(bits.join(" · ") || "Distance et temps à préciser")}</small>
      ${equivalenceText(g.equivalence, d.principal)}
      ${g.note ? `<small class="gm-row-note">${F.escape(g.note)}</small>` : ""}</div>
    <div class="gm-row-side"><span class="gm-j">${F.escape(jMinus(g) || "Sans date")}</span>${before}</div>
    <div class="gm-tools">
      <button type="button" class="gm-mini" data-act="promote" data-id="${F.escape(g.id)}" title="En faire l'objectif principal" aria-label="En faire l'objectif principal">${icon("star")}</button>
      <button type="button" class="gm-mini" data-act="edit" data-id="${F.escape(g.id)}" title="Modifier" aria-label="Modifier">${icon("edit")}</button>
      <button type="button" class="gm-mini" data-act="delete" data-id="${F.escape(g.id)}" title="Supprimer" aria-label="Supprimer">${icon("trash")}</button>
    </div>
  </li>`;
}

function pastRow(g, d) {
  const res = g.resultat;
  let result = `<small>Pas de séance retrouvée ce jour-là à la bonne distance.</small>`;
  if (res) {
    const vs = F.isNum(res.ecart_s) && g.temps_cible ? ` <span class="${gapClass(res.ecart_s)}">${gapText(res.ecart_s)} sur le ${F.escape(g.temps_cible)} visé</span>` : "";
    result = `<small>Réalisé en <b>${F.escape(res.temps || "–")}</b>${res.allure ? ` (${F.escape(res.allure)})` : ""}${vs}</small>${equivalenceText(g.equivalence, d.principal)}`;
  }
  return `<li class="gm-row gm-row--past">
    ${dateBlock(g)}
    <div class="gm-row-text"><b title="${F.escape(g.nom)}">${F.escape(g.nom)}${g.id === "principal" ? ` <span class="gm-tag">principal</span>` : ""}</b>${result}</div>
    <div class="gm-tools">
      ${res?.seance_id ? `<button type="button" class="gm-mini" data-act="open" data-seance="${F.escape(res.seance_id)}" title="Voir la séance" aria-label="Voir la séance">${icon("right")}</button>` : ""}
      ${g.id !== "principal" ? `<button type="button" class="gm-mini" data-act="delete" data-id="${F.escape(g.id)}" title="Supprimer" aria-label="Supprimer">${icon("trash")}</button>` : ""}
    </div>
  </li>`;
}

function calendarRow(c) {
  return `<li class="gm-row gm-row--cal">${dateBlock(c)}
    <div class="gm-row-text"><b title="${F.escape(c.nom)}">${F.escape(c.nom)}</b><small>${F.escape([c.lieu, distanceText(c)].filter(Boolean).join(" · ") || "Dans ton calendrier")}</small></div>
    <div class="gm-row-side"><span class="gm-j">J−${c.dans_jours}</span></div>
    <div class="gm-tools"><button type="button" class="btn btn-small" data-act="from-cal" data-date="${F.escape(c.date)}">${icon("plus")}Ajouter</button></div>
  </li>`;
}

/**
 * Le centre des objectifs, dans une tuile ou dans les Réglages.
 * onChange(res, { principal }) : après chaque modification (res contient « objectif » et « reglages »).
 */
export async function goalManager(box, { toast, onChange, openActivity, vma } = {}) {
  let d = await api.get("/api/objectifs", null, { fresh: true });
  let pastOpen = false;

  const draw = () => {
    const others = d.secondaires;
    box.innerHTML = `<div class="gm">
      <div class="gm-col">
        ${principalCard(d)}
        ${d.calendrier.length ? `<div class="gm-sub"><h5>${icon("calendar")}Dans ton calendrier</h5><ul class="gm-list">${d.calendrier.slice(0, 4).map(calendarRow).join("")}</ul></div>` : ""}
        ${d.passes.length ? `<details class="gm-sub gm-past" ${pastOpen ? "open" : ""}><summary><h5>${icon("trophy")}Passés <span class="gm-n">${d.passes.length}</span></h5></summary>
          <ul class="gm-list">${d.passes.map((g) => pastRow(g, d)).join("")}</ul></details>` : ""}
      </div>
      <div class="gm-side">
        <div class="gm-side-head"><h4>Objectifs secondaires${others.length ? ` <span class="gm-n">${others.length}</span>` : ""}</h4>
          <button type="button" class="btn btn-small" data-act="add">${icon("plus")}Ajouter</button></div>
        ${others.length ? `<ul class="gm-list">${others.map((g) => secondaryRow(g, d)).join("")}</ul>`
          : `<p class="gm-empty">Tes courses de préparation, un 10 km pour se tester, une autre épreuve : ajoute-les ici. Le plus proche s'affiche sur l'Accueil, sous l'objectif principal.</p>`}
      </div>
    </div>`;
  };

  const find = (id) => (id === "principal" ? (d.principal || d.principal_passe) : [...d.secondaires, ...d.passes].find((g) => g.id === id));
  const apply = async (call, message, principalChanged) => {
    try {
      const res = await call();
      d = res;
      draw();
      if (message) toast?.(message);
      onChange?.(res, { principal: principalChanged });
    } catch (err) {
      toast?.(err.message, { error: true });
    }
  };

  box.addEventListener("toggle", (e) => { if (e.target.matches?.(".gm-past")) pastOpen = e.target.open; }, true);
  box.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn || !box.contains(btn)) return;
    const { act, id } = btn.dataset;
    const vmaNow = vma?.() ?? d.vma_kmh;
    if (act === "add" || act === "add-principal") {
      const goal = await editGoal(null, { vma: vmaNow, canPrincipal: act === "add", isPrincipal: act === "add-principal" });
      if (!goal) return;
      if (act === "add-principal") goal.principal = true;
      await apply(() => api.post("/api/objectifs", goal), goal.principal ? "Objectif principal enregistré." : "Objectif ajouté.", goal.principal);
    } else if (act === "edit") {
      const current = find(id);
      const goal = await editGoal(current, { vma: vmaNow, isPrincipal: id === "principal" });
      if (!goal) return;
      await apply(() => api.put(`/api/objectifs/${encodeURIComponent(id)}`, goal), "Objectif enregistré.", id === "principal");
    } else if (act === "delete") {
      const current = find(id);
      const text = id === "principal"
        ? `Retirer « ${current?.nom} » de ton objectif principal ? Tu pourras en choisir un autre, ou promouvoir un objectif secondaire.`
        : `Supprimer l'objectif « ${current?.nom} » ?`;
      if (!window.confirm(text)) return;
      await apply(() => api.del(`/api/objectifs/${encodeURIComponent(id)}`), id === "principal" ? "Objectif principal retiré." : "Objectif supprimé.", id === "principal");
    } else if (act === "promote") {
      const current = find(id);
      await apply(() => api.post(`/api/objectifs/${encodeURIComponent(id)}/principal`), `« ${current?.nom} » est ton objectif principal.`, true);
    } else if (act === "from-cal") {
      const race = d.calendrier.find((c) => c.date === btn.dataset.date);
      const goal = await editGoal({ nom: race.nom, date: race.date, distance_km: race.distance_km }, { vma: vmaNow, canPrincipal: true });
      if (!goal) return;
      await apply(() => api.post("/api/objectifs", goal), goal.principal ? "Objectif principal enregistré." : "Objectif ajouté.", goal.principal);
    } else if (act === "open" && openActivity) {
      openActivity(btn.dataset.seance);
    }
  });
  draw();
}

// ================================================================ tuile « Mes objectifs »
export const objectifs = {
  title: () => "Mes objectifs",
  async render(body, p, ctx) {
    body.classList.add("scroll", "gm-body");
    await goalManager(body, {
      toast: ctx.toast,
      openActivity: ctx.openActivity,
      onChange: (res, { principal }) => ctx.goalsChanged?.(res, principal),
    });
  },
};
