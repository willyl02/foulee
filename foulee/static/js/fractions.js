// Analyse d'une séance « fraction par fraction » (façon intervals.icu) : au-dessus des courbes d'allure et de
// FC, une colonne par tour, aussi large que sa durée, avec son temps, son allure, sa FC moyenne, la zone de
// cette FC et la part du tour passée dans cette zone. Même dessin dans la vue « Séance » (données locales) et
// dans les pages coach / élève (tours et courbe allégée partagés par le relais).
//
//   analysisHTML(segments, curve, { running })  → le HTML (ou "" si rien à montrer)
//   wireAnalysis(root)                          → le curseur au survol (heure, allure, FC)

import * as F from "./format.js";

const SPEED_MIN = 1.4;  // en dessous (≈ 12 min/km), à pied : arrêt ou marche, pas d'allure

/** Les tours, quel que soit leur nom de champ (vue Séance : analyse ; relais : tours partagés). */
export function normalizeSegments(list) {
  let clock = 0;
  return (list || []).map((s) => {
    const start = F.isNum(s.debut_s) ? s.debut_s : clock;
    const end = F.isNum(s.fin_s) ? s.fin_s : start + (Number(s.duree_s) || 0);
    clock = end;
    const speed = F.isNum(s.vitesse) ? s.vitesse : F.isNum(s.vitesse_kmh) ? s.vitesse_kmh / 3.6 : null;
    return { start, end, duration: Number(s.duree_s) || end - start, speed, hr: s.fc_moy, zone: s.zone,
             paceText: s.allure ? String(s.allure).replace(/\s+/g, "") : null,
             pct: s.zone_pct, rest: ["rest", "recovery"].includes(s.intensite), distance: s.distance_m };
  }).filter((s) => s.end > s.start);
}

/** Durée courte à la façon d'intervals.icu : « 33m54s », « 82s », « 1h05m ». */
function short(seconds) {
  const s = Math.round(seconds);
  if (s < 100) return `${s}s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h${String(m).padStart(2, "0")}m` : `${m}m${String(s % 60).padStart(2, "0")}s`;
}

function speedText(speed, running) {
  if (!F.isNum(speed) || speed <= 0) return "–";
  return running ? `${F.pace(speed)}/km` : `${F.dec1(speed * 3.6)} km/h`;
}

/** Courbe → points SVG (x en 0…1000 sur la durée, y en 0…h), avec trous là où la valeur manque. */
function path(ts, values, t0, t1, lo, hi, h) {
  const parts = [];
  let open = false;
  for (let i = 0; i < ts.length; i += 1) {
    const v = values[i];
    if (!F.isNum(v) || !F.isNum(ts[i])) { open = false; continue; }
    const x = ((ts[i] - t0) / (t1 - t0)) * 1000;
    const r = (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo || 1);
    const y = h - r * h * 0.9 - 2;
    parts.push(`${open ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`);
    open = true;
  }
  return parts.join("");
}

function quantile(values, q) {
  const sorted = values.filter(F.isNum).sort((a, b) => a - b);
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];
}

/**
 * segments : tours (voir normalizeSegments) ; curve : {t, v (m/s), fc} ; running : allure plutôt que vitesse.
 * Sans courbe, les colonnes seules (et les allures des tours en marches d'escalier).
 */
