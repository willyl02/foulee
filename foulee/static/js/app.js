// Foulée : chef d'orchestre de l'interface (navigation, vues, tuiles, édition, synchro, thème).
import * as api from "./api.js";
import * as C from "./charts.js";
import * as E from "./editor.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { renderSettings } from "./settings.js";
import * as A from "./tiles-activity.js";
import * as D from "./tiles-data.js";

const RENDERERS = {
  kpi: D.kpi, serie: D.serie, charge: D.charge, zones: D.zones, calendrier: D.calendrier, nuage: D.nuage,
  postes: D.postes, objectif: D.objectif, fractions: D.fractions, note: D.note,
  activites: A.activites, derniere_seance: A.derniere_seance, seance_resume: A.seance_resume,
  seance_carte: A.seance_carte, seance_courbes: A.seance_courbes, seance_tours: A.seance_tours,
};
const PERIODS = [[7, "7 j"], [30, "30 j"], [90, "90 j"], [180, "6 mois"], [365, "1 an"], [730, "2 ans"]];
const WIDTHS = [3, 4, 6, 8, 12];
const THEMES = ["auto", "light", "dark"];
const THEME_LABELS = { auto: "Thème : automatique", light: "Thème : clair", dark: "Thème : sombre" };

const state = {
  boot: null, catalog: {}, types: {}, views: [], viewId: null, days: 90, editing: false,
  activityId: null, pass: { token: 0, disposers: [] }, syncTimer: null, dragIndex: null,
};

const $ = (sel, root = document) => root.querySelector(sel);

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
  } catch (e) { /* stockage indisponible */ }
  return null;
}

export function toast(text, { error = false } = {}) {
  const box = document.createElement("div");
  box.className = `toast${error ? " error" : ""}`;
  box.textContent = text;
  $("#toasts").appendChild(box);
  setTimeout(() => box.remove(), error ? 7000 : 4500);
}

// =================================================================== démarrage
async function start() {
  try {
    await loadBoot();
  } catch (err) {
    const hint = isLocalHost() ? "Relance « foulee web »." : "Vérifie que Tailscale est connecté sur cet appareil.";
    $("#page").innerHTML = `<div class="tile-msg" style="position:static;padding:60px 0">Le serveur Foulée ne répond pas (${F.escape(err.message)}). ${hint}</div>`;
    return;
  }
  registerServiceWorker();
  state.days = Number(store("foulee-period")) || 90;
  setupChrome();
  window.addEventListener("hashchange", route);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (themeChoice() === "auto") rerender(); });
  route();
  if (state.boot.synchro?.en_cours) pollSync();
}

function isLocalHost() {
  return ["127.0.0.1", "localhost"].includes(location.hostname);
}

// Sur le serveur (adresse Tailscale en HTTPS), Foulée s'installe comme une appli sur l'écran d'accueil.
// Sur le PC, inutile : l'interface est servie par la machine elle-même.
function registerServiceWorker() {
  if (isLocalHost() || !("serviceWorker" in navigator) || !window.isSecureContext) return;
  navigator.serviceWorker.register("/sw.js").catch(() => { /* l'interface marche aussi sans */ });
}

async function loadBoot() {
  state.boot = await api.get("/api/bootstrap", null, { fresh: true });
  state.catalog = Object.fromEntries(state.boot.metriques.map((m) => [m.key, m]));
  state.types = Object.fromEntries(state.boot.tuiles.map((t) => [t.type, t]));
  state.views = state.boot.vues;
}

