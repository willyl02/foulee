// Analyse d'une séance « fraction par fraction » (façon intervals.icu) : au-dessus des courbes d'allure et de
// FC, une colonne par tour, aussi large que sa durée, avec son temps, son allure, sa FC moyenne, la zone de
// cette FC et la part du tour passée dans cette zone. Même dessin dans la vue « Séance » (données locales) et
// dans les pages coach / élève (tours et courbe allégée partagés par le relais).
//
//   analysisHTML(segments, curve, { running })  → le HTML (ou "" si rien à montrer)
//   wireAnalysis(root)                          → le curseur au survol (heure, allure, FC) et le zoom
//
// Zoom (boîte à outils en haut à droite, comme sur les autres graphiques) : glisser sur les courbes pour zoomer sur
// une plage de temps, Ctrl + molette pour zoomer, Maj + molette (ou glisser à deux doigts) pour se déplacer, boutons
// ↔ et ↕ pour zoomer en largeur ou en hauteur, double-clic ou ⟲ pour revenir à la séance entière. En largeur, l'axe
// vertical s'ajuste à la plage affichée.

import * as F from "./format.js";
import { icon } from "./icons.js";
import { scrollbarHTML, wireScrollbar } from "./charts.js";

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

/** Tours coupés à la fenêtre [a, b] et positions en % de la fenêtre. */
function windowed(segs, a, b) {
  const pos = (t) => ((t - a) / (b - a)) * 100;
  return segs.map((s, i) => ({ s, i, left: pos(Math.max(a, s.start)), right: pos(Math.min(b, s.end)) }))
    .filter((x) => x.right > x.left);
}

