// D'où viennent les chiffres : « Garmin », « Strava (Wahoo ELEMNT BOLT) », « Withings »…
// Affiché à côté du titre de chaque tuile (les règles de Garmin demandent sa mention près du titre, et celles de
// Strava une mention de Garmin pour les séances venues d'une montre Garmin).

const GARMIN_DEVICE = /^garmin\b/i;

/** Réunit des listes de sources [{cle, nom, appareils}] (plusieurs requêtes pour une même tuile). */
export function mergeSources(...lists) {
  const found = new Map();
  for (const list of lists) {
    for (const s of list || []) {
      if (!s?.cle) continue;
      const entry = found.get(s.cle) || { cle: s.cle, nom: s.nom || s.cle, appareils: new Set() };
      (s.appareils || []).forEach((d) => d && entry.appareils.add(d));
      found.set(s.cle, entry);
    }
  }
  const order = ["garmin", "strava", "withings"];
  return [...found.values()]
    .sort((a, b) => (order.indexOf(a.cle) + 1 || 9) - (order.indexOf(b.cle) + 1 || 9))
    .map((s) => ({ ...s, appareils: [...s.appareils] }));
}

/** Sources des séances d'une liste (chaque séance porte sa source et, pour Strava, son appareil). */
export function rowSources(rows) {
  const names = { garmin: "Garmin", strava: "Strava", withings: "Withings" };
  return mergeSources((rows || []).filter((a) => a?.source).map((a) => ({
    cle: a.source, nom: names[a.source] || a.source, appareils: a.source !== "garmin" && a.appareil ? [a.appareil] : [],
  })));
}

/** « Garmin · Strava (Wahoo ELEMNT BOLT) · Garmin Forerunner 965 » ; vide s'il n'y a rien. */
export function sourceText(list) {
  const parts = [];
  for (const s of list || []) {
    const devices = s.appareils || [];
    if (s.cle === "strava") {
      const others = devices.filter((d) => !GARMIN_DEVICE.test(d));
      parts.push(others.length === 1 ? `Strava (${others[0]})` : "Strava");
      devices.filter((d) => GARMIN_DEVICE.test(d)).forEach((d) => parts.push(d));  // séance d'une montre Garmin
    } else {
      parts.push(s.nom || s.cle);
    }
  }
  return [...new Set(parts)].join(" · ");
}