function setupChrome() {
  $("#sync-btn").innerHTML = `${icon("sync")}Synchroniser`;
  $("#sync-btn").addEventListener("click", startSync);
  $("#settings-btn").innerHTML = `${icon("settings")}Réglages`;
  $("#settings-btn").addEventListener("click", () => { location.hash = "#/reglages"; closeMenu(); });
  $("#menu-btn").innerHTML = icon("menu");
  $("#menu-btn").addEventListener("click", () => $("#rail").classList.toggle("open"));
  $("#theme-btn").addEventListener("click", cycleTheme);
  paintTheme();
  if (state.boot.demo) {
    $("#demo-strip").innerHTML = `<div class="demo-strip">${icon("info")}<span>Mode démo : toutes les données sont fictives. Pour les tiennes, lance « foulee setup » puis « foulee web ».</span></div>`;
  } else if (!state.boot.volumes.daily && !state.boot.volumes.activities) {
    $("#demo-strip").innerHTML = state.boot.cle
      ? `<div class="demo-strip">${icon("info")}<span>Pas encore de données : clique sur « Synchroniser » à gauche pour lancer le premier import.</span></div>`
      : `<div class="demo-strip">${icon("info")}<span>Pas encore de clé API : double-clique sur « Configurer-cle-Garmin.cmd » dans le dossier Foulee, puis reviens ici.</span></div>`;
  }
  renderNav();
  renderSyncLine();
}

function closeMenu() { $("#rail").classList.remove("open"); }

// ======================================================================= thème
function themeChoice() { return store("foulee-theme") || "auto"; }