/** Les morceaux qui changent avec le zoom : colonnes, courbes, graduations. view = {a, b, ky}. */
function parts(model, view) {
  const { segs, ts, vs, hs, running, t0 } = model;
  const { a, b, ky } = view;
  const H = 120;
  const shown = windowed(segs, a, b);
  const cols = shown.map(({ s, i, left, right }) => {
    const width = Math.max(0.2, right - left);
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
  // l'échelle verticale suit la plage affichée, puis le zoom vertical (autour du milieu)
  const inside = (arr) => arr.filter((v, k) => ts[k] >= a && ts[k] <= b);
  const range = (arr, unit) => {
    let lo = quantile(inside(arr), 0.02); let hi = quantile(inside(arr), 0.995);
    if (!F.isNum(lo) || !F.isNum(hi)) return null;
    if (hi - lo < unit) { lo -= unit / 2; hi += unit / 2; }
    const mid = (lo + hi) / 2; const half = (hi - lo) / 2 / ky;
    return [mid - half, mid + half];
  };
  const bounds = shown.slice(1).map(({ left }) => `<line x1="${(left * 10).toFixed(1)}" x2="${(left * 10).toFixed(1)}" y1="0" y2="${H}" class="an-sep"/>`).join("");
  const shade = shown.map(({ s, left, right }) => (!s.rest && s.zone >= 3 ? `<rect x="${(left * 10).toFixed(1)}" y="0" width="${((right - left) * 10).toFixed(1)}" height="${H}" class="an-shade an-z${s.zone}"/>` : "")).join("");
  const lines = [];
  const v = range(vs, 0.05);
  if (v) {
    // Allure : plus rapide = plus haut (comme intervals.icu)
    const d = path(ts, vs, a, b, v[0], v[1], H);
    lines.push(`<div class="an-plot"><span class="an-axis"><span>${F.escape(speedText(v[1], running))}</span><span>${F.escape(speedText(v[0], running))}</span></span>
      <svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none">${shade}${bounds}<path d="${d}" class="an-line an-line-v"/></svg></div>`);
  }
  const h = range(hs, 4);
  if (h) {
    const d = path(ts, hs, a, b, h[0], h[1], H);
    lines.push(`<div class="an-plot"><span class="an-axis"><span>${F.int(h[1])} bpm</span><span>${F.int(h[0])} bpm</span></span>
      <svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none">${shade}${bounds}<path d="${d}" class="an-line an-line-fc"/></svg></div>`);
  }
  const span = b - a;
  const step = [10, 15, 30, 60, 120, 300, 600, 900, 1200, 1800, 3600].find((st) => span / st <= 8) || 3600;
  const ticks = [];
  for (let t = Math.ceil((a - t0) / step) * step + t0; t < b; t += step) {
    if (t > a) ticks.push(`<span style="left:${(((t - a) / span) * 100).toFixed(2)}%">${F.chrono(t - t0)}</span>`);
  }
  return { cols, plots: lines.join(""), ticks: ticks.join("") };
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
  // ---- courbes (ou, sans courbe, l'allure et la FC des tours en escalier)
  let ts; let vs; let hs;
  if (curve?.t?.length > 1) {
    ts = curve.t; vs = curve.v || []; hs = curve.fc || [];
  } else {
    ts = []; vs = []; hs = [];
    segs.forEach((s) => { ts.push(s.start, s.end); vs.push(s.speed, s.speed); hs.push(s.hr, s.hr); });
  }
  const speeds = vs.map((v) => (F.isNum(v) && (!running || v >= SPEED_MIN) ? v : null));
  const model = { segs, ts, vs: speeds, hs, running, t0, t1 };
  const p = parts(model, { a: t0, b: t1, ky: 1 });
  const data = encodeURIComponent(JSON.stringify(model));
  const tool = (key, name, title, extra = "") => `<button class="zb-btn" type="button" data-zoom="${key}" title="${title}" aria-label="${title}">${icon(name)}${extra}</button>`;
  return `<div class="analyse" data-analyse="${data}">
    <div class="zoombar" role="toolbar" aria-label="Zoom du graphique">
      <span class="zb-group" title="En largeur (le temps)">${icon("arrowsh")}${tool("x+", "plus", "Zoomer en largeur")}${tool("x-", "minus", "Dézoomer en largeur")}</span>
      <span class="zb-group" title="En hauteur (allure et FC)">${icon("arrowsv")}${tool("y+", "plus", "Zoomer en hauteur")}${tool("y-", "minus", "Dézoomer en hauteur")}</span>
      ${tool("area", "search", "Zoomer sur une autre plage (trace-la sur les courbes)")}
      ${tool("reset", "reset", "Zoom initial (double-clic)")}
      <span class="zb-help" title="Glisse sur les courbes pour zoomer sur une plage. Une fois zoomé, la main : glisse pour te déplacer, ou fais glisser la barre sous le graphique ; pour choisir une autre plage, la loupe (ou Maj + glisser). Ctrl + molette : zoomer ; Maj + molette : se déplacer. Double-clic : zoom initial.">?</span>
    </div>
    <div class="an-band">${p.cols}</div>
    <div class="an-plots">${p.plots}</div>
    <div class="an-ticks">${p.ticks}</div>
    ${scrollbarHTML()}
    <div class="an-cursor" hidden></div><div class="an-tip" hidden></div><div class="an-brush" hidden></div>
  </div>`;
}

/** Curseur vertical au survol (temps, allure, FC) et zoom. */
export function wireAnalysis(root) {
  root.querySelectorAll(".analyse[data-analyse]").forEach((box) => {
    if (box.dataset.wired) return;
    box.dataset.wired = "1";
    let data;
    try { data = JSON.parse(decodeURIComponent(box.dataset.analyse)); } catch (e) { return; }
    const full = { a: data.t0, b: data.t1, ky: 1 };
    let view = { ...full };
    const cursor = box.querySelector(".an-cursor");
    const tip = box.querySelector(".an-tip");
    const brush = box.querySelector(".an-brush");
    const minSpan = Math.min(30, (data.t1 - data.t0) / 2);
    const plotRect = () => (box.querySelector(".an-plot svg") || box.querySelector(".an-band")).getBoundingClientRect();
    const zoomed = () => view.a > full.a || view.b < full.b || view.ky !== 1;
    const zoomedX = () => view.a > full.a || view.b < full.b;
    let area = false; // loupe armée : le prochain glisser choisit une plage, même zoomé
    const setArea = (on) => {
      area = on;
      box.querySelector('[data-zoom="area"]')?.classList.toggle("is-on", on);
      box.classList.toggle("is-area", on);
    };
    let scroll = () => {};
    const draw = () => {
      const p = parts(data, view);
      box.querySelector(".an-band").innerHTML = p.cols;
      box.querySelector(".an-plots").innerHTML = p.plots;
      box.querySelector(".an-ticks").innerHTML = p.ticks;
      box.classList.toggle("is-zoomed", zoomed());
      // zoomé en largeur : la main (glisser déplace la vue) et la barre de défilement
      box.classList.toggle("can-pan", zoomedX());
      scroll();
      fit();
    };
    // une seule mise à jour par image quand on glisse (les courbes sont recalculées à chaque fois)
    let pending = null;
    const later = (fn) => {
      const first = !pending;
      pending = fn;
      if (first) requestAnimationFrame(() => { const run = pending; pending = null; run(); });
    };
    const setX = (a, b) => {
      let span = Math.max(minSpan, Math.min(full.b - full.a, b - a));
      let lo = Math.max(full.a, Math.min(a, full.b - span));
      if (b - a < minSpan) lo = Math.max(full.a, Math.min((a + b) / 2 - span / 2, full.b - span));
      span = Math.min(span, full.b - lo);
      view = { ...view, a: lo, b: lo + span };
      draw();
    };
    const zoomX = (factor, at = (view.a + view.b) / 2) => {
      const span = (view.b - view.a) / factor;
      const r = (at - view.a) / (view.b - view.a);
      setX(at - r * span, at - r * span + span);
    };
    const timeAt = (clientX) => {
      const rect = plotRect();
      const r = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      return view.a + r * (view.b - view.a);
    };
    const span = () => full.b - full.a;
    scroll = wireScrollbar(box.querySelector(".zscroll"), {
      get: () => ({ start: (view.a - full.a) / span(), end: (view.b - full.a) / span() }),
      move: (start) => { const w = view.b - view.a; const a = full.a + start * span(); later(() => setX(a, a + w)); },
    });
    box.querySelectorAll("[data-zoom]").forEach((btn) => btn.addEventListener("click", () => {
      const k = btn.dataset.zoom;
      if (k === "x+") zoomX(2);
      else if (k === "x-") zoomX(0.5);
      else if (k === "y+") { view = { ...view, ky: Math.min(8, view.ky * 1.5) }; draw(); }
      else if (k === "y-") { view = { ...view, ky: Math.max(0.5, view.ky / 1.5) }; draw(); }
      else if (k === "area") setArea(!area);
      else { view = { ...full }; setArea(false); draw(); }
    }));
    box.addEventListener("dblclick", (ev) => {
      if (ev.target.closest(".zoombar, .zscroll")) return;
      view = { ...full };
      setArea(false);
      draw();
    });
    box.addEventListener("wheel", (ev) => {
      if (ev.ctrlKey || ev.metaKey) {
        ev.preventDefault();
        zoomX(ev.deltaY < 0 ? 1.25 : 0.8, timeAt(ev.clientX));
      } else if ((ev.shiftKey || Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) && zoomed()) {
        ev.preventDefault();
        const shift = ((ev.shiftKey ? ev.deltaY : ev.deltaX) / plotRect().width) * (view.b - view.a);
        setX(view.a + shift, view.b + shift);
      }
    }, { passive: false });
    // glisser sur les courbes : choisir la plage à agrandir ; une fois zoomé en largeur, déplacer la vue (la main),
    // sauf loupe armée ou Maj enfoncée. Au doigt, seul le déplacement (zoomé) : sinon le glisser fait défiler la page
    let drag = null;
    box.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0 || !ev.target.closest(".an-plots")) return;
      const pan = zoomedX() && !area && !ev.shiftKey;
      if (ev.pointerType === "touch" && !pan) return;
      drag = pan ? { pan: true, x: ev.clientX, a: view.a, b: view.b } : { x: ev.clientX, t: timeAt(ev.clientX) };
      box.classList.toggle("is-panning", pan);
      box.setPointerCapture(ev.pointerId);
    });
    box.addEventListener("pointerup", (ev) => {
      if (!drag) return;
      const done = drag;
      drag = null;
      box.classList.remove("is-panning");
      if (done.pan) return;
      const moved = Math.abs(ev.clientX - done.x);
      const t = timeAt(ev.clientX);
      brush.hidden = true;
      if (moved > 6) { setArea(false); setX(Math.min(done.t, t), Math.max(done.t, t)); }
    });
    box.addEventListener("pointercancel", () => { drag = null; brush.hidden = true; box.classList.remove("is-panning"); });
    const move = (ev) => {
      const rect = plotRect();
      const host = box.getBoundingClientRect();
      if (drag?.pan) {
        const shift = -((ev.clientX - drag.x) / rect.width) * (drag.b - drag.a);
        const { a, b } = drag;
        later(() => setX(a + shift, b + shift));
      } else if (drag) {
        const x1 = Math.min(Math.max(drag.x, rect.left), rect.right) - host.left;
        const x2 = Math.min(Math.max(ev.clientX, rect.left), rect.right) - host.left;
        brush.hidden = false;
        brush.style.left = `${Math.min(x1, x2)}px`;
        brush.style.width = `${Math.abs(x2 - x1)}px`;
      }
      const r = (ev.clientX - rect.left) / rect.width;
      if (r < 0 || r > 1 || ev.target.closest(".zoombar")) { cursor.hidden = true; tip.hidden = true; return; }
      const t = view.a + r * (view.b - view.a);
      // le point le plus proche (les temps sont croissants : recherche par dichotomie)
      let lo = 0; let hi = data.ts.length - 1;
      while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (data.ts[mid] < t) lo = mid; else hi = mid; }
      const best = Math.abs(data.ts[hi] - t) < Math.abs(data.ts[lo] - t) ? hi : lo;
      const x = rect.left - host.left + r * rect.width;
      cursor.hidden = false;
      cursor.style.left = `${x}px`;
      tip.hidden = false;
      tip.innerHTML = `<b>${F.chrono(t - data.t0)}</b> · <span class="an-v">${F.escape(speedText(data.vs[best], data.running))}</span> · <span class="an-fc">${F.isNum(data.hs[best]) ? `${F.int(data.hs[best])} bpm` : "–"}</span>`;
      tip.style.left = `${Math.min(Math.max(x, 70), host.width - 70)}px`;
    };
    box.addEventListener("pointermove", move);
    box.addEventListener("pointerleave", () => { cursor.hidden = true; tip.hidden = true; });
    // Colonnes trop étroites pour leur texte : la zone seule (le reste au survol)
    function fit() {
      box.querySelectorAll(".an-col").forEach((col) => {
        const w = col.getBoundingClientRect().width;
        col.classList.toggle("is-narrow", w < 54);
        col.classList.toggle("is-thin", w < 18);
      });
    }
    fit();
    if (window.ResizeObserver) new ResizeObserver(fit).observe(box);
  });
}
