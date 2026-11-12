// Foulée : chef d'orchestre de l'interface (navigation, vues, tuiles, édition, synchro, thème).
import * as api from "./api.js";
import * as C from "./charts.js";
import * as E from "./editor.js";
import * as F from "./format.js";
import { renderHelp } from "./faq.js";
import { renderFeedback } from "./feedback.js";
import { icon } from "./icons.js";
import { brandMark, setFavicon } from "./logos.js";
import { startUpdateAlert } from "./maj.js";
import { renderSettings } from "./settings.js";
import { renderChooser, whoButton, wireWho } from "./users.js";
import { renderWelcome } from "./welcome.js";
import { mergeSources, rowSources, sourceText } from "./sources.js";
import { connPills, wireConn } from "./connections.js";
import * as A from "./tiles-activity.js";
import * as R from "./tiles-renfo.js";
import * as D from "./tiles-data.js";
import * as H from "./tiles-home.js";
import * as W from "./tiles-withings.js";

const RENDERERS = {
  kpi: D.kpi, serie: D.serie, charge: D.charge, zones: D.zones, calendrier: D.calendrier, nuage: D.nuage,
  postes: D.postes, objectif: D.objectif, fractions: D.fractions, note: D.note,
  activites: A.activites, derniere_seance: A.derniere_seance, seance_resume: A.seance_resume,
  seance_carte: A.seance_carte, seance_courbes: A.seance_courbes, seance_tours: A.seance_tours,
  seance_mesures: A.seance_mesures,
  renfo: R.renfo, renfo_exercices: R.renfo_exercices, seance_renfo: R.seance_renfo,
  profil: H.profil, forme: H.forme, allures: H.allures, semaine: H.semaine, records: H.records, journee: H.journee,
  club: H.club, withings: W.withings,
};
const PERIODS = [[7, "7 j"], [30, "30 j"], [90, "90 j"], [180, "6 mois"], [365, "1 an"], [730, "2 ans"]];
// Tuiles qui ne dépendent pas de la période : une vue faite seulement de celles-ci se passe du sélecteur
const TIMELESS = new Set(["profil", "club", "withings"]);
const WIDTHS = [3, 4, 6, 8, 12];
const THEMES = ["auto", "light", "dark"];
const THEME_LABELS = { auto: "Thème : automatique", light: "Thème : clair", dark: "Thème : sombre" };

const state = {
  boot: null, catalog: {}, types: {}, views: [], viewId: null, days: 90, editing: false,
  activityId: null, pass: { token: 0, disposers: [] }, syncTimer: null, dragIndex: null,
  syncPolling: false, connTimer: null,  // synchro suivie depuis cette page ; relecture des pastilles
  fromHash: "",  // dernière page visitée avant le formulaire de retours (jointe au signalement)
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
  if (state.boot.profil_requis) {
    // Plusieurs profils et aucun choisi sur cet appareil : « Qui utilise Foulée ? », rien d'autre
    document.body.classList.add("choosing");
    paintTheme();
    renderChooser($("#page"), state.boot, { toast });
    return;
  }
  state.days = Number(store("foulee-period")) || 90;
  setupChrome();
  // « Une nouvelle version est disponible ! » en haut à droite (GitHub revérifié toutes les 3 heures)
  startUpdateAlert($("#update-alert"), () => state.boot);
  // Premier lancement (ni clé, ni données) : la page d'accueil guide pas à pas
  if (needsWelcome() && (!location.hash || location.hash === "#/")) history.replaceState(null, "", "#/bienvenue");
  window.addEventListener("hashchange", route);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (themeChoice() === "auto") rerender(); });
  route();
  if (state.boot.synchro?.en_cours) pollSync();
  // Pastilles de connexion : revérifiées toutes les 2 minutes et au retour sur l'onglet (synchros automatiques)
  setInterval(refreshConn, 120000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refreshConn(); });
}

function noData() { return !state.boot.volumes.daily && !state.boot.volumes.activities && !state.boot.strava?.seances; }

function needsWelcome() {
  const b = state.boot;
  // Ni données ni démo : clé à enregistrer, premier import à lancer, ou ancienne installation à reprendre
  return b.acces === "local" && !b.demo && noData() && store(welcomeKey()) !== "vu";
}