function paintTheme() {
  const choice = themeChoice();
  if (choice === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  const btn = $("#theme-btn");
  btn.innerHTML = icon("contrast");
  btn.title = THEME_LABELS[choice];
  btn.setAttribute("aria-label", THEME_LABELS[choice]);
}

function cycleTheme() {
  const next = THEMES[(THEMES.indexOf(themeChoice()) + 1) % THEMES.length];
  store("foulee-theme", next === "auto" ? null : next);
  paintTheme();
  toast(THEME_LABELS[next]);
  rerender();
}

// ================================================================== navigation
function renderNav() {
  const nav = $("#nav");
  nav.innerHTML = state.views.map((v, i) => `<button class="nav-item" type="button" data-id="${F.escape(v.id)}" data-index="${i}"
      ${v.id === state.viewId && !isSettings() ? 'aria-current="page"' : ""} ${state.editing ? 'draggable="true"' : ""}>
      ${icon(v.icon)}<span>${F.escape(v.name)}</span><span class="blaze" aria-hidden="true"></span></button>`).join("")
    + `<button class="nav-item nav-add" type="button" data-new>${icon("plus")}<span>Nouvelle vue</span></button>`;
  nav.querySelectorAll("[data-id]").forEach((b) => {
    b.addEventListener("click", () => { location.hash = `#/vue/${encodeURIComponent(b.dataset.id)}`; closeMenu(); });
    if (state.editing) wireNavDrag(b);
  });
  nav.querySelector("[data-new]").addEventListener("click", newView);
}

function wireNavDrag(item) {
  item.addEventListener("dragstart", (e) => { e.dataTransfer.effectAllowed = "move"; item.classList.add("dragging"); state.navDrag = Number(item.dataset.index); });
  item.addEventListener("dragend", () => item.classList.remove("dragging"));
  item.addEventListener("dragover", (e) => e.preventDefault());
  item.addEventListener("drop", async (e) => {
    e.preventDefault();
    const from = state.navDrag;
    const to = Number(item.dataset.index);
    if (from === to || from == null) return;
    const [moved] = state.views.splice(from, 1);
    state.views.splice(to, 0, moved);
    renderNav();
    await api.post("/api/views/reorder", { ids: state.views.map((v) => v.id) });
  });
}

function isSettings() { return location.hash.startsWith("#/reglages"); }

function route() {
  const [path, query] = location.hash.slice(1).split("?");
  if (path === "/reglages") { showSettings(); return; }
  const match = path.match(/^\/vue\/([^/]+)/);
  const wanted = match ? decodeURIComponent(match[1]) : null;
  const view = state.views.find((v) => v.id === wanted) || state.views[0];
  state.viewId = view?.id || null;
  const seance = new URLSearchParams(query || "").get("seance");
  if (seance) state.activityId = seance;
  renderNav();
  renderView();
}

function currentView() { return state.views.find((v) => v.id === state.viewId); }

function rerender() {
  if (isSettings()) showSettings(); else renderView();
}

// ======================================================================= vue
function disposePass() {
  state.pass.disposers.forEach((d) => { try { d.dispose(); } catch (e) { /* déjà libéré */ } });
  state.pass = { token: state.pass.token + 1, disposers: [] };
}

function shiftChip() {
  const today = new Date();
  const { week } = F.isoWeek(today);
  const postes = state.boot.reglages.postes || {};
  if (postes.actif === false) return `<span class="shift-chip">Semaine ${week}</span>`;
  const label = F.shiftOf(today, state.boot.reglages, false);
  const color = label === "matin" ? "var(--s1)" : "var(--s2)";
  return `<span class="shift-chip" title="Semaine ISO ${week}, ${week % 2 ? "impaire" : "paire"}"><i class="dot" style="background:${color}"></i>Semaine ${week}, poste du ${label}</span>`;
}

async function renderView() {
  disposePass();
  const token = state.pass.token;
  const page = $("#page");
  const view = currentView();
  if (!view) {
    page.innerHTML = `<div class="tile-msg" style="position:static;padding:60px 0">Aucune vue. Crée-en une avec « Nouvelle vue ».</div>`;
    return;
  }
  const needsActivity = view.spec.tuiles.some((t) => t.type.startsWith("seance_"));
  const todayIso = F.isoDate(new Date());
  page.innerHTML = `
    <header class="head">
      <div><h1>${F.escape(view.name)}</h1>
        <div class="head-sub"><span>${F.escape(F.dateLong(todayIso))}</span>${shiftChip()}</div></div>
      <div class="head-tools">
        <div class="segmented" role="group" aria-label="Période affichée">${PERIODS.map(([d, l]) =>
          `<button type="button" data-days="${d}" aria-pressed="${d === state.days}">${l}</button>`).join("")}</div>
        <button class="btn${state.editing ? " btn-primary" : ""}" type="button" data-edit>${icon(state.editing ? "check" : "edit")}${state.editing ? "Terminer" : "Modifier la vue"}</button>
      </div>
    </header>
    ${state.editing ? viewBar() : ""}
    ${needsActivity ? '<div class="picker" id="picker"></div>' : ""}
    <div class="grid${state.editing ? " editing" : ""}" id="grid"></div>`;

  page.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => {
    state.days = Number(b.dataset.days);
    store("foulee-period", String(state.days));
    renderView();
  }));
  page.querySelector("[data-edit]").addEventListener("click", () => { state.editing = !state.editing; renderNav(); renderView(); });
  if (state.editing) wireViewBar(view);
  if (needsActivity) await renderPicker($("#picker"));
  if (token !== state.pass.token) return;

  const ctx = makeContext(token);
  const grid = $("#grid");
  view.spec.tuiles.forEach((tile, index) => grid.appendChild(renderTile(view, tile, index, ctx)));
  if (state.editing) {
    const add = document.createElement("button");
    add.className = "add-tile";
    add.type = "button";
    add.innerHTML = `${icon("plus")}Ajouter une tuile`;
    add.addEventListener("click", () => addTile(view));
    grid.appendChild(add);
  }
  if (!view.spec.tuiles.length && !state.editing) {
    grid.innerHTML = `<div class="tile" style="grid-column:span 12;grid-row:span 1;--h:1"><div class="tile-msg">Cette vue est vide. Clique sur « Modifier la vue » pour ajouter des tuiles.</div></div>`;
  }
}

