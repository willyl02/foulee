// Esquisse d'une séance prévue : une barre par étape (échauffement, chaque fraction, chaque récup, retour au
// calme), aussi large que sa durée et aussi haute que son intensité, aux couleurs des allures VMA du club.
// Pour le calendrier (cases du mois, détail du jour) et les pages coach / élève.

const COLORS = [  // [jusqu'à ce % de VMA, couleur] : celles du tableau des allures du club
  [70, "var(--vb-ef)"], [80, "var(--vb-es)"], [88, "var(--vb-seuil)"], [95, "var(--vb-pa)"], [Infinity, "var(--vb-vma)"],
];
const ZONE_PCT = { 1: 62, 2: 70, 3: 82, 4: 90, 5: 100 };
const GENRE_PCT = { echauffement: 65, calme: 60, corps: 70, libre: 70 };

/** Les étapes d'une séance : [{minutes, pct, rest}]. Les blocs à la distance prennent leur durée à l'allure
 * visée (VMA de l'élève, ou 15 km/h) ; un bloc « libre » (touche Lap) compte 1 min 30. */
export function steps(blocs, vma) {
  const out = [];
  const speedFor = (pct) => ((vma || 15) * (pct || 70)) / 100;  // km/h
  for (const b of blocs || []) {
    const pct = b.pct_vma || (b.zone_fc ? ZONE_PCT[b.zone_fc] : GENRE_PCT[b.genre] || 70);
    let minutes = b.duree_min || 0;
    if (!minutes && b.distance_m) minutes = (b.distance_m / 1000 / speedFor(pct)) * 60;
    if (!minutes) minutes = b.libre ? 1.5 : 0;
    if (!minutes) continue;
    const reps = Math.max(1, Math.min(50, b.repetitions || 1));
    const rest = b.recup_min || (reps > 1 && (b.recup_libre || b.recup_texte) ? 1.5 : 0);
    for (let i = 0; i < reps; i += 1) {
      out.push({ minutes, pct, rest: false });
      if (rest && i < reps - 1) out.push({ minutes: rest, pct: 55, rest: true });
    }
  }
  return out;
}

export function totalMinutes(blocs, vma) {
  return steps(blocs, vma).reduce((t, s) => t + s.minutes, 0);
}

/** Le SVG (largeur 100 %, hauteur en px) ; approx : séance type devinée du nom, dessinée en pâle. */
export function sketchSVG(blocs, { vma = null, height = 18, approx = false, label = "" } = {}) {
  const list = steps(blocs, vma);
  const total = list.reduce((t, s) => t + s.minutes, 0);
  if (!list.length || !total) return "";
  const W = 1000;
  let x = 0;
  const bars = list.map((s) => {
    const w = (s.minutes / total) * W;
    const level = s.rest ? 0.18 : Math.max(0.22, Math.min(1, (s.pct - 45) / 60));
    const h = Math.max(1.5, level * height);
    const color = s.rest ? "var(--vb-recup)" : COLORS.find(([max]) => s.pct <= max)[1];
    const rect = `<rect x="${x.toFixed(2)}" y="${(height - h).toFixed(2)}" width="${Math.max(0.6, w - (list.length > 1 ? 3 : 0)).toFixed(2)}" height="${h.toFixed(2)}" fill="${color}"/>`;
    x += w;
    return rect;
  }).join("");
  return `<svg class="sketch${approx ? " is-approx" : ""}" viewBox="0 0 ${W} ${height}" preserveAspectRatio="none" height="${height}" role="img" aria-label="${label || "Profil de la séance"}">${bars}</svg>`;
}
