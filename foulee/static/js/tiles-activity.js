// Tuiles « séances » : liste, dernière séance, et le détail de la séance choisie
// (résumé, carte, courbes, tours).
import * as api from "./api.js";
import * as C from "./charts.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { message } from "./tiles-data.js";

const FOOT_SPORTS = ["course", "trail", "marche", "rando"];
const INTENSITY = { warmup: "Échauffement", active: "Effort", rest: "Récup", recovery: "Récup", cooldown: "Retour au calme", interval: "Effort" };

function speedText(a) {
  if (FOOT_SPORTS.includes(a.sport)) return a.avg_speed ? `${F.pace(a.avg_speed)} /km` : "–";
  return a.avg_speed ? `${F.dec1(a.avg_speed * 3.6)} km/h` : "–";
}

function figure(label, value, unit = "") {
  return `<div><div class="figure-label">${F.escape(label)}</div><div class="figure-value">${F.escape(value)}${unit ? `<small>${F.escape(unit)}</small>` : ""}</div></div>`;
}

function keyFigures(a, { extra = false } = {}) {
  const out = [];
  if (a.distance_m) out.push(figure("Distance", F.dec1(a.distance_m / 1000), "km"));
  out.push(figure("Durée", F.duration(a.duration_s)));
  if (a.avg_speed) {
    out.push(FOOT_SPORTS.includes(a.sport)
      ? figure("Allure", F.pace(a.avg_speed), "/km")
      : figure("Vitesse", F.dec1(a.avg_speed * 3.6), "km/h"));
  }
  if (a.avg_hr) out.push(figure("FC moyenne", F.int(a.avg_hr), "bpm"));
  if (a.elev_gain_m) out.push(figure("D+", F.int(a.elev_gain_m), "m"));
  if (F.isNum(a.load)) out.push(figure("Charge", F.int(a.load)));
  if (extra) {
    if (a.max_hr) out.push(figure("FC max", F.int(a.max_hr), "bpm"));
    if (a.avg_cadence) out.push(figure("Cadence", F.int(a.avg_cadence), FOOT_SPORTS.includes(a.sport) ? "pas/min" : "tr/min"));
    if (F.isNum(a.te_aerobic)) out.push(figure("Effet aérobie", F.dec1(a.te_aerobic)));
    if (F.isNum(a.pct_vma)) out.push(figure("Part de VMA", F.int(a.pct_vma), "%"));
    if (a.decouplage) out.push(figure("Découplage", F.dec1(a.decouplage.derive_pct), "%"));
    if (F.isNum(a.vo2max)) out.push(figure("VO2max", F.int(a.vo2max)));
  }
  return out.join("");
}

function traceSVG(streams, p) {
  const pts = [];
  (streams.lat || []).forEach((lat, i) => {
    const lon = streams.lon?.[i];
    if (F.isNum(lat) && F.isNum(lon)) pts.push([lat, lon]);
  });
  if (pts.length < 5) return "";
  const k = Math.cos((pts[0][0] * Math.PI) / 180);
  const xs = pts.map((pt) => pt[1] * k);
  const ys = pts.map((pt) => -pt[0]);
  const minX = Math.min(...xs); const maxX = Math.max(...xs);
  const minY = Math.min(...ys); const maxY = Math.max(...ys);
  const span = Math.max(maxX - minX, maxY - minY) || 1;
  const map = (x, y) => [6 + ((x - minX) / span) * 108 + (108 - ((maxX - minX) / span) * 108) / 2,
    6 + ((y - minY) / span) * 108 + (108 - ((maxY - minY) / span) * 108) / 2];
  const path = xs.map((x, i) => map(x, ys[i])).map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const [sx, sy] = map(xs[0], ys[0]);
  const [ex, ey] = map(xs[xs.length - 1], ys[ys.length - 1]);
  return `<svg class="trace" viewBox="0 0 120 120" role="img" aria-label="Tracé de la séance">
    <path d="${path}" fill="none" stroke="${p.ink}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    <circle cx="${sx}" cy="${sy}" r="4" fill="${p.surface}" stroke="${p.ink}" stroke-width="2"/>
    <circle cx="${ex}" cy="${ey}" r="3.5" fill="${p.ink}" stroke="${p.surface}" stroke-width="1.5"/></svg>`;
}

