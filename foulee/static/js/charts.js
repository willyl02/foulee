// Habillage commun des graphiques ECharts : couleurs lues dans le CSS (clair / sombre),
// traits fins, grille discrète, info-bulles au survol.
import * as F from "./format.js";
import { icon } from "./icons.js";

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

export function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function palette() {
  return {
    ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"), hair: css("--hair"), base: css("--base"),
    surface: css("--surface"), band: css("--band"), good: css("--good"), bad: css("--bad"),
    series: ["--s1", "--s2", "--s3", "--s4"].map(css),
    zones: ["--z1", "--z2", "--z3", "--z4", "--z5"].map(css),
    seq: ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4"].map(css),
    divPos: css("--div-pos"), divNeg: css("--div-neg"),
    font: "Barlow, system-ui, sans-serif",
  };
}

export function mount(el, option, onReady) {
  const chart = echarts.init(el, null, { renderer: "canvas" });
  chart.setOption(option);
  let zoom = zoomable(el, chart, option);
  const observer = new ResizeObserver(() => {
    chart.resize();
    // un graphique monté avant d'avoir sa taille (onglet caché, tuile qui s'ouvre) gagne son zoom ensuite
    if (!zoom && el.clientHeight >= ZOOM_MIN_HEIGHT) zoom = zoomable(el, chart, option);
  });
  observer.observe(el);
  if (onReady) onReady(chart);
  return { chart, dispose() { observer.disconnect(); zoom?.dispose(); chart.dispose(); } };
}

// ------------------------------------------------------------------ zoom des graphiques
// Une boîte à outils en haut à droite de chaque graphique à axes (assez grand pour ça) : zoomer en largeur ou en
// hauteur, zoomer sur une zone tracée à la souris, revenir au zoom initial (aussi au double-clic). Ctrl + molette
// zoome en largeur, Maj + molette déplace. Même allure que celle de l'analyse fraction par fraction.
const ZOOM_MIN_HEIGHT = 150;
const ZOOM_MIN_POINTS = 15;

function axesOf(option, key) {
  const list = option[key];
  if (!list) return [];
  return (Array.isArray(list) ? list : [list]).map((_, i) => i);
}

export function zoomBarHTML({ area = true } = {}) {
  const tool = (key, name, title) => `<button class="zb-btn" type="button" data-zoom="${key}" title="${title}" aria-label="${title}">${icon(name)}</button>`;
  return `<div class="zoombar" role="toolbar" aria-label="Zoom du graphique">
    <span class="zb-group" title="En largeur">${icon("arrowsh")}${tool("x+", "plus", "Zoomer en largeur")}${tool("x-", "minus", "Dézoomer en largeur")}</span>
    <span class="zb-group" title="En hauteur">${icon("arrowsv")}${tool("y+", "plus", "Zoomer en hauteur")}${tool("y-", "minus", "Dézoomer en hauteur")}</span>
    ${area ? tool("area", "search", "Zoomer sur une zone (trace-la sur le graphique)") : ""}
    ${tool("reset", "reset", "Zoom initial (double-clic)")}
  </div>`;
}

/** Barre de défilement horizontale d'un graphique zoomé (analyse fraction par fraction, tuiles). */
export function scrollbarHTML() {
  return `<div class="zscroll is-off"><div class="zs-thumb" role="scrollbar" tabindex="0" aria-orientation="horizontal"
    aria-valuemin="0" aria-valuemax="100" aria-label="Se déplacer dans le graphique zoomé"></div></div>`;
}

/**
 * get() : la fenêtre vue, {start, end} entre 0 et 1 ; move(start) : la décaler (même largeur, bornée par l'appelant).
 * Glisser le curseur, cliquer dans la piste (la vue s'y centre), ou au clavier : flèches, Pg préc./suiv., Début, Fin.
 * Renvoie la fonction qui remet la barre à jour.
 */