// Chaque profil voit la page d'accueil une fois (le principal garde la clé d'avant les profils)
function welcomeKey() {
  const id = state.boot.utilisateur?.id;
  return !id || id === "p0" ? "foulee-bienvenue" : `foulee-bienvenue-${id}`;
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
  if (state.boot.profil_requis) return;
  api.setProfile(state.boot.utilisateur?.id);
  state.catalog = Object.fromEntries(state.boot.metriques.map((m) => [m.key, m]));
  state.types = Object.fromEntries(state.boot.tuiles.map((t) => [t.type, t]));
  state.views = state.boot.vues;
}

function setupChrome() {
  $("#sync-btn").innerHTML = `${icon("sync")}Synchroniser`;
  $("#sync-btn").addEventListener("click", startSync);
  $("#settings-btn").innerHTML = `${icon("settings")}Réglages`;
  $("#settings-btn").addEventListener("click", () => { location.hash = "#/reglages"; closeMenu(); });
  $("#help-link").innerHTML = `${icon("help")}<span>Aide et FAQ</span>`;
  $("#feedback-link").innerHTML = `${icon("feedback")}<span><b>Un bug, une idée ?</b><small>Parles-en !</small></span>`;
  document.querySelectorAll("#help-link, #feedback-link").forEach((link) => link.addEventListener("click", closeMenu));
  $("#menu-btn").innerHTML = icon("menu");
  $("#menu-btn").addEventListener("click", () => $("#rail").classList.toggle("open"));
  $("#theme-btn").addEventListener("click", cycleTheme);
  paintTheme();
  renderBrand();
  renderStrip();
  // Sur téléphone, les pastilles de connexion vont dans la barre du haut (toujours visible)
  paintConn();
  wireConn($(".topbar"), connState, { onSync: startSync });
  renderNav();
  renderSyncLine();
}

// Bandeau d'information en haut de page : démo, clé refusée ou absente, pas encore de données
function renderStrip() {
  const b = state.boot;
  const local = b.acces === "local";
  const strip = (kind, text, action = "") => `<div class="demo-strip${kind ? ` ${kind}` : ""}">${icon(kind ? "warning" : "info")}<span>${text}</span>${action}</div>`;
  let html = "";
  if (b.demo) {
    html = strip("", "Mode démo : toutes les données sont fictives.",
      local ? `<button class="btn btn-ghost" type="button" data-demo-off>Quitter la démo</button>` : "");
  } else if (b.cle_refusee) {
    html = strip("alert", `Garmin refuse ta clé API depuis le ${F.escape(F.dateTime(b.cle_refusee.depuis))} : la synchro est en pause.`,
      local ? `<a class="btn btn-ghost" href="#/reglages?section=cle">Remplacer la clé</a>` : "");
  } else if (!b.cle) {
    html = noData()
      ? strip("", "Pas encore de clé API Garmin : l'accueil te guide en trois étapes.", local ? `<a class="btn btn-ghost" href="#/bienvenue">Commencer</a>` : "")
      : strip("alert", "Aucune clé API Garmin enregistrée : la synchro est en pause.", local ? `<a class="btn btn-ghost" href="#/reglages?section=cle">Ajouter ma clé</a>` : "");
  } else if (b.withings?.refus) {
    html = strip("alert", "Withings n'accepte plus l'accès de Foulée : la synchro de tes mesures Withings est en pause.",
      local ? `<a class="btn btn-ghost" href="#/reglages?section=withings">Reconnecter Withings</a>` : "");
  } else if (noData()) {
    html = strip("", "Pas encore de données : lance le premier import.", `<a class="btn btn-ghost" href="#/bienvenue">Premier import</a>`);
  }
  $("#demo-strip").innerHTML = html;
  $("#demo-strip [data-demo-off]")?.addEventListener("click", async () => {
    try {
      await api.post("/api/demo", { actif: false });
      location.hash = "#/";
      location.reload();
    } catch (err) {
      toast(err.message, { error: true });
    }
  });
}

function closeMenu() { $("#rail").classList.remove("open"); }

// Logo choisi (ou photo de profil) dans la colonne, la barre du téléphone et l'onglet du navigateur
function renderBrand() {
  const profil = state.boot.profil || {};
  document.querySelectorAll(".brand-mark").forEach((box) => { box.innerHTML = brandMark(profil, box.dataset.size ? Number(box.dataset.size) : 28); });
  setFavicon(profil);
}