function makeContext(token) {
  const bus = new EventTarget();
  const id = state.activityId;
  let detail = null;
  let streams = null;
  const getDetail = () => {
    if (!id) return Promise.resolve(null);
    detail ||= api.get(`/api/activities/${encodeURIComponent(id)}`).catch(() => null);
    return detail;
  };
  return {
    boot: state.boot,
    settings: state.boot.reglages,
    palette: C.palette(),
    bus,
    activityId: id,
    meta: (key) => state.catalog[key],
    sportLabel: (s) => E.sportLabel(s, state.boot.sports),
    period: (p) => {
      const days = !p?.periode || p.periode === "herite" ? state.days : Number(p.periode);
      const end = new Date();
      return { start: F.isoDate(F.addDays(end, -(days - 1))), end: F.isoDate(end), days };
    },
    activityDetail: getDetail,
    activityStreams: () => {
      if (!id) return Promise.resolve(null);
      streams ||= getDetail().then((d) => (d && d.has_streams === 1
        ? api.get(`/api/activities/${encodeURIComponent(id)}/streams`, { max_points: 2500 }).catch(() => null) : null));
      return streams;
    },
    openActivity: (activityId) => {
      const target = state.views.find((v) => v.spec.tuiles.some((t) => t.type.startsWith("seance_")));
      state.activityId = activityId;
      if (!target) { toast("Ajoute une tuile « Séance » à une vue pour ouvrir le détail des séances."); return; }
      location.hash = `#/vue/${encodeURIComponent(target.id)}?seance=${encodeURIComponent(activityId)}`;
    },
    token,
  };
}

function renderTile(view, tile, index, ctx) {
  const renderer = RENDERERS[tile.type];
  const type = state.types[tile.type];
  const el = document.createElement("section");
  el.className = `tile tile--${tile.type}`;
  el.style.gridColumn = `span ${tile.w}`;
  el.style.gridRow = `span ${tile.h}`;
  el.style.setProperty("--h", tile.h);  // hauteur utilisée sur téléphone
  if (!renderer || !type) {
    el.innerHTML = `<div class="tile-msg">Type de tuile inconnu : ${F.escape(tile.type)}</div>`;
    return el;
  }
  const title = tile.titre || renderer.title(tile.params, ctx);
  el.setAttribute("aria-label", title);
  el.innerHTML = `${renderer.ownHead ? "" : `<div class="tile-head"><h2 class="tile-title" title="${F.escape(title)}">${F.escape(title)}</h2><span class="tile-sub"></span></div>`}
    <div class="tile-body"></div>${state.editing ? tileTools() : ""}`;
  const body = el.querySelector(".tile-body");
  const tileCtx = { ...ctx, sub: (text) => { const s = el.querySelector(".tile-sub"); if (s) { s.textContent = text; s.title = text; } } };
  D.message(body, "Chargement…");
  const keep = (disposable) => {
    if (ctx.token !== state.pass.token) disposable.dispose();
    else state.pass.disposers.push(disposable);
  };
  Promise.resolve()
    .then(() => renderer.render(body, tile.params, tileCtx, tile, keep))
    .catch((err) => D.message(body, `Impossible d'afficher cette tuile : ${err.message}`));
  if (state.editing) wireTileTools(view, el, index);
  return el;
}

// =================================================================== édition
function viewBar() {
  return `<div class="view-bar">
    <button class="btn" type="button" data-add>${icon("plus")}Ajouter une tuile</button>
    <button class="btn btn-ghost" type="button" data-rename>${icon("edit")}Renommer</button>
    <button class="btn btn-ghost" type="button" data-duplicate>${icon("copy")}Dupliquer</button>
    <button class="btn btn-ghost" type="button" data-export>${icon("download")}Exporter</button>
    <button class="btn btn-ghost" type="button" data-import>${icon("upload")}Importer une vue</button>
    <span class="spacer"></span>
    <button class="btn btn-ghost btn-danger" type="button" data-delete>${icon("trash")}Supprimer la vue</button>
    <input type="file" accept="application/json,.json" hidden data-file>
  </div>`;
}