export function wireScrollbar(track, { get, move }) {
  const thumb = track.querySelector(".zs-thumb");
  let drag = null;
  const update = () => {
    const { start, end } = get();
    const on = end - start < 0.999;
    track.classList.toggle("is-off", !on);
    if (!on) return;
    thumb.style.left = `${(start * 100).toFixed(3)}%`;
    thumb.style.width = `${Math.max(0, (end - start) * 100).toFixed(3)}%`;
    thumb.setAttribute("aria-valuenow", String(Math.round((start / Math.max(1e-9, 1 - (end - start))) * 100)));
  };
  thumb.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    ev.stopPropagation();
    drag = { x: ev.clientX, start: get().start };
    thumb.setPointerCapture(ev.pointerId);
    track.classList.add("is-dragging");
  });
  thumb.addEventListener("pointermove", (ev) => {
    if (drag) move(drag.start + (ev.clientX - drag.x) / track.getBoundingClientRect().width);
  });
  const stop = () => { drag = null; track.classList.remove("is-dragging"); };
  thumb.addEventListener("pointerup", stop);
  thumb.addEventListener("pointercancel", stop);
  track.addEventListener("pointerdown", (ev) => {
    if (ev.target === thumb || ev.button !== 0) return;
    ev.stopPropagation();
    const rect = track.getBoundingClientRect();
    const { start, end } = get();
    move((ev.clientX - rect.left) / rect.width - (end - start) / 2);
  });
  track.addEventListener("dblclick", (ev) => ev.stopPropagation());
  thumb.addEventListener("keydown", (ev) => {
    const { start, end } = get();
    const w = end - start;
    const steps = { ArrowLeft: -w / 10, ArrowRight: w / 10, PageUp: -w, PageDown: w };
    let to = null;
    if (ev.key in steps) to = start + steps[ev.key];
    else if (ev.key === "Home") to = 0;
    else if (ev.key === "End") to = 1 - w;
    if (to === null) return;
    ev.preventDefault();
    move(to);
  });
  update();
  return update;
}

