// Carte du corps (face et dos) : chaque groupe musculaire se colore selon le nombre de séries qu'il a reçues.
// Dessin propre à Foulée : une moitié du corps est décrite, l'autre en est le reflet.
import * as F from "./format.js";

// Formes de la moitié droite de l'image (x ≥ 100), repère 200 × 440. « m » : groupe musculaire, sinon neutre.
const HALF_FRONT = [
  { m: "trapezes", d: "M108,60 C116,66 128,70 140,73 C132,76 122,78 112,78 C109,73 108,66 108,60 Z" },
  { m: "epaules", d: "M140,73 C152,74 162,84 163,98 C164,108 161,118 157,124 C153,116 147,106 139,100 C134,96 131,88 132,81 C134,77 137,74 140,73 Z" },
  { m: "pectoraux", d: "M101,80 C112,78 126,79 136,84 C138,94 137,104 132,111 C124,118 110,120 101,117 Z" },
  { m: "biceps", d: "M157,128 C162,136 164,148 163,160 C162,168 158,173 153,173 C148,165 145,152 145,140 C147,131 152,127 157,128 Z" },
  { m: "avant_bras", d: "M153,178 C160,178 166,186 168,198 C170,214 168,232 164,246 L152,246 C148,232 145,214 146,198 C147,188 149,180 153,178 Z" },
  { d: "M152,250 L164,250 C168,258 168,268 163,276 C158,280 152,276 150,268 C149,262 150,255 152,250 Z" },
  { m: "abdos", d: "M102,124 L116,122 C118,129 118,136 117,142 L102,143 Z" },
  { m: "abdos", d: "M102,147 L117,146 C118,153 118,160 117,166 L102,167 Z" },
  { m: "abdos", d: "M102,171 L117,170 C118,177 118,184 116,190 L102,191 Z" },
  { m: "abdos", d: "M102,195 L116,194 C115,206 111,218 102,228 Z" },
  { m: "obliques", d: "M121,121 C130,124 136,132 137,144 C138,160 136,176 132,190 C127,200 122,206 119,208 C121,190 122,170 122,150 C122,138 121,128 121,121 Z" },
  { m: "abducteurs", d: "M119,213 C126,207 133,201 138,196 C141,206 142,216 140,226 C133,224 124,226 117,231 C116,224 117,218 119,213 Z" },
  { m: "quadriceps", d: "M108,236 C118,228 132,226 141,232 C145,248 146,268 143,288 C140,304 134,316 127,322 C121,324 115,322 111,314 C107,294 105,272 106,254 C106,246 107,240 108,236 Z" },
  { m: "adducteurs", d: "M101,238 C104,236 107,238 107,244 C106,260 107,278 109,296 C105,298 102,290 101,280 Z" },
  { d: "M113,326 C119,322 129,322 133,328 C135,335 132,342 126,344 C120,345 114,341 113,334 Z" },
  { d: "M115,350 C122,346 132,347 136,354 C139,374 137,396 133,414 L121,414 C117,396 114,374 115,350 Z" },
  { d: "M119,420 L134,420 C139,425 141,431 137,434 L117,434 C115,429 116,424 119,420 Z" },
];
const HALF_BACK = [
  { m: "trapezes", d: "M100,52 C104,56 108,60 110,64 C120,70 132,74 142,76 C134,82 124,92 116,104 C110,114 104,126 100,134 Z" },
  { m: "epaules", d: "M142,77 C153,78 162,87 163,100 C164,110 161,119 157,124 C153,116 147,106 140,100 C135,96 132,90 133,84 C135,80 138,78 142,77 Z" },
  { m: "dorsaux", d: "M116,108 C124,98 134,90 141,90 C145,104 144,120 140,136 C135,154 126,170 114,184 C110,166 110,140 112,124 C113,116 114,111 116,108 Z" },
  { m: "lombaires", d: "M102,150 C106,146 110,148 112,154 C113,170 113,186 112,200 C108,204 104,204 102,202 Z" },
  { m: "obliques", d: "M116,190 C124,184 132,178 138,172 C141,186 140,200 136,210 C128,208 121,207 114,206 C114,200 115,195 116,190 Z" },
  { m: "triceps", d: "M157,128 C162,136 164,148 163,160 C162,168 158,173 153,173 C148,165 145,152 145,140 C147,131 152,127 157,128 Z" },
  { m: "avant_bras", d: "M153,178 C160,178 166,186 168,198 C170,214 168,232 164,246 L152,246 C148,232 145,214 146,198 C147,188 149,180 153,178 Z" },
  { d: "M152,250 L164,250 C168,258 168,268 163,276 C158,280 152,276 150,268 C149,262 150,255 152,250 Z" },
  { m: "abducteurs", d: "M118,213 C128,210 137,214 140,224 C141,232 140,238 137,244 C132,238 125,234 117,232 C116,225 116,218 118,213 Z" },
  { m: "fessiers", d: "M101,216 C106,214 111,216 114,223 C116,229 119,234 124,237 C131,240 136,246 137,254 C139,265 136,276 129,282 C121,288 110,288 101,285 Z" },
  { m: "ischios", d: "M106,292 C116,288 130,288 140,294 C143,308 142,322 137,332 C129,337 117,337 110,331 C106,318 104,304 106,292 Z" },
  { d: "M112,339 C120,343 130,343 136,339 C136,343 134,346 130,347 C124,348 117,347 112,344 Z" },
  { m: "mollets", d: "M114,351 C122,345 133,347 138,356 C142,371 140,387 134,399 C129,405 122,405 118,399 C112,387 111,369 114,351 Z" },
  { d: "M119,403 L131,403 C132,411 133,417 134,423 L118,423 C119,417 119,410 119,403 Z" },
  { d: "M117,425 L135,425 C138,427 139,431 136,434 L116,434 C114,431 115,428 117,425 Z" },
];
const HEAD = '<ellipse cx="100" cy="32" rx="17" ry="21"/>';
const NECK = '<path d="M90,48 C91,56 90,62 88,66 L112,66 C110,62 109,56 110,48 Z"/>';