function wireViewBar(view) {
  const bar = $(".view-bar");
  bar.querySelector("[data-add]").addEventListener("click", () => addTile(view));
  bar.querySelector("[data-rename]").addEventListener("click", async () => {
    const res = await E.editView(view, state.boot);
    if (!res) return;
    await saveView({ ...view, ...res });
    renderNav();
  });
  bar.querySelector("[data-duplicate]").addEventListener("click", async () => {
    const created = await api.post("/api/views", { name: `${view.name} (copie)`, icon: view.icon, spec: view.spec });
    state.views.push(created);
    location.hash = `#/vue/${encodeURIComponent(created.id)}`;
    toast("Vue dupliquée.");
  });
  bar.querySelector("[data-export]").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify({ foulee_vue: 1, name: view.name, icon: view.icon, spec: view.spec }, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `foulee-vue-${view.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 2000);
  });
  const file = bar.querySelector("[data-file]");
  bar.querySelector("[data-import]").addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    try {
      const data = JSON.parse(await file.files[0].text());
      if (!data?.spec?.tuiles) throw new Error("ce fichier ne contient pas de vue Foulée");
      const created = await api.post("/api/views", { name: data.name || "Vue importée", icon: data.icon, spec: data.spec });
      state.views.push(created);
      location.hash = `#/vue/${encodeURIComponent(created.id)}`;
      toast("Vue importée.");
    } catch (err) {
      toast(`Import impossible : ${err.message}`, { error: true });
    }
  });
  bar.querySelector("[data-delete]").addEventListener("click", async () => {
    const ok = await E.confirm("Supprimer cette vue ?", `« ${view.name} » disparaîtra de la navigation. Tes données ne sont pas touchées.`, "Supprimer la vue");
    if (!ok) return;
    await api.del(`/api/views/${encodeURIComponent(view.id)}`);
    state.views = state.views.filter((v) => v.id !== view.id);
    state.editing = false;
    location.hash = state.views[0] ? `#/vue/${encodeURIComponent(state.views[0].id)}` : "#/";
    renderNav();
    toast("Vue supprimée.");
  });
}

function tileTools() {
  return `<div class="tile-tools" role="toolbar" aria-label="Outils de la tuile">
    <button type="button" data-tool="left" title="Déplacer avant" aria-label="Déplacer avant">${icon("left")}</button>
    <button type="button" data-tool="right" title="Déplacer après" aria-label="Déplacer après">${icon("right")}</button>
    <button type="button" data-tool="width" title="Changer la largeur" aria-label="Changer la largeur">${icon("width")}</button>
    <button type="button" data-tool="height" title="Changer la hauteur" aria-label="Changer la hauteur">${icon("height")}</button>
    <button type="button" data-tool="edit" title="Régler" aria-label="Régler la tuile">${icon("settings")}</button>
    <button type="button" data-tool="delete" title="Retirer" aria-label="Retirer la tuile">${icon("trash")}</button>
  </div>`;
}