/** Ajoute le zoom à un graphique ECharts à axes ; à rappeler après chaque setOption qui remplace tout. */
export function zoomable(el, chart, option) {
  const xs = axesOf(option, "xAxis");
  const ys = axesOf(option, "yAxis");
  if (!xs.length || !ys.length || option.zoom === false || el.clientHeight < ZOOM_MIN_HEIGHT) return null;
  // quelques barres (zones, mois) : rien à zoomer, pas de boîte à outils
  const points = Math.max(0, ...[].concat(option.series || []).map((s) => (Array.isArray(s?.data) ? s.data.length : 0)));
  if (points < ZOOM_MIN_POINTS) return null;
  const own = (Array.isArray(option.dataZoom) ? option.dataZoom : option.dataZoom ? [option.dataZoom] : []);
  const hasX = own.some((d) => d.type === "inside" && d.xAxisIndex !== undefined);
  chart.setOption({
    dataZoom: [...own,
      // en largeur, les points hors fenêtre sont écartés (rien ne déborde dans la marge des étiquettes, et la hauteur
      // s'ajuste à ce qu'on voit) ; en hauteur, rien n'est écarté : les courbes sont seulement coupées au bord
      ...(hasX ? [] : [{ id: "zx", type: "inside", xAxisIndex: xs, filterMode: "filter", zoomOnMouseWheel: "ctrl", moveOnMouseWheel: "shift", moveOnMouseMove: false, preventDefaultMouseMove: false }]),
      // un zoom vertical par axe : graphiques empilés, chaque grille garde son échelle
      ...ys.map((i) => ({ id: `zy${i}`, type: "inside", yAxisIndex: i, filterMode: "none", zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: false, preventDefaultMouseMove: false }))],
    // la sélection de zone passe par l'outil « dataZoom » d'ECharts, dont les icônes restent cachées (hors champ)
    toolbox: { show: true, left: -1000, top: -1000, itemSize: 1, feature: { dataZoom: { filterMode: "none", xAxisIndex: xs, yAxisIndex: ys } } },
  });
  let bar = el.querySelector(":scope > .zoombar");
  if (!bar) {
    el.classList.add("zoom-host");
    if (getComputedStyle(el).position === "static") el.style.position = "relative";
    el.insertAdjacentHTML("beforeend", zoomBarHTML() + scrollbarHTML());
    bar = el.querySelector(":scope > .zoombar");
  }
  const track = el.querySelector(":scope > .zscroll");
  const zooms = () => (chart.getOption().dataZoom || []).map((d, i) => ({ ...d, index: i }));
  // zoomé en hauteur, les bornes de l'axe tombent sur des valeurs quelconques (« 29 », « -65,48 ») : on cache ces
  // deux étiquettes-là, les graduations rondes entre les deux restent ; le zoom initial rend les réglages d'origine
  const labels = (chart.getOption().yAxis || []).map((a) => ({
    showMinLabel: a.axisLabel?.showMinLabel ?? null, showMaxLabel: a.axisLabel?.showMaxLabel ?? null }));
  let yShown = false;
  const yLabels = (zoomed) => {
    if (zoomed === yShown) return;
    yShown = zoomed;
    chart.setOption({ yAxis: labels.map((l) => ({ axisLabel: zoomed ? { showMinLabel: false, showMaxLabel: false } : l })) });
  };
  const has = (v) => (Array.isArray(v) ? v.length > 0 : v !== undefined && v !== null);
  const isX = (d) => has(d.xAxisIndex) && !String(d.id).startsWith("zy");
  const isY = (d) => has(d.yAxisIndex) && !has(d.xAxisIndex);
  const scale = (pick, factor) => zooms().filter(pick).forEach((d) => {
    const start = d.start ?? 0; const end = d.end ?? 100;
    const mid = (start + end) / 2; const half = Math.min(50, Math.max(1, ((end - start) / 2) / factor));
    let s = mid - half; let e = mid + half;
    if (s < 0) { e -= s; s = 0; }
    if (e > 100) { s -= e - 100; e = 100; }
    chart.dispatchAction({ type: "dataZoom", dataZoomIndex: d.index, start: Math.max(0, s), end: Math.min(100, e) });
  });
  let area = false;
  const setArea = (on) => {
    area = on;
    chart.dispatchAction({ type: "takeGlobalCursor", key: "dataZoomSelect", dataZoomSelectActive: on });
    bar.querySelector('[data-zoom="area"]')?.classList.toggle("is-on", on);
    el.classList.toggle("is-area", on);
  };
  const reset = () => {
    zooms().forEach((d) => chart.dispatchAction({ type: "dataZoom", dataZoomIndex: d.index, start: 0, end: 100 }));
    if (area) setArea(false);
  };
  const onClick = (ev) => {
    const btn = ev.target.closest("[data-zoom]");
    if (!btn) return;
    const k = btn.dataset.zoom;
    if (k === "x+") scale(isX, 2);
    else if (k === "x-") scale(isX, 0.5);
    else if (k === "y+") scale(isY, 1.5);
    else if (k === "y-") scale(isY, 1 / 1.5);
    else if (k === "area") setArea(!area);
    else reset();
  };
  // zoomé, un glisser déplace la vue ; au zoom initial, le glisser rend la main à la page (défilement au doigt)
  let panning = false;
  const pan = (on) => {
    if (on === panning) return;
    panning = on;
    const mine = zooms().filter((d) => d.id === "zx" || String(d.id).startsWith("zy"));
    chart.setOption({ dataZoom: mine.map((d) => ({ id: d.id, moveOnMouseMove: on })) });
  };
  // la barre de défilement, posée sur le bas de la grille du bas, suit la fenêtre en largeur
  const windowX = () => {
    const d = zooms().find(isX);
    return d ? { start: (d.start ?? 0) / 100, end: (d.end ?? 100) / 100 } : { start: 0, end: 1 };
  };
  let wanted = null;
  const scroll = wireScrollbar(track, {
    get: windowX,
    move: (start) => {
      const first = wanted === null;
      wanted = start;
      if (!first) return;
      requestAnimationFrame(() => {
        const { start: s0, end: e0 } = windowX();
        const w = e0 - s0;
        const s = Math.max(0, Math.min(1 - w, wanted));
        wanted = null;
        zooms().filter(isX).forEach((d) => chart.dispatchAction({ type: "dataZoom", dataZoomIndex: d.index, start: s * 100, end: (s + w) * 100 }));
      });
    },
  });
  const place = () => {
    let rect = null;
    try {
      chart.getModel().eachComponent("grid", (g) => {
        const r = g.coordinateSystem?.getRect?.();
        if (r && (!rect || r.y + r.height > rect.y + rect.height)) rect = r;
      });
    } catch (e) { rect = null; }
    if (!rect) return;
    track.style.left = `${rect.x}px`;
    track.style.width = `${rect.width}px`;
    track.style.top = `${rect.y + rect.height - 8}px`;
  };
  const onZoom = () => {
    const narrowed = (d) => (d.start ?? 0) > 0.01 || (d.end ?? 100) < 99.99;
    const list = zooms();
    const zoomed = list.some(narrowed);
    el.classList.toggle("is-zoomed", zoomed);
    yLabels(list.some((d) => isY(d) && narrowed(d)));
    pan(zoomed);
    scroll();
    if (area) setArea(false); // une zone à la fois : l'outil se range après usage
  };
  // la main : « attrapée » pendant qu'on fait glisser la vue
  const ungrab = () => el.classList.remove("is-grabbing");
  const grab = (ev) => {
    if (!el.classList.contains("is-zoomed") || area || ev.button !== 0 || ev.target.closest(".zoombar, .zscroll")) return;
    el.classList.add("is-grabbing");
    window.addEventListener("pointerup", ungrab, { once: true });
  };
  bar.onclick = onClick;
  if (el._zoomOff) el._zoomOff(); // rappelé après un setOption qui remplace tout : on ne double pas les écouteurs
  chart.on("datazoom", onZoom);
  chart.on("finished", place);
  chart.getZr().on("dblclick", reset);
  el.addEventListener("pointerdown", grab);
  el._zoomOff = () => {
    chart.off("datazoom", onZoom);
    chart.off("finished", place);
    chart.getZr()?.off("dblclick", reset);
    el.removeEventListener("pointerdown", grab);
  };
  place();
  return {
    dispose() {
      el._zoomOff?.(); el._zoomOff = null;
      bar?.remove(); track?.remove();
      el.classList.remove("zoom-host", "is-zoomed", "is-area", "is-grabbing");
    },
  };
}

