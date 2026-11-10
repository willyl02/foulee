// Tuiles de données : chiffres clés, séries, charge, zones, calendrier, nuage,
// comparaison par poste, objectif, fractions, note.
import * as api from "./api.js";
import * as C from "./charts.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

export function message(body, text) {
  body.innerHTML = `<div class="tile-msg">${F.escape(text)}</div>`;
}

function chartShell(body, legend = "") {
  body.innerHTML = `<div class="stack">${legend}<div class="chart-wrap"><div class="chart"></div></div></div>`;
  return body.querySelector(".chart");
}

const LECTURE = {
  "net": "net", "moyen": "moyen", "faible": "faible", "négligeable": "négligeable",
  "pas assez de jours": "trop peu de jours", "valeurs identiques": "aucun",
};

// ------------------------------------------------------------- chiffre clé
export const kpi = {
  ownHead: true,
  title: (p, ctx) => ctx.meta(p.metrique)?.label || "Chiffre clé",
  async render(body, p, ctx, tile) {
    const meta = ctx.meta(p.metrique);
    const d = await api.get("/api/kpi", {
      metric: p.metrique, baseline: p.reference_jours, window: p.fenetre === "auto" ? "" : p.fenetre,
    });
    const label = tile.titre || meta.label;
    const value = F.value(meta, d.value, { unit: false });
    const unit = ["duration", "clock"].includes(meta.fmt) ? "" : meta.fmt === "pace" ? "/km" : meta.fmt === "km" ? "km" : (meta.unit === "/100" ? "/100" : meta.unit);
    const span = d.window === "semaine" ? "les 4 semaines d'avant" : d.window === "mois" ? "les mois d'avant" : `ta moyenne ${d.baseline_days} j`;
    let deltaHtml = `<div class="kpi-delta">Pas de référence</div>`;
    if (F.isNum(d.value) && F.isNum(d.baseline)) {
      const text = F.delta(meta, d.value, d.baseline);
      const rel = Math.abs(d.delta_pct ?? (d.delta / (Math.abs(d.baseline) || 1)) * 100);
      let cls = "";
      let arrow = "flat";
      if (rel >= 2 && d.delta !== 0) {
        arrow = d.delta > 0 ? "up" : "down";
        if (meta.better) cls = (d.delta > 0) === (meta.better === "up") ? "good" : "bad";
      }
      const qualifier = cls === "good" ? "Mieux que" : cls === "bad" ? "Moins bien que" : "Par rapport à";
      const tip = `${qualifier} ${span} (${F.value(meta, d.baseline)})`;
      deltaHtml = `<div class="kpi-delta ${cls}" title="${F.escape(tip)}">${icon(arrow)}<span>${F.escape(text)} vs ${F.escape(span)}</span></div>`;
    } else if (!F.isNum(d.value)) {
      deltaHtml = `<div class="kpi-delta">Pas de valeur récente</div>`;
    }
    const today = F.isoDate(new Date());
    const stale = d.date && d.window === "jour" && d.date !== today ? `<span class="kpi-date">, au ${F.dateShort(d.date)}</span>` : "";
    body.innerHTML = `
      <div class="kpi-label" title="${F.escape(meta.description || meta.label)}">${F.escape(label)}${stale}</div>
      <div class="kpi-value">${F.escape(value)}${unit ? `<span class="kpi-unit">${F.escape(unit)}</span>` : ""}</div>
      ${deltaHtml}
      ${sparkline(d.spark, ctx.palette)}`;
  },
};