export function analysisHTML(rawSegments, curve, { running = true } = {}) {
  const segs = normalizeSegments(rawSegments);
  if (segs.length < 2) return "";
  const t0 = segs[0].start;
  const t1 = segs[segs.length - 1].end;
  if (!(t1 > t0)) return "";
  const pos = (t) => ((t - t0) / (t1 - t0)) * 100;

  // ---- colonnes
  const cols = segs.map((s, i) => {
    const left = pos(s.start);
    const width = Math.max(0.2, pos(s.end) - left);
    const tip = [`Tour ${i + 1}`, F.chrono(s.duration), speedText(s.speed, running), F.isNum(s.hr) ? `${F.int(s.hr)} bpm` : "",
      s.zone ? `Z${s.zone}${F.isNum(s.pct) ? ` (${s.pct} % du tour)` : ""}` : ""].filter(Boolean).join(" · ");
    return `<div class="an-col${s.rest ? " is-rest" : ""}${s.zone ? ` an-z${s.zone}` : ""}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%" title="${F.escape(tip)}">
      <span class="an-t">${short(s.duration)}</span>
      <span class="an-v">${F.escape(running && s.paceText ? s.paceText : speedText(s.speed, running))}</span>
      <span class="an-fc">${F.isNum(s.hr) ? `${F.int(s.hr)}bpm` : "–"}</span>
      <span class="an-zone">${s.zone ? `Z${s.zone}` : "–"}</span>
      <span class="an-pct">${F.isNum(s.pct) ? `${s.pct}%` : ""}</span>
    </div>`;
  }).join("");

  // ---- courbes (ou, sans courbe, l'allure et la FC des tours en escalier)
  let ts; let vs; let hs;
  if (curve?.t?.length > 1) {
    ts = curve.t; vs = curve.v || []; hs = curve.fc || [];
  } else {
    ts = []; vs = []; hs = [];
    segs.forEach((s) => { ts.push(s.start, s.end); vs.push(s.speed, s.speed); hs.push(s.hr, s.hr); });
  }
  const speeds = vs.map((v) => (F.isNum(v) && (!running || v >= SPEED_MIN) ? v : null));
  const H = 120;
  const vLo = quantile(speeds, 0.02); const vHi = quantile(speeds, 0.995);
  const hLo = quantile(hs, 0.02); const hHi = quantile(hs, 0.995);
  const lines = [];
  const bounds = segs.slice(1).map((s) => `<line x1="${(pos(s.start) * 10).toFixed(1)}" x2="${(pos(s.start) * 10).toFixed(1)}" y1="0" y2="${H}" class="an-sep"/>`).join("");
  const shade = segs.map((s) => (!s.rest && s.zone >= 3 ? `<rect x="${(pos(s.start) * 10).toFixed(1)}" y="0" width="${((pos(s.end) - pos(s.start)) * 10).toFixed(1)}" height="${H}" class="an-shade an-z${s.zone}"/>` : "")).join("");
  if (F.isNum(vLo) && F.isNum(vHi) && vHi > vLo) {
    // Allure : plus rapide = plus haut (comme intervals.icu)
    const d = path(ts, speeds, t0, t1, vLo, vHi, H);
    lines.push(`<div class="an-plot"><span class="an-axis"><span>${F.escape(speedText(vHi, running))}</span><span>${F.escape(speedText(vLo, running))}</span></span>
      <svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none">${shade}${bounds}<path d="${d}" class="an-line an-line-v"/></svg></div>`);
  }
  if (F.isNum(hLo) && F.isNum(hHi) && hHi > hLo) {
    const d = path(ts, hs, t0, t1, hLo, hHi, H);
    lines.push(`<div class="an-plot"><span class="an-axis"><span>${F.int(hHi)} bpm</span><span>${F.int(hLo)} bpm</span></span>
      <svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none">${shade}${bounds}<path d="${d}" class="an-line an-line-fc"/></svg></div>`);
  }
  const span = t1 - t0;
  const step = [300, 600, 900, 1200, 1800, 3600].find((s) => span / s <= 8) || 3600;
  const ticks = [];
  for (let t = step; t < span; t += step) ticks.push(`<span style="left:${((t / span) * 100).toFixed(2)}%">${F.chrono(t)}</span>`);
  const data = encodeURIComponent(JSON.stringify({ t0, t1, ts, vs: speeds, hs, running }));
  return `<div class="analyse" data-analyse="${data}">
    <div class="an-band">${cols}</div>
    ${lines.join("")}
    <div class="an-ticks">${ticks.join("")}</div>
    <div class="an-cursor" hidden></div><div class="an-tip" hidden></div>
  </div>`;
}

/** Curseur vertical au survol : le temps, l'allure et la FC à cet instant. */
export function wireAnalysis(root) {
  root.querySelectorAll(".analyse[data-analyse]").forEach((box) => {
    let data;
    try { data = JSON.parse(decodeURIComponent(box.dataset.analyse)); } catch (e) { return; }
    const cursor = box.querySelector(".an-cursor");
    const tip = box.querySelector(".an-tip");
    const plots = box.querySelectorAll(".an-plot svg");
    if (!plots.length) return;
    const move = (ev) => {
      const rect = plots[0].getBoundingClientRect();
      const r = (ev.clientX - rect.left) / rect.width;
      if (r < 0 || r > 1) { cursor.hidden = true; tip.hidden = true; return; }
      const t = data.t0 + r * (data.t1 - data.t0);
      let best = 0;
      let gap = Infinity;
      data.ts.forEach((x, i) => { const g = Math.abs(x - t); if (g < gap) { gap = g; best = i; } });
      const host = box.getBoundingClientRect();
      const x = rect.left - host.left + r * rect.width;
      cursor.hidden = false;
      cursor.style.left = `${x}px`;
      tip.hidden = false;
      tip.innerHTML = `<b>${F.chrono(t - data.t0)}</b> · <span class="an-v">${F.escape(speedText(data.vs[best], data.running))}</span> · <span class="an-fc">${F.isNum(data.hs[best]) ? `${F.int(data.hs[best])} bpm` : "–"}</span>`;
      tip.style.left = `${Math.min(Math.max(x, 70), host.width - 70)}px`;
    };
    box.addEventListener("mousemove", move);
    box.addEventListener("mouseleave", () => { cursor.hidden = true; tip.hidden = true; });
    // Colonnes trop étroites pour leur texte : la zone seule (le reste au survol)
    const fit = () => box.querySelectorAll(".an-col").forEach((col) => {
      const w = col.getBoundingClientRect().width;
      col.classList.toggle("is-narrow", w < 54);
      col.classList.toggle("is-thin", w < 18);
    });
    fit();
    if (window.ResizeObserver) new ResizeObserver(fit).observe(box);
  });
}