export function baseOption(p) {
  return {
    animation: !reduced,
    animationDuration: 300,
    textStyle: { fontFamily: p.font, color: p.ink2, fontSize: 12 },
    tooltip: tooltipBase(p),
    grid: { left: 6, right: 14, top: 14, bottom: 4, containLabel: true },
  };
}

export function tooltipBase(p, trigger = "axis") {
  return {
    trigger,
    confine: true,
    backgroundColor: p.surface,
    borderColor: p.hair,
    borderWidth: 1,
    padding: [8, 10],
    textStyle: { color: p.ink, fontFamily: p.font, fontSize: 13 },
    extraCssText: "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.14);",
    axisPointer: { type: "line", lineStyle: { color: p.base, width: 1 }, label: { show: false } },
  };
}

export function tooltipHTML(title, rows) {
  const lines = rows
    .filter((r) => r && r.value !== undefined)
    .map((r) => `<div style="display:flex;align-items:center;gap:8px;justify-content:space-between;min-width:170px">
      <span style="display:inline-flex;align-items:center;gap:7px">${r.color ? `<span style="width:10px;height:10px;border-radius:${r.square ? 2 : 5}px;background:${r.color};display:inline-block"></span>` : ""}${F.escape(r.label)}</span>
      <b style="font-weight:600">${F.escape(r.value)}</b></div>`)
    .join("");
  return `<div style="font-size:12.5px;opacity:.75;margin-bottom:4px">${F.escape(title)}</div>${lines}`;
}