function sparkline(points, p) {
  const vals = (points || []).map((pt) => pt[1]);
  const nums = vals.filter(F.isNum);
  if (nums.length < 3) return "";
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;
  const w = 120;
  const h = 30;
  const step = w / Math.max(vals.length - 1, 1);
  let path = "";
  let pen = false;
  let last = null;
  vals.forEach((v, i) => {
    if (!F.isNum(v)) { pen = false; return; }
    const x = i * step;
    const y = h - 4 - ((v - min) / range) * (h - 8);
    path += `${pen ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    pen = true;
    last = [x, y];
  });
  return `<svg class="kpi-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path d="${path}" fill="none" stroke="${p.base}" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`;
}

// ------------------------------------------------------------- série
/** Fonds colorés selon le poste de travail de chaque jour (un aplat par suite de jours du même poste). */
function shiftBands(dates, ctx) {
  const ranges = [];
  let current = null;
  for (const iso of dates) {
    const label = F.shiftOf(F.parseDate(iso), ctx.settings, true);
    if (label && label !== "repos" && current && current.label === label) {
      current.end = iso;
    } else {
      if (current) ranges.push(current);
      current = label && label !== "repos" ? { label, start: iso, end: iso } : null;
    }
  }
  if (current) ranges.push(current);
  return ranges.map((r) => [{ xAxis: r.start, itemStyle: { color: F.shiftColor(r.label, ctx.settings, ctx.palette), opacity: 0.1 } }, { xAxis: r.end }]);
}

function shiftLegend(ctx, used) {
  return used.map((id) => ({ label: F.shiftName(id, ctx.settings), color: F.shiftColor(id, ctx.settings, ctx.palette), kind: "band-color" }));
}

export const serie = {
  title: (p, ctx) => p.metriques.map((k) => ctx.meta(k)?.label).filter(Boolean).join(" et "),
  async render(body, p, ctx, tile, cleanup) {
    const { start, end } = ctx.period(p);
    const metas = p.metriques.map((k) => ctx.meta(k)).filter(Boolean);
    const results = await Promise.all(metas.map((m) => api.get("/api/series", {
      metric: m.key, start, end, agg: p.agregation, fn: p.fonction === "auto" ? "" : p.fonction,
      sport: p.sport === "tous" ? "" : p.sport, smooth: p.lissage || 0,
    })));
    if (results.every((r) => r.points.every((pt) => !F.isNum(pt[1])))) {
      return message(body, "Pas de données sur cette période.");
    }
    const P = ctx.palette;
    const dates = results[0].points.map((pt) => pt[0]);
    const kinds = new Set(metas.map((m) => `${m.fmt}|${m.unit}`));
    const stacked = metas.length > 1 && (p.disposition === "empiler" || (p.disposition === "auto" && kinds.size > 1));
    const bands = p.bandes_postes && p.agregation === "jour" ? shiftBands(dates, ctx) : [];
    const legend = [];
    if (!stacked && metas.length > 1) metas.forEach((m, i) => legend.push({ label: m.label, color: P.series[i], kind: p.style === "barres" ? "square" : "line" }));
    if (bands.length) legend.push(...shiftLegend(ctx, [...new Set(bands.map((b) => F.shiftOf(F.parseDate(b[0].xAxis), ctx.settings, true)))]));
    const el = chartShell(body, legend.length ? C.legendHTML(legend) : "");
    const labelOf = (iso) => F.periodLabel(iso, p.agregation);
    const plotted = results.map((r, i) => r.points.map((pt) => C.toChart(metas[i], pt[1])));
    const tooltip = {
      ...C.tooltipBase(P),
      formatter: (items) => C.tooltipHTML(F.periodLong(items[0].axisValue, p.agregation),
        items.map((it) => ({ label: metas[it.seriesIndex]?.label, color: it.color, value: F.value(metas[it.seriesIndex], results[it.seriesIndex].points[it.dataIndex]?.[1]) }))),
    };
    const seriesFor = (i, xAxisIndex = 0, yAxisIndex = 0) => {
      const color = P.series[i % P.series.length];
      const sparse = metas[i].agg === "last" || plotted[i].filter((v) => v === null).length > plotted[i].length / 2;
      const s = p.style === "barres"
        ? C.bars(P, color, plotted[i], { name: metas[i].label, xAxisIndex, yAxisIndex })
        : C.line(P, color, plotted[i], { name: metas[i].label, area: p.style === "aire", xAxisIndex, yAxisIndex, connectNulls: sparse });
      if (bands.length) s.markArea = { silent: true, data: bands };
      return s;
    };
    const axisFor = (i, extra = {}) => {
      const range = metas[i].fmt === "pace" ? C.paceRange(stacked ? plotted[i] : plotted.flat()) : {};
      return C.valueAxis(P, metas[i], { scale: p.style !== "barres", ...range, ...extra });
    };
    if (!stacked) {
      cleanup(C.mount(el, {
        ...C.baseOption(P), tooltip,
        xAxis: C.categoryAxis(P, dates, { labels: labelOf, boundaryGap: p.style === "barres" }),
        yAxis: axisFor(0),
        series: metas.map((_, i) => seriesFor(i)),
      }));
      return;
    }
    cleanup(C.mountSized(el, (w, h) => {
      const { grids, titles } = C.gridStack(metas.length, h);
      return {
        ...C.baseOption(P), tooltip, grid: grids,
        title: metas.map((m, i) => C.gridTitle(P, m.label, titles[i])),
        axisPointer: { link: [{ xAxisIndex: "all" }] },
        xAxis: metas.map((_, i) => C.categoryAxis(P, dates, { labels: labelOf, gridIndex: i, show: i === metas.length - 1, boundaryGap: p.style === "barres" })),
        yAxis: metas.map((m, i) => axisFor(i, { gridIndex: i, splitNumber: 2, hideMax: true })),
        series: metas.map((_, i) => seriesFor(i, i, i)),
      };
    }));
  },
};

// ------------------------------------------------------------- charge
export const charge = {
  title: () => "Forme et fatigue",
  async render(body, p, ctx, tile, cleanup) {
    const { start, end } = ctx.period(p);
    const d = await api.get("/api/load", { start, end });
    if (!d.ctl.some((pt) => F.isNum(pt[1]) && pt[1] > 0)) return message(body, "Pas encore de séances pour calculer la charge.");
    const P = ctx.palette;
    const dates = d.ctl.map((pt) => pt[0]);
    const ratio = !!p.afficher_ratio;
    const legend = [
      { label: "Charge chronique (42 j)", color: P.series[0] },
      { label: "Charge aiguë (7 j)", color: P.series[1] },
      { label: "Fraîcheur positive", color: P.divPos, kind: "square" },
      { label: "négative", color: P.divNeg, kind: "square" },
    ];
    if (ratio) legend.push({ kind: "band", label: "Ratio entre 0,8 et 1,3" });
    const el = chartShell(body, C.legendHTML(legend));
    const metaLoad = { fmt: "int", unit: "" };
    const titles = ["Charge", "Fraîcheur", "Ratio aiguë / chronique"];
    cleanup(C.mountSized(el, (w, h) => {
      const n = ratio ? 3 : 2;
      const { grids, titles: tops } = C.gridStack(n, h, { weights: ratio ? [2, 1, 1] : [2, 1] });
      const tsb = d.tsb.map((pt) => (F.isNum(pt[1]) ? { value: pt[1], itemStyle: { color: pt[1] >= 0 ? P.divPos : P.divNeg, borderRadius: pt[1] >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2] } } : null));
      const series = [
        C.line(P, P.series[0], d.ctl.map((pt) => pt[1]), { name: "Charge chronique (42 j)" }),
        C.line(P, P.series[1], d.atl.map((pt) => pt[1]), { name: "Charge aiguë (7 j)" }),
        { type: "bar", name: "Fraîcheur", data: tsb, xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 6, emphasis: { disabled: true } },
      ];
      if (ratio) {
        const s = C.line(P, P.series[2], d.acwr.map((pt) => pt[1]), { name: "Ratio", xAxisIndex: 2, yAxisIndex: 2 });
        s.markArea = { silent: true, itemStyle: { color: P.band }, data: [[{ yAxis: 0.8 }, { yAxis: 1.3 }]] };
        series.push(s);
      }
      return {
        ...C.baseOption(P), grid: grids,
        title: titles.slice(0, n).map((t, i) => C.gridTitle(P, t, tops[i])),
        axisPointer: { link: [{ xAxisIndex: "all" }] },
        tooltip: {
          ...C.tooltipBase(P),
          formatter: (items) => C.tooltipHTML(F.dateLong(items[0].axisValue, { year: true }), items.map((it) => ({
            label: it.seriesName, color: it.seriesName === "Fraîcheur" ? (it.value >= 0 ? P.divPos : P.divNeg) : it.color,
            value: it.seriesName === "Ratio" ? F.dec2(it.value?.value ?? it.value) : F.int(it.value?.value ?? it.value),
          }))),
        },
        xAxis: Array.from({ length: n }, (_, i) => C.categoryAxis(P, dates, { labels: F.dateShort, gridIndex: i, show: i === n - 1, boundaryGap: false })),
        yAxis: Array.from({ length: n }, (_, i) => C.valueAxis(P, metaLoad, {
          gridIndex: i, splitNumber: i ? 2 : 3, scale: i === 2, hideMax: true,
          formatter: i === 2 ? (v) => F.dec1(v) : undefined,
        })),
        series,
      };
    }));
  },
};

// ------------------------------------------------------------- zones
export const zones = {
  title: (p) => (p.zones === "allure" ? "Temps par zone d'allure" : "Temps par zone de FC"),
  async render(body, p, ctx, tile, cleanup) {
    const { start, end } = ctx.period(p);
    const d = await api.get("/api/zones", {
      kind: p.zones, start, end, group: p.groupe, sport: p.sport === "tous" ? (p.zones === "allure" ? "pied" : "") : p.sport,
    });
    if (!d.seances) {
      return message(body, p.zones === "allure"
        ? "Pas de séance de course avec courbes sur la période (les fichiers FIT arrivent avec la synchro)."
        : "Pas de séance avec zones de FC sur la période.");
    }
    if (p.zones === "allure") ctx.sub(`VMA ${F.dec1(ctx.settings.vma_kmh)} km/h`);
    const P = ctx.palette;
    const names = d.noms;
    if (p.groupe === "total") {
      const secs = d.series[0].secondes;
      const total = secs.reduce((a, b) => a + b, 0) || 1;
      const el = chartShell(body);
      cleanup(C.mount(el, {
        ...C.baseOption(P),
        grid: { left: 6, right: 70, top: 4, bottom: 4, containLabel: true },
        tooltip: {
          ...C.tooltipBase(P, "item"),
          formatter: (it) => C.tooltipHTML(names[it.dataIndex], [
            { label: "Bornes", value: d.bornes[it.dataIndex] },
            { label: "Temps", value: F.duration(secs[it.dataIndex]) },
            { label: "Part", value: `${Math.round((secs[it.dataIndex] / total) * 100)} %` },
          ]),
        },
        xAxis: { type: "value", show: false },
        yAxis: { type: "category", data: names, inverse: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: P.ink2, fontSize: 13 } },
        series: [{
          type: "bar", barMaxWidth: 22,
          data: secs.map((s, i) => ({ value: s, itemStyle: { color: P.zones[i], borderRadius: [0, 4, 4, 0] } })),
          label: { show: true, position: "right", color: P.ink2, fontSize: 12.5, formatter: (it) => `${F.duration(it.value, { short: true })}  ${Math.round((it.value / total) * 100)} %` },
          emphasis: { disabled: true },
        }],
      }));
      return;
    }
    const periods = d.series.map((s) => s.periode);
    const el = chartShell(body, C.legendHTML(names.map((n, i) => ({ label: n, color: P.zones[i], kind: "square" }))));
    cleanup(C.mount(el, {
      ...C.baseOption(P),
      tooltip: {
        ...C.tooltipBase(P),
        formatter: (items) => C.tooltipHTML(F.periodLong(items[0].axisValue, p.groupe), [
          ...items.slice().reverse().map((it) => ({ label: `${names[it.seriesIndex]} (${d.bornes[it.seriesIndex]})`, color: it.color, square: true, value: F.duration(d.series[it.dataIndex].secondes[it.seriesIndex]) })),
          { label: "Total", value: F.duration(d.series[items[0].dataIndex].secondes.reduce((a, v) => a + v, 0)) },
        ]),
      },
      xAxis: C.categoryAxis(P, periods, { labels: (v) => F.periodLabel(v, p.groupe) }),
      yAxis: C.valueAxis(P, { fmt: "duration" }, { scale: false }),
      series: names.map((n, i) => C.bars(P, P.zones[i], d.series.map((s) => s.secondes[i] / 3600), { name: n, stack: "z", top: i === names.length - 1 })),
    }));
  },
};