// ------------------------------------------------------------- liste
// Colonnes de la liste. « has » : une colonne vide pour toutes les séances affichées ne s'affiche pas
// (pas de distance ni d'allure pour une liste de renfo). « renfo » : seulement si toutes sont du renfo.
const LIST_COLUMNS = [
  { head: "Date", cell: (a) => F.escape(F.dateShort(a.date)) },
  { head: "Séance", cls: "name", cell: (a) => `${F.escape(a.name || a.sport_label)} <span class="sport-tag">${F.escape(a.sport_label)}</span>` },
  { head: "Distance", num: true, has: (a) => a.distance_m > 0, cell: (a) => (a.distance_m ? `${F.dec1(a.distance_m / 1000)} km` : "–") },
  { head: "Durée", num: true, cell: (a) => F.escape(a.duree) },
  { head: "Allure / vitesse", num: true, has: (a) => a.avg_speed > 0, cell: (a) => F.escape(speedText(a)) },
  { head: "Séries", num: true, renfo: true, has: (a) => a.extra?.sets > 0, cell: (a) => F.int(a.extra?.sets) },
  { head: "Tonnage", num: true, renfo: true, has: (a) => a.extra?.volume > 0, cell: (a) => (a.extra?.volume > 0 ? `${F.int(a.extra.volume)} kg` : "–") },
  { head: "FC moy.", num: true, has: (a) => a.avg_hr > 0, cell: (a) => F.int(a.avg_hr) },
  { head: "D+", num: true, has: (a) => a.elev_gain_m > 0, cell: (a) => (a.elev_gain_m ? `${F.int(a.elev_gain_m)} m` : "–") },
  { head: "Charge", num: true, has: (a) => a.load > 0, cell: (a) => F.int(a.load) },
];

function listColumns(rows) {
  const allRenfo = rows.every((a) => a.sport === "renfo");
  return LIST_COLUMNS.filter((c) => (!c.renfo || allRenfo) && (!c.has || rows.some(c.has)));
}