function wireTileTools(view, el, index) {
  const tiles = view.spec.tuiles;
  const tile = tiles[index];
  el.querySelector(".tile-tools").addEventListener("click", async (e) => {
    const tool = e.target.closest("[data-tool]")?.dataset.tool;
    if (!tool) return;
    if (tool === "left" && index > 0) [tiles[index - 1], tiles[index]] = [tiles[index], tiles[index - 1]];
    else if (tool === "right" && index < tiles.length - 1) [tiles[index + 1], tiles[index]] = [tiles[index], tiles[index + 1]];
    else if (tool === "width") tile.w = WIDTHS[(WIDTHS.indexOf(tile.w) + 1) % WIDTHS.length];
    else if (tool === "height") tile.h = (tile.h % 3) + 1;
    else if (tool === "edit") {
      const res = await E.editTile(tile, state.types[tile.type], state.boot);
      if (!res) return;
      Object.assign(tile, res);
      if (!res.titre) delete tile.titre;
    } else if (tool === "delete") {
      tiles.splice(index, 1);
    } else return;
    await saveView(view);
  });
  el.setAttribute("draggable", "true");
  el.addEventListener("dragstart", (e) => {
    if (e.target.closest(".tile-tools")) return;
    state.dragIndex = index;
    e.dataTransfer.effectAllowed = "move";
    el.classList.add("is-dragging");
  });
  el.addEventListener("dragend", () => {
    el.classList.remove("is-dragging");
    document.querySelectorAll(".drop-before,.drop-after").forEach((x) => x.classList.remove("drop-before", "drop-after"));
  });
  el.addEventListener("dragover", (e) => {
    e.preventDefault();
    const rect = el.getBoundingClientRect();
    const after = e.clientX > rect.left + rect.width / 2;
    el.classList.toggle("drop-after", after);
    el.classList.toggle("drop-before", !after);
  });
  el.addEventListener("dragleave", () => el.classList.remove("drop-before", "drop-after"));
  el.addEventListener("drop", async (e) => {
    e.preventDefault();
    const from = state.dragIndex;
    if (from == null) return;
    const rect = el.getBoundingClientRect();
    let to = index + (e.clientX > rect.left + rect.width / 2 ? 1 : 0);
    const [moved] = tiles.splice(from, 1);
    if (from < to) to -= 1;
    tiles.splice(to, 0, moved);
    state.dragIndex = null;
    await saveView(view);
  });
}

async function addTile(view) {
  const type = await E.pickTileType(state.boot);
  if (!type) return;
  const def = state.types[type];
  const draft = {
    type, w: def.taille.w, h: def.taille.h,
    params: Object.fromEntries(def.params.map((p) => [p.key, structuredClone(p.default)])),
  };
  if (def.params.length) {
    const res = await E.editTile(draft, def, state.boot);
    if (!res) return;
    Object.assign(draft, res);
    if (!res.titre) delete draft.titre;
  }
  view.spec.tuiles.push(draft);
  await saveView(view);
  toast(`Tuile « ${def.label} » ajoutée.`);
}

async function saveView(view) {
  try {
    const saved = await api.put(`/api/views/${encodeURIComponent(view.id)}`, { name: view.name, icon: view.icon, spec: view.spec });
    const i = state.views.findIndex((v) => v.id === view.id);
    state.views[i] = { ...state.views[i], ...saved };
  } catch (err) {
    toast(`Enregistrement impossible : ${err.message}`, { error: true });
  }
  renderView();
}

async function newView() {
  closeMenu();
  const res = await E.editView(null, state.boot);
  if (!res) return;
  const created = await api.post("/api/views", { name: res.name, icon: res.icon, spec: { tuiles: [] } });
  state.views.push(created);
  state.editing = true;
  location.hash = `#/vue/${encodeURIComponent(created.id)}`;
}

// ============================================================ choix de séance
async function renderPicker(box) {
  let list = [];
  try { list = await api.get("/api/activities", { limit: 80 }); } catch (e) { list = []; }
  if (!list.length) {
    box.innerHTML = `<span class="tile-sub">Aucune séance pour l'instant.</span>`;
    state.activityId = null;
    return;
  }
  if (!state.activityId) state.activityId = list[0].id;
  if (!list.some((a) => a.id === state.activityId)) {
    try {
      const one = await api.get(`/api/activities/${encodeURIComponent(state.activityId)}`, { fetch: 0 });
      list.unshift(one);
    } catch (e) { state.activityId = list[0].id; }
  }
  const index = list.findIndex((a) => a.id === state.activityId);
  const option = (a) => `${F.dateShort(a.date)} : ${a.name || a.sport_label}${a.distance_m ? `, ${F.dec1(a.distance_m / 1000)} km` : ""}`;
  box.innerHTML = `
    <button class="btn btn-ghost icon-btn" type="button" data-step="1" aria-label="Séance précédente" ${index >= list.length - 1 ? "disabled" : ""}>${icon("left")}</button>
    <select aria-label="Séance affichée">${list.map((a) => `<option value="${F.escape(a.id)}" ${a.id === state.activityId ? "selected" : ""}>${F.escape(option(a))}</option>`).join("")}</select>
    <button class="btn btn-ghost icon-btn" type="button" data-step="-1" aria-label="Séance suivante" ${index <= 0 ? "disabled" : ""}>${icon("right")}</button>`;
  const go = (id) => { location.hash = `#/vue/${encodeURIComponent(state.viewId)}?seance=${encodeURIComponent(id)}`; };
  box.querySelector("select").addEventListener("change", (e) => go(e.target.value));
  box.querySelectorAll("[data-step]").forEach((b) => b.addEventListener("click", () => {
    const next = list[index + Number(b.dataset.step)];
    if (next) go(next.id);
  }));
}