/** Recharge l'état du serveur (après un réglage qui touche l'en-tête, les horaires…). */
async function refreshBoot() {
  api.clearCache();
  await loadBoot();
  renderBrand();
  renderStrip();
  renderNav();
}

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
      ${v.id === state.viewId && !isOtherPage() ? 'aria-current="page"' : ""} ${state.editing ? 'draggable="true"' : ""}>
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
/** Une page qui n'est pas une vue : réglages, bienvenue, aide, retours. */
function isOtherPage() { return /^#\/(reglages|bienvenue|aide|retours)/.test(location.hash); }

function markRailLinks(path) {
  [["#help-link", "/aide"], ["#feedback-link", "/retours"]].forEach(([selector, page]) => {
    if (path === page) $(selector).setAttribute("aria-current", "page");
    else $(selector).removeAttribute("aria-current");
  });
}

function route() {
  const [path, query] = location.hash.slice(1).split("?");
  const params = new URLSearchParams(query || "");
  $("#demo-strip").hidden = path === "/bienvenue";  // l'accueil dit déjà tout
  markRailLinks(path);
  if (path !== "/retours") state.fromHash = location.hash;
  if (path === "/reglages") { showSettings(params.get("section")); return; }
  if (path === "/bienvenue") { showWelcome(); return; }
  if (path === "/aide") { showHelp(params); return; }
  if (path === "/retours") { showFeedback(params); return; }
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
  // Formulaires en cours (bienvenue, retours) ou texte sans graphique (aide) : on ne redessine pas
  if (/^#\/(bienvenue|aide|retours)/.test(location.hash)) return;
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
  const plan = F.dayPlan(today, state.boot.reglages);
  if (!plan.actif) return `<span class="shift-chip">Semaine ${week}</span>`;
  const color = F.shiftColor(plan.poste, state.boot.reglages, C.palette());
  const text = plan.poste ? `${plan.nom}, ${plan.debut}–${plan.fin}` : plan.conges ? plan.conges : plan.nom;
  return `<span class="shift-chip" title="Semaine ISO ${week} (${week % 2 ? "impaire" : "paire"}) : ${F.escape(text)}"><i class="dot" style="background:${color}"></i>Semaine ${week}, ${F.escape(text.charAt(0).toLowerCase() + text.slice(1))}</span>`;
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
  const usesPeriod = state.editing || !view.spec.tuiles.length || view.spec.tuiles.some((t) => !TIMELESS.has(t.type));
  const todayIso = F.isoDate(new Date());
  page.innerHTML = `
    <header class="head">
      <div class="conn" role="group" aria-label="Connexions">${connPills(state.boot.connexions, connBusy())}</div>
      <div><h1>${F.escape(view.name)}</h1>
        <div class="head-sub"><span>${F.escape(F.dateLong(todayIso))}</span>${shiftChip()}</div></div>
      <div class="head-tools">
        ${usesPeriod ? `<div class="segmented" role="group" aria-label="Période affichée">${PERIODS.map(([d, l]) =>
          `<button type="button" data-days="${d}" aria-pressed="${d === state.days}">${l}</button>`).join("")}</div>` : ""}
        <button class="btn${state.editing ? " btn-primary" : ""}" type="button" data-edit>${icon(state.editing ? "check" : "edit")}${state.editing ? "Terminer" : "Modifier la vue"}</button>
      </div>
      ${view.id === "accueil" ? whoButton(state.boot) : ""}
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
  const who = wireWho(page, state.boot, { toast });
  if (who) state.pass.disposers.push(who);
  const conn = wireConn(page.querySelector(".head"), connState, { onSync: startSync });
  if (conn) state.pass.disposers.push(conn);
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
    toast,
    activityId: id,
    /** Enregistre des réglages depuis une tuile, puis redessine la vue. */
    saveSettings: async (patch, done) => {
      try {
        const res = await api.put("/api/settings", patch);
        state.boot.reglages = res.reglages;
        state.boot.objectif = res.objectif;
        if (res.profil_fc) state.boot.profil_fc = res.profil_fc;
        if (res.planning) state.boot.planning = res.planning;
        api.clearCache();
        if (done) toast(done);
        renderView();
      } catch (err) {
        toast(err.message, { error: true });
      }
    },
    meta: (key) => state.catalog[key] || state.boot.metriques.find((m) => m.key === key) || { key, label: key, fmt: "num", unit: "" },
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
  el.innerHTML = `${renderer.ownHead ? "" : `<div class="tile-head"><h2 class="tile-title" title="${F.escape(title)}">${F.escape(title)}</h2><span class="tile-src" hidden></span><span class="tile-sub"></span></div>`}
    <div class="tile-body"></div>${state.editing ? tileTools() : ""}`;
  const body = el.querySelector(".tile-body");
  // Sources des chiffres (Garmin, Strava, Withings), d'après les réponses de chaque requête de la tuile
  let sources = [];
  const paintSources = () => {
    const text = sourceText(sources);
    if (!text || renderer.ownSource) return;
    let src = el.querySelector(".tile-src");
    if (!src) {  // tuile qui dessine son propre en-tête (chiffre clé…) : la source en haut à droite
      src = document.createElement("span");
      src.className = "tile-src tile-src-corner";
      el.appendChild(src);
    }
    src.textContent = text;
    src.title = `Données : ${text}`;
    src.hidden = false;
  };
  const noteSources = (list) => { sources = mergeSources(sources, list); paintSources(); };
  const tileCtx = {
    ...ctx,
    /** api.get, en notant d'où viennent les données reçues (mention à côté du titre). */
    get: (path, params, options) => api.get(path, params, options).then((res) => {
      if (Array.isArray(res)) noteSources(rowSources(res));
      else if (res?.sources) noteSources(res.sources);
      return res;
    }),
    noteSources,
    sub: (text) => { const s = el.querySelector(".tile-sub"); if (s) { s.textContent = text; s.title = text; } },
    /** La tuile n'a rien à montrer ici (séance sans renfo…) : elle s'efface, sauf pendant la modification de la vue. */
    hide: () => { if (!state.editing) el.hidden = true; },
  };
  D.message(body, "Chargement…");
  const keep = (disposable) => {
    if (ctx.token !== state.pass.token) disposable.dispose();
    else state.pass.disposers.push(disposable);
  };
  Promise.resolve()
    .then(() => renderer.render(body, tile.params, tileCtx, tile, keep))
    .then(paintSources)  // l'en-tête propre à la tuile vient d'être dessiné : la source y trouve sa place
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

// ============================================================== aide et retours
function showHelp(params) {
  disposePass();
  state.editing = false;
  closeMenu();
  renderNav();
  window.scrollTo(0, 0);
  renderHelp($("#page"), state.boot, { query: params.get("q") || "", theme: params.get("theme") || "", question: params.get("question") || "" });
}

function showFeedback(params) {
  disposePass();
  state.editing = false;
  closeMenu();
  renderNav();
  window.scrollTo(0, 0);
  renderFeedback($("#page"), state.boot, {
    toast,
    from: state.fromHash,
    kind: params.get("type") || "",
    keep: (disposable) => state.pass.disposers.push(disposable),
  });
}

// =================================================================== réglages
function showWelcome() {
  disposePass();
  state.editing = false;
  closeMenu();
  renderNav();
  renderWelcome($("#page"), state.boot, {
    toast,
    onImport: () => pollSync(),
    onDone: () => { store(welcomeKey(), "vu"); location.hash = "#/"; },
  });
}

function showSettings(section = null) {
  disposePass();
  state.editing = false;
  renderNav();
  renderSettings($("#page"), state.boot, {
    toast,
    section,
    onSaved: (res) => {
      state.boot.reglages = res.reglages;
      if (res.objectif) state.boot.objectif = res.objectif;
      if (res.profil_fc) state.boot.profil_fc = res.profil_fc;
      if (res.planning) state.boot.planning = res.planning;
      api.clearCache();
    },
    onProfile: (profil) => { state.boot.profil = profil; renderBrand(); },
    refreshBoot: async (again) => { await refreshBoot(); if (again) showSettings(again); },
    startSync,
    resetViews: async () => {
      const ok = await E.confirm("Restaurer les vues d'origine ?", "Les six vues fournies avec Foulée (dont l'accueil) reprennent leur contenu de départ. Tes vues personnelles ne bougent pas.", "Restaurer");
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
  if (!state.boot.cle) {
    line.innerHTML = state.boot.acces === "local" ? `Aucune clé API : <a href="#/reglages?section=cle">ajoute-la</a>.` : "Aucune clé API enregistrée.";
    return;
  }
  if (state.boot.cle_refusee) {
    line.innerHTML = `<strong>Synchro en pause</strong><br>Garmin refuse la clé API.`;
    return;
  }
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
  state.syncPolling = true;
  paintConn();
  const tick = async () => {
    let status;
    try { status = await api.get("/api/sync", null, { fresh: true }); } catch (e) { state.syncTimer = setTimeout(tick, 3000); return; }
    const job = status.job;
    if (job.en_cours || status.en_cours) {
      renderSyncLine({ en_cours: true, message: job.message, progression: job.progression });
      state.syncTimer = setTimeout(tick, 1500);
      return;
    }
    state.syncPolling = false;
    if (job.erreur) toast(`Synchro impossible : ${job.erreur}`, { error: true });
    else if (job.resultat) syncToast(job.resultat.sources || {});
    api.clearCache();
    await loadBoot();
    renderStrip();
    renderSyncLine();
    renderNav();
    paintConn();
    // Sur les Réglages, la page reste en place (saisie en cours, position) : le panneau Withings suit seul
    if (!isSettings()) rerender();
  };
  tick();
}

// ------------------------------------------------------------ pastilles de connexion
function connBusy() { return Boolean(state.syncPolling || state.boot.synchro?.en_cours); }

function connState() {
  return { list: state.boot.connexions || [], busy: connBusy(), demo: state.boot.demo, local: state.boot.acces === "local" };
}

/** Redessine les pastilles (en-tête de la vue, barre du téléphone), sauf celles dont le détail est ouvert. */
function paintConn() {
  document.querySelectorAll("#page .head > .conn, .topbar > .conn").forEach((box) => {
    if (!box.querySelector(".conn-pill[aria-expanded='true']")) box.innerHTML = connPills(state.boot.connexions, connBusy());
  });
}

/** État des sources relu sans recharger la page : une synchro automatique a pu passer entre-temps. */
async function refreshConn() {
  if (document.visibilityState !== "visible" || state.syncPolling || !state.boot || state.boot.profil_requis) return;
  clearTimeout(state.connTimer);
  let status;
  try { status = await api.get("/api/sync", null, { fresh: true }); } catch (e) { return; }  // serveur injoignable : plus tard
  if (state.syncPolling) return;
  const { connexions, en_cours: busy, derniere_reussie: lastOk, derniere: last } = status;
  if (connexions) state.boot.connexions = connexions;
  state.boot.synchro = { ...state.boot.synchro, en_cours: busy, derniere_reussie: lastOk, derniere: last };
  paintConn();
  renderSyncLine(busy ? { en_cours: true, message: "Synchro automatique" } : undefined);
  if (busy) state.connTimer = setTimeout(refreshConn, 15000);
}

/** Bilan d'une synchro, source par source (Garmin, Withings), dans un seul message. */
function syncToast(sources) {
  const { garmin: g, withings: w } = sources;
  const both = Boolean(g && w);
  const done = [];
  const failed = [];
  if (g?.erreur) failed.push(both ? `Garmin : ${g.erreur}` : g.erreur);
  else if (g) done.push(`${g.seances_nouvelles || 0} nouvelle(s) séance(s), ${g.fit || 0} fichier(s) FIT${g.erreurs?.length ? `, ${g.erreurs.length} alerte(s) dans le journal` : ""}`);
  if (w?.erreur) failed.push(both ? `Withings : ${w.erreur}` : w.erreur);
  else if (w) done.push(`mesures Withings à jour${w.erreurs?.length ? ` (${w.erreurs.length} alerte(s) dans le journal)` : ""}`);
  if (!failed.length) toast(`Synchro terminée : ${done.join(" ; ") || "rien de nouveau"}.`);
  else if (!done.length) toast(`Synchro impossible : ${failed.join(" ; ")}`, { error: true });
  else toast(`Synchro partielle : ${done.join(" ; ")}. ${failed.join(" ; ")}`, { error: true });
}

start();