export function categoryAxis(p, data, { labels = (v) => v, show = true, gridIndex = 0, boundaryGap = true } = {}) {
  return {
    type: "category", data, gridIndex, boundaryGap,
    axisLine: { show, lineStyle: { color: p.base } },
    axisTick: { show: false },
    axisLabel: { show, color: p.muted, fontSize: 12, hideOverlap: true, formatter: labels },
  };
}

/**
 * Valeur « tracée » d'une métrique : les durées en heures (graduations rondes),
 * les allures en secondes par km (axe inversé : plus haut = plus rapide).
 */
export function toChart(meta, v) {
  if (!F.isNum(v)) return null;
  if (meta?.fmt === "duration") return v / 3600;
  if (meta?.fmt === "pace") return v > 0.3 ? 1000 / v : null;
  return v;
}

export function fromChart(meta, v) {
  if (!F.isNum(v)) return null;
  if (meta?.fmt === "duration") return v * 3600;
  if (meta?.fmt === "pace") return v > 0 ? 1000 / v : null;
  return v;
}

/** Bornes et pas « ronds » pour un axe d'allure (secondes par km). */
export function paceRange(values) {
  const nums = values.filter(F.isNum).sort((a, b) => a - b);
  if (!nums.length) return {};
  const lo = nums[Math.floor(nums.length * 0.02)];
  const hi = nums[Math.ceil(nums.length * 0.98) - 1];
  const span = Math.max(hi - lo, 20);
  const interval = [10, 15, 20, 30, 60, 120, 300].find((s) => span / s <= 5) || 600;
  return { min: Math.floor(lo / interval) * interval, max: Math.ceil(hi / interval) * interval, interval };
}

/** Graduation d'un axe de durée (tracé en heures) : « 20 min », « 1 h », « 1 h 30 ». */
export function hoursLabel(v) {
  if (!F.isNum(v)) return "";
  const minutes = Math.round(v * 60);
  if (!minutes) return "0";
  if (minutes < 60) return `${minutes} min`;
  return minutes % 60 ? `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}` : `${minutes / 60} h`;
}

/** Pas « ronds » en minutes pour un axe de durées courtes (valeurs en heures) ; rien au-delà de 4 h. */
export function durationRange(values) {
  const hi = Math.max(0, ...values.filter(F.isNum));
  if (!(hi > 0) || hi > 4) return {};
  const step = [5, 10, 15, 20, 30, 60].find((m) => (hi * 60) / m <= 5) || 60;
  return { min: 0, max: (Math.ceil((hi * 60) / step) * step) / 60, interval: step / 60 };
}

export function valueAxis(p, meta, { gridIndex = 0, scale = true, min, max, interval, splitNumber = 4, formatter, hideMax = false } = {}) {
  let fmt = formatter || ((v) => F.axis(meta, v));
  let inverse = false;
  if (!formatter && meta?.fmt === "duration") fmt = hoursLabel;
  if (!formatter && meta?.fmt === "pace") { fmt = (v) => F.chrono(v); inverse = true; }
  return {
    type: "value", gridIndex, scale, min, max, interval, splitNumber, inverse,
    axisLine: { show: false }, axisTick: { show: false },
    splitLine: { lineStyle: { color: p.hair, width: 1 } },
    axisLabel: { color: p.muted, fontSize: 12, formatter: fmt, showMaxLabel: !hideMax || inverse, showMinLabel: !(hideMax && inverse) },
  };
}