/** Niveau 0 (pas travaillé) à 4 (le plus travaillé de la carte). */
function level(value, max) {
  if (!(value > 0) || !(max > 0)) return 0;
  return Math.min(4, Math.max(1, Math.ceil((value / max) * 4)));
}

function half(shapes, scores, max, labels) {
  return shapes.map((s) => {
    if (!s.m) return `<path class="bm-off" d="${s.d}"/>`;
    const v = scores[s.m] || 0;
    const tip = `${labels[s.m] || s.m} : ${v ? `${F.dec1(v).replace(/,0$/, "")} série${v >= 2 ? "s" : ""}` : "pas travaillé"}`;
    return `<path class="bm-m bm-l${level(v, max)}" data-muscle="${s.m}" d="${s.d}"><title>${F.escape(tip)}</title></path>`;
  }).join("");
}

function figure(shapes, scores, max, labels, caption) {
  const body = half(shapes, scores, max, labels);
  return `<figure class="bm-fig">
      <svg viewBox="0 6 200 432" aria-hidden="true" focusable="false">
        <g class="bm-neutral">${HEAD}${NECK}</g>
        <g>${body}</g>
        <g transform="matrix(-1 0 0 1 200 0)">${body}</g>
      </svg>
      <figcaption>${F.escape(caption)}</figcaption>
    </figure>`;
}

/**
 * Carte face + dos. scores : { muscle: séries }, labels : { muscle: libellé }.
 * Le texte alternatif liste les muscles travaillés, du plus au moins sollicité.
 */
export function bodyMap(scores = {}, labels = {}) {
  const max = Math.max(0, ...Object.values(scores));
  const worked = Object.entries(scores).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const alt = worked.length
    ? `Muscles travaillés : ${worked.map(([m, v]) => `${labels[m] || m} (${F.dec1(v).replace(/,0$/, "")} séries)`).join(", ")}.`
    : "Aucun muscle travaillé sur cette période.";
  return `<div class="bodymap" role="img" aria-label="${F.escape(alt)}">
      ${figure(HALF_FRONT, scores, max, labels, "Face")}
      ${figure(HALF_BACK, scores, max, labels, "Dos")}
    </div>`;
}

/** Légende des niveaux de couleur. */
export function legend() {
  return `<div class="bm-legend" aria-hidden="true"><span>Peu</span>${[1, 2, 3, 4].map((l) => `<i class="bm-l${l}"></i>`).join("")}<span>Beaucoup</span></div>`;
}