export const activites = {
  title: () => "Séances",
  async render(body, p, ctx) {
    const { start, end } = ctx.period(p);
    const limit = Math.max(5, Number(p.limite) || 20);
    let offset = 0;
    let rows = [];
    const load = async () => {
      const page = await api.get("/api/activities", { start, end, sport: p.sport === "tous" ? "" : p.sport, search: p.recherche, limit, offset });
      rows = rows.concat(page);
      offset += page.length;
      draw(page.length === limit);
    };
    const draw = (more) => {
      if (!rows.length) return message(body, "Aucune séance sur cette période.");
      ctx.sub(`${rows.length}${more ? "+" : ""} séance${rows.length > 1 ? "s" : ""}`);
      body.classList.add("scroll");
      const cols = listColumns(rows);
      const td = (c, a) => {
        if (c.num) return `<td class="num">${c.cell(a)}</td>`;
        if (c.cls === "name") return `<td class="name" title="${F.escape(a.description || a.name || "")}">${c.cell(a)}</td>`;
        return `<td>${c.cell(a)}</td>`;
      };
      body.innerHTML = `<table class="table">
        <thead><tr>${cols.map((c) => `<th${c.num ? ' class="num"' : ""}>${F.escape(c.head)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((a) => `<tr class="clickable" data-id="${F.escape(a.id)}" tabindex="0">
          ${cols.map((c) => td(c, a)).join("")}</tr>`).join("")}</tbody></table>
        ${more ? `<div class="tile-foot"><span></span><button class="btn btn-ghost" data-more type="button">Afficher plus</button></div>` : ""}`;
      body.querySelectorAll("tr[data-id]").forEach((tr) => {
        const open = () => ctx.openActivity(tr.dataset.id);
        tr.addEventListener("click", open);
        tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
      });
      body.querySelector("[data-more]")?.addEventListener("click", load);
    };
    await load();
  },
};

// ------------------------------------------------------------- dernière séance
export const derniere_seance = {
  title: (p, ctx) => (p.sport && p.sport !== "tous" ? `Dernière séance (${ctx.sportLabel(p.sport).toLowerCase()})` : "Dernière séance"),
  async render(body, p, ctx) {
    const [a] = await api.get("/api/activities", { limit: 1, sport: p.sport === "tous" ? "" : p.sport });
    if (!a) return message(body, "Aucune séance pour l'instant : lance une synchro.");
    let trace = "";
    if (a.has_streams === 1) {
      try { trace = traceSVG(await api.get(`/api/activities/${encodeURIComponent(a.id)}/streams`, { max_points: 400 }), ctx.palette); } catch (e) { trace = ""; }
    }
    body.innerHTML = `<div class="act-card">
      <div style="min-width:0;display:flex;flex-direction:column">
        <h3 class="act-name">${F.escape(a.name || a.sport_label)}</h3>
        <div class="act-when">${F.escape(F.whenActivity(a.start_local))}, ${F.escape(a.sport_label.toLowerCase())}</div>
        <div class="figures">${keyFigures(a)}</div>
        ${a.description ? `<div class="act-desc">${F.escape(a.description)}</div>` : ""}
        <div style="margin-top:auto;padding-top:8px"><button class="btn btn-ghost" type="button" data-open style="margin-left:-12px">${icon("map")}Ouvrir la séance</button></div>
      </div>
      <div class="trace-box">${trace}</div>
    </div>`;
    body.querySelector("[data-open]").addEventListener("click", () => ctx.openActivity(a.id));
  },
};

// ------------------------------------------------------------- séance : résumé
export const seance_resume = {
  ownHead: true,
  title: () => "Séance",
  async render(body, p, ctx) {
    const a = await ctx.activityDetail();
    if (!a) return message(body, "Choisis une séance en haut de la vue.");
    body.innerHTML = `<div class="summary">
      <div class="summary-title">
        <h2 class="act-name" style="font-size:24px">${F.escape(a.name || a.sport_label)}</h2>
        <div class="act-when">${F.escape(F.whenActivity(a.start_local))}, ${F.escape(a.sport_label.toLowerCase())}</div>
        ${a.description ? `<div class="act-desc" title="${F.escape(a.description)}">${F.escape(a.description)}</div>` : ""}
        ${a.telechargement && a.telechargement !== "ok" ? `<div class="act-desc">Fichier FIT : ${F.escape(a.telechargement)}</div>` : ""}
      </div>
      <div class="figures">${keyFigures(a, { extra: true })}</div>
    </div>`;
  },
};

// ------------------------------------------------------------- séance : carte
const TILES = {
  osm: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }],
  ign: ["https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}", { maxZoom: 19, attribution: "© IGN, Plan IGN" }],
};

export const seance_mesures = {
  title: () => "Séance : autres mesures",
  async render(body, p, ctx) {
    const a = await ctx.activityDetail();
    if (!a) return message(body, "Choisis une séance en haut de la vue.");
    if (!a.mesures?.length) return message(body, "Pas d'autres mesures pour cette séance (dynamique de course, puissance, respiration… selon la montre et les capteurs).");
    body.classList.add("scroll");
    body.innerHTML = `<dl class="measures">${a.mesures.map((m) => `<div><dt>${F.escape(m.label)}</dt><dd>${F.escape(m.affiche)}</dd></div>`).join("")}</dl>`;
  },
};

export const seance_carte = {
  title: () => "Tracé",
  async render(body, p, ctx, tile, cleanup) {
    const s = await ctx.activityStreams();
    if (!s) return message(body, ctx.activityId ? "Pas de courbes pour cette séance." : "Choisis une séance en haut de la vue.");
    const idx = [];
    const latlngs = [];
    (s.lat || []).forEach((lat, i) => {
      if (F.isNum(lat) && F.isNum(s.lon?.[i])) { latlngs.push([lat, s.lon[i]]); idx.push(i); }
    });
    if (latlngs.length < 2) return message(body, "Pas de tracé GPS pour cette séance.");
    const P = ctx.palette;
    body.innerHTML = '<div class="map"></div>';
    const el = body.querySelector(".map");
    const map = L.map(el, { zoomControl: true, attributionControl: true, preferCanvas: true });
    const choice = TILES[ctx.settings.carte_fond];
    if (choice) L.tileLayer(choice[0], choice[1]).addTo(map);
    const line = L.polyline(latlngs, { color: P.series[0], weight: 3.5, opacity: 0.95 }).addTo(map);
    L.circleMarker(latlngs[0], { radius: 6, color: P.surface, weight: 2, fillColor: P.ink, fillOpacity: 1 }).addTo(map).bindTooltip("Départ");
    L.circleMarker(latlngs[latlngs.length - 1], { radius: 5, color: P.surface, weight: 2, fillColor: P.series[1], fillOpacity: 1 }).addTo(map).bindTooltip("Arrivée");
    const cursor = L.circleMarker(latlngs[0], { radius: 7, color: P.surface, weight: 3, fillColor: P.series[1], fillOpacity: 1, opacity: 0 }).addTo(map);
    map.fitBounds(line.getBounds(), { padding: [18, 18] });
    const onCursor = (e) => {
      const i = e.detail;
      let k = idx.findIndex((v) => v >= i);
      if (k < 0) k = idx.length - 1;
      cursor.setLatLng(latlngs[k]).setStyle({ opacity: 1, fillOpacity: 1 });
    };
    ctx.bus.addEventListener("cursor", onCursor);
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(el);
    cleanup({ dispose() { ctx.bus.removeEventListener("cursor", onCursor); observer.disconnect(); map.remove(); } });
  },
};

// ------------------------------------------------------------- séance : courbes
const CURVES = {
  hr: { label: "Fréquence cardiaque", meta: { fmt: "int", unit: "bpm" }, color: (P) => P.series[1] },
  spd: { label: "Allure", meta: { fmt: "pace" }, color: (P) => P.series[0] },
  alt: { label: "Altitude", meta: { fmt: "int", unit: "m" }, color: (P) => P.ink2, area: true },
  cad: { label: "Cadence", meta: { fmt: "int", unit: "pas/min" }, color: (P) => P.series[2] },
  pwr: { label: "Puissance", meta: { fmt: "int", unit: "W" }, color: (P) => P.series[3] },
  temp: { label: "Température", meta: { fmt: "dec1", unit: "°C" }, color: (P) => P.ink2 },
};

export const seance_courbes = {
  title: () => "Courbes",
  async render(body, p, ctx, tile, cleanup) {
    const s = await ctx.activityStreams();
    if (!s) return message(body, ctx.activityId ? "Pas de courbes pour cette séance (fichier FIT absent)." : "Choisis une séance en haut de la vue.");
    const a = await ctx.activityDetail();
    const foot = FOOT_SPORTS.includes(a?.sport);
    const keys = (p.courbes || []).filter((k) => (s[k] || []).some(F.isNum));
    if (!keys.length) return message(body, "Aucune des courbes choisies n'est disponible pour cette séance.");
    const byDistance = p.axe === "distance" && (s.dist || []).some(F.isNum);
    const xs = byDistance ? s.dist.map((d) => (F.isNum(d) ? d / 1000 : null)) : s.t.map((t) => t / 60);
    const P = ctx.palette;
    const defs = keys.map((k) => {
      const def = { ...CURVES[k] };
      if (k === "spd" && !foot) def.meta = { fmt: "dec1", unit: "km/h" };
      if (k === "spd" && !foot) def.label = "Vitesse";
      if (k === "cad" && !foot) def.meta = { fmt: "int", unit: "tr/min" };
      return def;
    });
    const dataFor = (k) => s[k].map((v, i) => {
      if (!F.isNum(v) || !F.isNum(xs[i])) return [xs[i], null];
      if (k === "spd") return [xs[i], foot ? (v < 1.4 ? null : 1000 / v) : v * 3.6];
      return [xs[i], v];
    });
    const el = (() => { body.innerHTML = '<div class="chart"></div>'; return body.querySelector(".chart"); })();
    const xLabel = (v) => (byDistance ? `${F.dec1(v)} km` : F.chrono(v * 60));
    cleanup(C.mountSized(el, (w, h) => {
      const { grids, titles } = C.gridStack(keys.length, h, { gap: 26, bottom: 26 });
      return {
        ...C.baseOption(P), grid: grids,
        title: defs.map((d, i) => C.gridTitle(P, d.label, titles[i])),
        axisPointer: { link: [{ xAxisIndex: "all" }] },
        dataZoom: [{ type: "inside", xAxisIndex: keys.map((_, i) => i), throttle: 40 }],
        tooltip: {
          ...C.tooltipBase(P),
          formatter: (items) => C.tooltipHTML(byDistance ? `${F.dec2(items[0].value[0])} km` : F.chrono(items[0].value[0] * 60),
            items.map((it) => {
              const def = defs[it.seriesIndex];
              const v = it.value[1];
              return { label: def.label, color: it.color, value: def.meta.fmt === "pace" ? (F.isNum(v) ? `${F.chrono(v)} /km` : "–") : F.value(def.meta, v) };
            })),
        },
        xAxis: keys.map((_, i) => ({
          type: "value", gridIndex: i, min: "dataMin", max: "dataMax",
          axisLine: { show: i === keys.length - 1, lineStyle: { color: P.base } }, axisTick: { show: false }, splitLine: { show: false },
          axisLabel: { show: i === keys.length - 1, color: P.muted, fontSize: 12, formatter: xLabel, hideOverlap: true },
        })),
        yAxis: defs.map((d, i) => C.valueAxis(P, d.meta, {
          gridIndex: i, splitNumber: 2, hideMax: true,
          ...(d.meta.fmt === "pace" ? C.paceRange(dataFor(keys[i]).map((pt) => pt[1])) : {}),
        })),
        series: keys.map((k, i) => ({
          type: "line", data: dataFor(k), xAxisIndex: i, yAxisIndex: i, symbol: "none", sampling: "lttb",
          lineStyle: { width: k === "alt" ? 1.5 : 1.75, color: defs[i].color(P) }, itemStyle: { color: defs[i].color(P) },
          areaStyle: defs[i].area ? { color: defs[i].color(P), opacity: 0.1 } : undefined, emphasis: { disabled: true },
        })),
      };
    }, (chart) => {
      chart.on("updateAxisPointer", (e) => {
        const info = e.axesInfo?.[0];
        if (!info) return;
        const target = info.value;
        let best = 0;
        let bestGap = Infinity;
        for (let i = 0; i < xs.length; i += 1) {
          if (!F.isNum(xs[i])) continue;
          const gap = Math.abs(xs[i] - target);
          if (gap < bestGap) { bestGap = gap; best = i; }
        }
        ctx.bus.dispatchEvent(new CustomEvent("cursor", { detail: best }));
      });
    }));
  },
};

// ------------------------------------------------------------- séance : tours
export const seance_tours = {
  title: (p) => (p.mode === "kilometres" ? "Kilomètre par kilomètre" : "Tours"),
  async render(body, p, ctx) {
    const a = await ctx.activityDetail();
    if (!a) return message(body, "Choisis une séance en haut de la vue.");
    body.classList.add("scroll");
    if (p.mode === "kilometres") {
      if (!a.splits_km?.length) return message(body, "Pas de découpage au kilomètre pour cette séance.");
      body.innerHTML = `<table class="table"><thead><tr><th>Km</th><th class="num">Temps</th><th class="num">Allure</th><th class="num">FC moy.</th><th class="num">D+</th></tr></thead>
        <tbody>${a.splits_km.map((k) => `<tr><td>${F.dec1(k.km)}</td><td class="num">${F.chrono(k.temps_s)}</td><td class="num">${F.escape(k.allure)}</td><td class="num">${F.int(k.fc_moy)}</td><td class="num">${F.isNum(k.d_plus_m) ? `${k.d_plus_m} m` : "–"}</td></tr>`).join("")}</tbody></table>`;
      return;
    }
    if (!a.tours?.length) return message(body, "Pas de tours pour cette séance (fichier FIT absent).");
    const vma = Number(ctx.settings.vma_kmh) || 16;
    const fast = (vma * (Number(ctx.settings.fractions_seuil_pct_vma) || 85)) / 100 / 3.6;
    const foot = FOOT_SPORTS.includes(a.sport);
    ctx.sub(`${a.tours.length} tours${foot ? `, en gras ceux plus rapides que ${F.pace(fast)} /km` : ""}`);
    body.innerHTML = `<table class="table"><thead><tr><th>N°</th><th>Type</th><th class="num">Durée</th><th class="num">Distance</th><th class="num">${foot ? "Allure" : "Vitesse"}</th><th class="num">FC moy.</th><th class="num">FC max</th><th class="num">Cadence</th><th class="num">D+</th></tr></thead>
      <tbody>${a.tours.map((t) => `<tr class="${foot && t.avg_speed >= fast && t.intensity !== "rest" ? "is-fast" : ""}">
        <td>${t.idx + 1}</td><td>${F.escape(INTENSITY[t.intensity] || "Tour")}</td>
        <td class="num">${F.chrono(t.duration_s)}</td><td class="num">${t.distance_m ? `${F.int(t.distance_m)} m` : "–"}</td>
        <td class="num">${foot ? (t.avg_speed ? `${F.pace(t.avg_speed)} /km` : "–") : (t.avg_speed ? `${F.dec1(t.avg_speed * 3.6)} km/h` : "–")}</td>
        <td class="num">${F.int(t.avg_hr)}</td><td class="num">${F.int(t.max_hr)}</td><td class="num">${F.int(t.avg_cadence)}</td>
        <td class="num">${F.isNum(t.elev_gain_m) ? `${F.int(t.elev_gain_m)} m` : "–"}</td></tr>`).join("")}</tbody></table>`;
  },
};