// =================================================================== réglages
function showSettings() {
  disposePass();
  state.editing = false;
  renderNav();
  renderSettings($("#page"), state.boot, {
    toast,
    onSaved: (settings) => { state.boot.reglages = settings; api.clearCache(); },
    resetViews: async () => {
      const ok = await E.confirm("Restaurer les vues d'origine ?", "Les cinq vues fournies avec Foulée reprennent leur contenu de départ. Tes vues personnelles ne bougent pas.", "Restaurer");
      if (!ok) return;
      state.views = await api.post("/api/views/reset");
      renderNav();
      toast("Vues d'origine restaurées.");
    },
  });
}

// ===================================================================== synchro
function renderSyncLine(job) {
  const line = $("#sync-line");
  const bar = $("#sync-progress");
  const s = state.boot.synchro || {};
  if (job?.en_cours) {
    line.innerHTML = `<strong>Synchro en cours</strong><br>${F.escape(job.message || "")}`;
    bar.hidden = false;
    bar.firstElementChild.style.width = `${Math.round((job.progression || 0) * 100)}%`;
    $("#sync-btn").disabled = true;
    return;
  }
  bar.hidden = true;
  $("#sync-btn").disabled = false;
  if (state.boot.demo) { line.innerHTML = "Données fictives : la synchro est désactivée en mode démo."; return; }
  if (!state.boot.cle) { line.innerHTML = "Aucune clé API : lance « foulee setup » dans un terminal."; return; }
  const last = s.derniere_reussie;
  line.innerHTML = last ? `Dernière synchro <strong>${F.escape(F.relative(last))}</strong>` : "Jamais synchronisé";
  if (s.derniere?.statut === "echec") line.innerHTML += "<br>La dernière tentative a échoué.";
}

async function startSync() {
  try {
    const res = await api.post("/api/sync");
    if (!res.lance) { toast(res.message); return; }
    pollSync();
  } catch (err) {
    toast(`Synchro impossible : ${err.message}`, { error: true });
  }
}

function pollSync() {
  clearTimeout(state.syncTimer);
  const tick = async () => {
    let status;
    try { status = await api.get("/api/sync", null, { fresh: true }); } catch (e) { state.syncTimer = setTimeout(tick, 3000); return; }
    const job = status.job;
    if (job.en_cours || status.en_cours) {
      renderSyncLine({ en_cours: true, message: job.message, progression: job.progression });
      state.syncTimer = setTimeout(tick, 1500);
      return;
    }
    if (job.erreur) toast(`Synchro impossible : ${job.erreur}`, { error: true });
    else if (job.resultat) {
      const g = job.resultat.sources?.garmin || {};
      if (g.erreur) toast(`Synchro impossible : ${g.erreur}`, { error: true });
      else toast(`Synchro terminée : ${g.seances_nouvelles || 0} nouvelle(s) séance(s), ${g.fit || 0} fichier(s) FIT.${g.erreurs?.length ? ` ${g.erreurs.length} alerte(s) dans le journal.` : ""}`);
    }
    api.clearCache();
    await loadBoot();
    renderSyncLine();
    renderNav();
    rerender();
  };
  tick();
}

start();