// ------------------------------------------------------------- calendrier
export const calendrier = {
  title: (p, ctx) => `${ctx.meta(p.metrique)?.label || "Calendrier"} jour par jour`,
  async render(body, p, ctx, tile, cleanup) {
    const meta = ctx.meta(p.metrique);
    const months = Number(p.mois) || 6;
    const end = new Date();
    const start = new Date(end.getFullYear(), end.getMonth() - months + 1, 1);
    const d = await api.get("/api/calendar", { metric: p.metrique, start: F.isoDate(start), end: F.isoDate(end) });
    const values = d.points.map((pt) => pt[1]).filter(F.isNum);
    if (!values.length) return message(body, "Pas de données sur cette période.");
    const P = ctx.palette;
    const el = chartShell(body);
    const sorted = values.slice().sort((a, b) => a - b);
    const lo = sorted[Math.floor(sorted.length * 0.05)];
    const hi = sorted[Math.floor(sorted.length * 0.95)];
    cleanup(C.mountSized(el, (w, h) => {
      const weeks = Math.ceil((end - start) / (7 * 86400000)) + 1;
      const cell = Math.max(8, Math.min(22, Math.floor((w - 40) / weeks), Math.floor((h - 50) / 7)));
      return {
        ...C.baseOption(P),
        tooltip: { ...C.tooltipBase(P, "item"), formatter: (it) => C.tooltipHTML(F.dateLong(it.value[0], { year: true }), [{ label: meta.label, value: F.value(meta, it.value[1]) }]) },
        visualMap: {
          min: lo, max: hi, calculable: false, orient: "horizontal", left: "center", bottom: 0, itemWidth: 10, itemHeight: 120,
          inRange: { color: P.seq.slice(1) }, text: [F.value(meta, hi), F.value(meta, lo)], textStyle: { color: P.muted, fontSize: 12 },
          textGap: 8,
        },
        calendar: {
          range: [F.isoDate(start), F.isoDate(end)], cellSize: [cell, cell], top: 22, left: 30, right: 6,
          orient: "horizontal", splitLine: { show: false }, itemStyle: { color: P.surface, borderColor: P.surface, borderWidth: 2 },
          yearLabel: { show: false },
          dayLabel: { firstDay: 1, nameMap: ["D", "L", "M", "M", "J", "V", "S"], color: P.muted, fontSize: 11 },
          monthLabel: { nameMap: ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."], color: P.muted, fontSize: 12 },
        },
        series: [{ type: "heatmap", coordinateSystem: "calendar", data: d.points, itemStyle: { borderRadius: 3, borderColor: P.surface, borderWidth: 2 } }],
      };
    }));
  },
};

// ------------------------------------------------------------- nuage
export const nuage = {
  title: (p, ctx) => `${ctx.meta(p.y)?.label} selon ${ctx.meta(p.x)?.label?.toLowerCase()}`,
  async render(body, p, ctx, tile, cleanup) {
    const { start, end } = ctx.period(p);
    const mx = ctx.meta(p.x);
    const my = ctx.meta(p.y);
    const d = await api.get("/api/scatter", { x: p.x, y: p.y, start, end, lag: p.decalage });
    if (d.n < 5) return message(body, "Pas assez de jours avec les deux mesures sur cette période.");
    ctx.sub(F.isNum(d.r) ? `r = ${F.dec2(d.r)} sur ${d.n} jours` : `${d.n} jours`);
    const P = ctx.palette;
    const groups = p.couleur_postes
      ? [...(d.groupes || []).map((g) => [g.id, g.nom, F.shiftColor(g.id, ctx.settings, P)]), [null, "Repos et congés", P.base]]
      : [["*", "Jours", P.series[0]]];
    const used = groups.filter(([key]) => key === "*" || d.points.some((pt) => pt.poste === key));
    const xs = d.points.map((pt) => C.toChart(mx, pt.x));
    const ys = d.points.map((pt) => C.toChart(my, pt.y));
    const n = xs.length;
    const mxv = xs.reduce((a, b) => a + b, 0) / n;
    const myv = ys.reduce((a, b) => a + b, 0) / n;
    const slope = xs.reduce((a, x, i) => a + (x - mxv) * (ys[i] - myv), 0) / (xs.reduce((a, x) => a + (x - mxv) ** 2, 0) || 1);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const legend = used.map(([, label, color]) => ({ label, color, kind: "dot" }));
    legend.push({ label: "Tendance", color: P.ink2 });
    const el = chartShell(body, C.legendHTML(legend));
    cleanup(C.mount(el, {
      ...C.baseOption(P),
      tooltip: {
        ...C.tooltipBase(P, "item"),
        formatter: (it) => (it.seriesName === "Tendance" ? "" : C.tooltipHTML(F.dateLong(it.data.date, { year: true }), [
          { label: mx.label, value: F.value(mx, it.data.raw[0]) },
          { label: my.label + (Number(p.decalage) ? ` (J+${p.decalage})` : ""), value: F.value(my, it.data.raw[1]) },
        ])),
      },
      xAxis: { ...C.valueAxis(P, mx), name: mx.label, nameLocation: "middle", nameGap: 26, nameTextStyle: { color: P.muted, fontSize: 12 } },
      yAxis: C.valueAxis(P, my),
      grid: { left: 6, right: 14, top: 10, bottom: 26, containLabel: true },
      series: [
        ...used.map(([key, label, color]) => ({
          type: "scatter", name: label, symbolSize: 8,
          itemStyle: { color, borderColor: P.surface, borderWidth: 2, opacity: 0.9 },
          data: d.points.filter((pt) => key === "*" || pt.poste === key).map((pt) => ({ value: [C.toChart(mx, pt.x), C.toChart(my, pt.y)], raw: [pt.x, pt.y], date: pt.date })),
          emphasis: { scale: 1.4 },
        })),
        { type: "line", name: "Tendance", symbol: "none", silent: true, lineStyle: { color: P.ink2, width: 1.5, opacity: 0.7 },
          data: [[minX, myv + slope * (minX - mxv)], [maxX, myv + slope * (maxX - mxv)]] },
      ],
    }));
  },
};

// ------------------------------------------------------- comparaison par poste
export const postes = {
  title: () => "Comparaison par poste",
  async render(body, p, ctx) {
    const { start, end } = ctx.period(p);
    const h = ctx.settings.horaires || {};
    if (h.actif === false) return message(body, "Les horaires de travail sont désactivés dans les réglages.");
    const d = await api.get("/api/shifts", { metrics_list: p.metriques.join(","), start, end, weekdays: p.jours_ouvres ? 1 : 0 });
    const P = ctx.palette;
    const groups = (d.groupes || []).filter((g) => d.jours[g.id]);
    if (groups.length < 2) return message(body, "Il faut au moins deux postes différents sur la période pour comparer.");
    const color = (id) => F.shiftColor(id, ctx.settings, P);
    ctx.sub(`${groups.map((g) => `${d.jours[g.id]} j ${g.nom.toLowerCase()}`).join(", ")}${d.jours_ouvres_seulement ? ", jours travaillés" : ""}`);
    const two = groups.length === 2;
    const rows = d.metriques.map((m) => {
      const meta = ctx.meta(m.metric);
      const stats = groups.map((g) => m.groupes[g.id]);
      const has = stats.filter((st) => F.isNum(st.moyenne));
      let svg = "";
      if (has.length >= 2) {
        // Lecture « forêt » : un point par poste (moyenne) et un trait pour ± un écart-type.
        const spread = (st) => (F.isNum(st.ecart_type) ? st.ecart_type : 0);
        const lo = Math.min(...has.map((st) => st.moyenne - spread(st)));
        const hi = Math.max(...has.map((st) => st.moyenne + spread(st)));
        const x = (v) => 3 + ((v - lo) / ((hi - lo) || 1)) * 94;
        const step = Math.min(12, 26 / groups.length);
        svg = `<div class="forest" aria-hidden="true">${groups.map((g, i) => {
          const st = m.groupes[g.id];
          if (!F.isNum(st.moyenne)) return "";
          const top = 2 + i * step;
          return `<i class="whisker" style="left:${x(st.moyenne - spread(st))}%;width:${x(st.moyenne + spread(st)) - x(st.moyenne - spread(st))}%;top:${top + 3}px;background:${color(g.id)}"></i>
            <i class="pt" style="left:${x(st.moyenne)}%;top:${top}px;background:${color(g.id)}"></i>`;
        }).join("")}</div>`;
      }
      const [a, b] = m.entre || [];
      const diff = m.entre ? F.delta(meta, m.groupes[a].moyenne, m.groupes[b].moyenne) : "–";
      const between = m.entre && !two ? `<br><small>${F.escape(F.shiftName(a, ctx.settings))} − ${F.escape(F.shiftName(b, ctx.settings))}</small>` : "";
      const tip = groups.map((g) => `${g.nom} : moyenne ${F.value(meta, m.groupes[g.id].moyenne)}, médiane ${F.value(meta, m.groupes[g.id].mediane)} (${m.groupes[g.id].n} j)`).join(". ") + ". Barres pâles : ± un écart-type.";
      return `<div class="shift-row" style="--n:${groups.length}" title="${F.escape(tip)}">
        <span>${F.escape(m.label)}</span>
        ${groups.map((g) => `<span class="val">${F.escape(F.value(meta, m.groupes[g.id].moyenne))}</span>`).join("")}
        <span class="bar-cell">${svg}</span>
        <span class="effect"><b>${F.escape(diff || "–")}</b>${between}<br>écart ${F.escape(LECTURE[m.effet.lecture] || m.effet.lecture)}</span>
      </div>`;
    }).join("");
    body.classList.add("scroll");
    const head = two ? `${F.escape(groups[0].nom)} − ${F.escape(groups[1].nom.toLowerCase())}` : "Écart max";
    body.innerHTML = `${C.legendHTML(groups.map((g) => ({ label: `${g.nom}${g.debut ? ` (${g.debut}–${g.fin})` : ""}`, color: color(g.id), kind: "dot" })))}
      <div class="shift-rows" role="table">
        <div class="shift-row head-row" style="--n:${groups.length}"><span>Métrique</span>${groups.map((g) => `<span class="val">${F.escape(g.nom)}</span>`).join("")}<span class="bar-cell"></span><span class="effect">${head}</span></div>
        ${rows}
      </div>`;
  },
};

// ------------------------------------------------------------- objectif
export const objectif = {
  title: () => "Objectif",
  async render(body, p, ctx) {
    const o = await api.get("/api/objective");
    if (!o.date) return message(body, "Définis ton objectif dans les réglages.");
    const left = o.jours_restants;
    const counter = left > 0 ? `${left}<small>jour${left > 1 ? "s" : ""}</small>` : left === 0 ? "Jour J" : "Passé";
    body.innerHTML = `<div class="goal">
      <div>
        <div class="goal-name">${F.escape(o.nom || "Objectif")}</div>
        <div class="goal-meta">${F.escape(F.dateLong(o.date, { year: true }))}${F.isNum(o.semaines_restantes) && left > 0 ? `, dans ${F.dec1(o.semaines_restantes)} semaines` : ""}</div>
      </div>
      <div class="goal-count">${counter}</div>
      <dl class="goal-rows">
        <dt>Temps visé</dt><dd>${F.escape(o.temps_cible || "–")}</dd>
        <dt>Allure cible</dt><dd>${F.escape(o.allure_cible || "–")}</dd>
        <dt>Vitesse</dt><dd>${F.isNum(o.vitesse_cible_kmh) ? `${F.dec1(o.vitesse_cible_kmh)} km/h` : "–"}</dd>
        <dt>Part de ta VMA</dt><dd>${F.isNum(o.pct_vma) ? `${Math.round(o.pct_vma)} % de ${F.dec1(ctx.settings.vma_kmh)} km/h` : "–"}</dd>
      </dl>
    </div>`;
  },
};

// ------------------------------------------------------------- fractions
export const fractions = {
  title: () => "Fractions rapides face à l'allure cible",
  async render(body, p, ctx, tile, cleanup) {
    const { start, end } = ctx.period(p);
    const d = await api.get("/api/fast-laps", { start, end });
    ctx.sub(`Tours plus rapides que ${d.seuil_allure} (${d.seuil_pct_vma} % de VMA)`);
    if (!d.seances.length) return message(body, "Aucun tour rapide sur la période. Les tours viennent des fichiers FIT, téléchargés à la synchro.");
    const P = ctx.palette;
    const target = d.objectif?.vitesse_cible;
    const longLabel = `Fractions longues (${F.duration(d.duree_longue_s)} et plus)`;
    const kinds = [
      ["longs", longLabel, P.series[0]],
      ["courts", "Fractions courtes", P.series[1]],
    ].filter(([key]) => d.seances.some((s) => s[key]));
    const legend = kinds.map(([, label, color]) => ({ label, color, kind: "dot" }));
    if (target) legend.push({ label: `Allure cible ${d.objectif.allure_cible}`, color: P.ink2 });
    const el = chartShell(body, C.legendHTML(legend));
    const secs = d.seances.flatMap((s) => kinds.map(([key]) => (s[key] ? 1000 / s[key].vitesse : null)));
    if (target) secs.push(1000 / target);
    const range = C.paceRange(secs);
    cleanup(C.mount(el, {
      ...C.baseOption(P),
      grid: { left: 6, right: 16, top: 12, bottom: 4, containLabel: true },
      tooltip: {
        ...C.tooltipBase(P, "item"),
        formatter: (it) => {
          const s = d.seances.find((x) => x.date === it.data.date && x.id === it.data.id);
          const part = s?.[it.data.kind];
          if (!part) return "";
          return C.tooltipHTML(`${F.dateLong(s.date)} : ${s.nom || "séance"}`, [
            { label: it.seriesName, value: `${part.fractions} tour${part.fractions > 1 ? "s" : ""}, ${F.dec1(part.distance_m / 1000)} km` },
            { label: "Allure moyenne", value: part.allure },
            { label: "FC moyenne", value: F.isNum(part.fc_moy) ? `${part.fc_moy} bpm` : "–" },
          ]);
        },
      },
      xAxis: { type: "time", axisLine: { lineStyle: { color: P.base } }, axisTick: { show: false }, splitLine: { show: false },
        axisLabel: { color: P.muted, fontSize: 12, hideOverlap: true, formatter: (v) => F.dateShort(F.isoDate(new Date(v))) } },
      yAxis: C.valueAxis(P, { fmt: "pace" }, range),
      series: kinds.map(([key, label, color], i) => ({
        type: "line", name: label, connectNulls: true, symbol: "circle", symbolSize: 9,
        data: d.seances.filter((s) => s[key]).map((s) => ({ value: [s.date, 1000 / s[key].vitesse], date: s.date, id: s.id, kind: key })),
        lineStyle: { width: 2, color }, itemStyle: { color, borderColor: P.surface, borderWidth: 2 }, emphasis: { scale: 1.3 },
        markLine: target && i === 0 ? { silent: true, symbol: "none", lineStyle: { color: P.ink2, width: 1, type: "solid" }, label: { show: false }, data: [{ yAxis: 1000 / target }] } : undefined,
      })),
    }));
  },
};

// ------------------------------------------------------------- note
export const note = {
  title: () => "Note",
  async render(body, p) {
    const text = F.escape(p.texte || "Note vide : passe en mode modification pour écrire.").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    body.innerHTML = `<div class="note">${text}</div>`;
  },
};