/** Courbe 2 px ; seul le dernier point porte un repère de 8 px cerclé de la couleur du fond. */
export function line(p, color, data, { area = false, name, xAxisIndex = 0, yAxisIndex = 0, smooth = false, connectNulls = false } = {}) {
  let last = -1;
  data.forEach((v, i) => { if (F.isNum(Array.isArray(v) ? v[1] : v)) last = i; });
  const points = data.map((v, i) => (i === last ? { value: v, symbol: "circle", symbolSize: 8 } : v));
  return {
    type: "line", name, data: points, xAxisIndex, yAxisIndex, smooth,
    symbol: "none", connectNulls,
    lineStyle: { width: 2, color, cap: "round", join: "round" },
    itemStyle: { color, borderColor: p.surface, borderWidth: 2 },
    areaStyle: area ? { color, opacity: 0.1 } : undefined,
    emphasis: { disabled: true },
  };
}

export function bars(p, color, data, { name, stack, top = true, xAxisIndex = 0, yAxisIndex = 0 } = {}) {
  return {
    type: "bar", name, data, stack, xAxisIndex, yAxisIndex,
    barMaxWidth: 24,
    itemStyle: { color, borderRadius: top ? [4, 4, 0, 0] : 0, borderColor: stack ? p.surface : undefined, borderWidth: stack ? 1 : 0 },
    emphasis: { disabled: true },
  };
}

/** Graphique dont l'option dépend de la taille (petits multiples) : reconstruit à chaque redimensionnement. */
export function mountSized(el, build, onReady) {
  const chart = echarts.init(el, null, { renderer: "canvas" });
  let lastH = 0;
  let zoom = null;
  const apply = () => {
    const h = el.clientHeight;
    if (Math.abs(h - lastH) > 4) {
      lastH = h;
      const option = build(el.clientWidth, h);
      chart.setOption(option, { notMerge: true });
      zoom?.dispose();
      zoom = zoomable(el, chart, option);
    }
    chart.resize();
  };
  apply();
  const observer = new ResizeObserver(apply);
  observer.observe(el);
  if (onReady) onReady(chart);
  return { chart, dispose() { observer.disconnect(); zoom?.dispose(); chart.dispose(); } };
}

/**
 * Petits multiples dans un seul graphique : une grille par métrique, empilées,
 * axe horizontal commun, une seule info-bulle. Renvoie les grilles et la position
 * verticale (px) du libellé de chacune.
 */
export function gridStack(count, height, { top = 24, bottom = 24, gap = 34, weights } = {}) {
  const w = weights || Array(count).fill(1);
  const total = w.reduce((a, b) => a + b, 0);
  const free = Math.max(height - top - bottom - gap * (count - 1), 40 * count);
  const grids = [];
  const titles = [];
  let y = top;
  for (let i = 0; i < count; i += 1) {
    const h = (free * w[i]) / total;
    grids.push({ left: 6, right: 14, top: y, height: h, containLabel: true });
    titles.push(y - 22);
    y += h + gap;
  }
  return { grids, titles };
}

export function gridTitle(p, text, top) {
  return { text, left: 4, top, textStyle: { fontSize: 13, fontWeight: 500, color: p.ink2, fontFamily: p.font } };
}

export function legendHTML(items) {
  return `<div class="legend">${items.map((it) => `<span>${
    it.kind === "band" ? '<i class="key-band"></i>'
      : it.kind === "band-color" ? `<i class="key-band" style="background:color-mix(in srgb, ${it.color} 22%, transparent)"></i>`
      : it.kind === "square" ? `<i class="dot" style="border-radius:2px;background:${it.color}"></i>`
        : it.kind === "dot" ? `<i class="dot" style="background:${it.color}"></i>`
          : `<i class="key-line" style="background:${it.color}"></i>`
  }${F.escape(it.label)}</span>`).join("")}</div>`;
}
