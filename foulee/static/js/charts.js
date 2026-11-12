// Habillage commun des graphiques ECharts : couleurs lues dans le CSS (clair / sombre),
// traits fins, grille discrète, info-bulles au survol.
import * as F from "./format.js";

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
  const observer = new ResizeObserver(() => chart.resize());
  observer.observe(el);
  if (onReady) onReady(chart);
  return { chart, dispose() { observer.disconnect(); chart.dispose(); } };
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
  const apply = () => {
    const h = el.clientHeight;
    if (Math.abs(h - lastH) > 4) {
      lastH = h;
      chart.setOption(build(el.clientWidth, h), { notMerge: true });
    }
    chart.resize();
  };
  apply();
  const observer = new ResizeObserver(apply);
  observer.observe(el);
  if (onReady) onReady(chart);
  return { chart, dispose() { observer.disconnect(); chart.dispose(); } };
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
