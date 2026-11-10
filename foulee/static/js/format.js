// Mise en forme française des nombres, durées, allures, heures et dates.

const NB = new Intl.NumberFormat("fr-FR");
const NB1 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const NB2 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const MONTHS_LONG = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const DAYS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];

export const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function int(v) { return isNum(v) ? NB.format(Math.round(v)) : "–"; }
export function dec1(v) { return isNum(v) ? NB1.format(v) : "–"; }
export function dec2(v) { return isNum(v) ? NB2.format(v) : "–"; }

export function duration(seconds, { short = false } = {}) {
  if (!isNum(seconds)) return "–";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (short) return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
  if (h) return `${h} h ${String(m).padStart(2, "0")}`;
  if (m >= 10) return `${m} min`;
  const sec = s % 60;
  return m ? `${m} min ${String(sec).padStart(2, "0")}` : `${sec} s`;
}

export function hoursAxis(seconds) {
  if (!isNum(seconds)) return "";
  const h = seconds / 3600;
  return Number.isInteger(Math.round(h * 10) / 10) ? `${Math.round(h)} h` : `${NB1.format(h)} h`;
}

export function chrono(seconds) {
  if (!isNum(seconds)) return "–";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

/** Vitesse (m/s) → allure « 4:58 ». */
export function pace(speed) {
  if (!isNum(speed) || speed <= 0.3) return "–";
  const total = Math.round(1000 / speed);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function clock(hours) {
  if (!isNum(hours)) return "–";
  let minutes = Math.round(hours * 60) % 1440;
  if (minutes < 0) minutes += 1440;
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
}

/** Valeur d'une métrique du catalogue, avec ou sans unité. */
export function value(meta, v, { unit = true } = {}) {
  if (!isNum(v)) return "–";
  switch (meta?.fmt) {
    case "duration": return duration(v);
    case "pace": return unit ? `${pace(v)} /km` : pace(v);
    case "clock": return clock(v);
    case "km": return unit ? `${dec1(v)} km` : dec1(v);
    case "dec1": return withUnit(dec1(v), meta, unit);
    case "dec2": return withUnit(dec2(v), meta, unit);
    case "num": return withUnit(Number.isInteger(v) ? int(v) : new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(v), meta, unit);
    default: return withUnit(int(v), meta, unit);
  }
}

/** « 4:05 » → 245 secondes par km (null si illisible). */
export function parsePace(text) {
  const m = String(text ?? "").trim().match(/^(\d{1,2})[:'’](\d{2})$/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

/** Secondes par km → « 4:05 ». */
export function paceSecs(secs) {
  if (!isNum(secs) || secs <= 0) return "–";
  const t = Math.round(secs);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

function withUnit(text, meta, unit) {
  if (!unit || !meta?.unit) return text;
  if (meta.unit === "/100") return `${text}/100`;
  return `${text} ${meta.unit}`;
}

/** Valeur courte pour les axes. */
export function axis(meta, v) {
  if (!isNum(v)) return "";
  switch (meta?.fmt) {
    case "duration": return hoursAxis(v);
    case "pace": return pace(v);
    case "clock": return clock(v);
    case "km": return NB.format(Math.round(v * 10) / 10);
    default:
      if (Math.abs(v) >= 10000) return `${NB.format(Math.round(v / 1000))} k`;
      return NB.format(Math.round(v * 100) / 100);
  }
}

/** Écart lisible entre deux valeurs d'une même métrique. */
export function delta(meta, current, reference) {
  if (!isNum(current) || !isNum(reference)) return null;
  const d = current - reference;
  const sign = d > 0 ? "+" : d < 0 ? "−" : "±";
  const a = Math.abs(d);
  switch (meta?.fmt) {
    case "duration": return a < 3600 ? `${sign}${Math.round(a / 60)} min` : `${sign}${duration(a)}`;
    case "clock": { const m = Math.round(a * 60); const t = m >= 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}` : `${m} min`; return `${t} ${d > 0 ? "plus tard" : "plus tôt"}`; }
    case "pace": {
      const s = Math.round(1000 / current - 1000 / reference);
      return `${s > 0 ? "+" : s < 0 ? "−" : "±"}${Math.abs(s)} s/km`;
    }
    case "km": return `${sign}${dec1(a)} km`;
    case "dec1": return `${sign}${dec1(a)}${meta.unit ? " " + meta.unit : ""}`;
    case "dec2": return `${sign}${dec2(a)}`;
    default: return `${sign}${int(a)}${meta?.unit && meta.unit !== "/100" ? " " + meta.unit : ""}`;
  }
}

// ------------------------------------------------------------------ dates
export function parseDate(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function isoDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function addDays(date, days) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

export function isoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const year = d.getUTCFullYear();
  const week = Math.ceil(((d - Date.UTC(year, 0, 1)) / 86400000 + 1) / 7);
  return { year, week };
}

export function dateShort(iso) {
  const d = parseDate(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function dateLong(iso, { year = false, weekday = true } = {}) {
  const d = parseDate(iso);
  const text = `${weekday ? DAYS[d.getDay()] + " " : ""}${d.getDate() === 1 ? "1er" : d.getDate()} ${MONTHS_LONG[d.getMonth()]}${year ? " " + d.getFullYear() : ""}`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function monthLabel(iso) {
  const d = parseDate(iso);
  return `${MONTHS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`;
}

export function periodLabel(iso, agg) {
  if (agg === "semaine") return `S${isoWeek(parseDate(iso)).week}`;
  if (agg === "mois") return monthLabel(iso);
  return dateShort(iso);
}

export function periodLong(iso, agg) {
  if (agg === "semaine") return `Semaine ${isoWeek(parseDate(iso)).week}, du ${dateLong(iso, { weekday: false })}`;
  if (agg === "mois") { const d = parseDate(iso); return `${MONTHS_LONG[d.getMonth()]} ${d.getFullYear()}`; }
  return dateLong(iso, { year: true });
}

export function relative(isoDateTime) {
  if (!isoDateTime) return "jamais";
  const then = new Date(String(isoDateTime).replace(" ", "T"));
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  return days === 1 ? "hier" : `il y a ${days} jours`;
}

export function whenActivity(startLocal) {
  const day = startLocal.slice(0, 10);
  const time = startLocal.slice(11, 16).replace(":", " h ");
  const today = isoDate(new Date());
  const yesterday = isoDate(addDays(new Date(), -1));
  if (day === today) return `Aujourd'hui à ${time}`;
  if (day === yesterday) return `Hier à ${time}`;
  return `${dateLong(day, { year: parseDate(day).getFullYear() !== new Date().getFullYear() })} à ${time}`;
}

// ------------------------------------------------- horaires de travail
// Même règle que le serveur (schedule.py) : cycle en semaines (parité ISO ou semaine n° 1 datée)
// ou en jours (jour n° 1 daté), jours de repos (""), congés.
function dayNumber(date) { return Math.round(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000); }
function mod(n, m) { return ((n % m) + m) % m; }
export function mondayOf(date) { return addDays(new Date(date.getFullYear(), date.getMonth(), date.getDate()), -((date.getDay() + 6) % 7)); }

export function cycleWeekIndex(date, horaires) {
  const c = horaires.cycle;
  if (c.ancrage === "parite") return isoWeek(date).week % 2 === 1 ? 0 : 1;
  const weeks = Math.floor((dayNumber(mondayOf(date)) - dayNumber(parseDate(c.ancrage))) / 7);
  return mod(weeks, c.semaines.length);
}

export function cycleCode(date, horaires) {
  const c = horaires.cycle;
  if (c.unite === "jour") return c.jours[mod(dayNumber(date) - dayNumber(parseDate(c.debut)), c.jours.length)] || "";
  return c.semaines[cycleWeekIndex(date, horaires)][(date.getDay() + 6) % 7] || "";
}

export function leaveOf(date, horaires) {
  const iso = isoDate(date);
  return (horaires.conges || []).find((c) => c.du <= iso && iso <= c.au) || null;
}

/** Groupe de comparaison d'un jour : un poste, « repos », ou null (congés, repos non compté). */
export function shiftOf(date, settings, includeRest = null) {
  const h = settings?.horaires;
  if (!h || h.actif === false || leaveOf(date, h)) return null;
  const code = cycleCode(date, h);
  if (code) return code;
  if (!(includeRest ?? !(h.jours_ouvres ?? true))) return null;
  if (h.cycle.unite !== "semaine") return "repos";
  const counts = {};
  h.cycle.semaines[cycleWeekIndex(date, h)].filter(Boolean).forEach((c) => { counts[c] = (counts[c] || 0) + 1; });
  return Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0] || null;
}

/** Ce que dit le planning d'un jour : { poste, nom, debut, fin, repos, conges }. */
export function dayPlan(date, settings) {
  const h = settings?.horaires;
  if (!h || h.actif === false) return { poste: null, nom: null, actif: false };
  const leave = leaveOf(date, h);
  if (leave) return { poste: null, nom: "Congés", conges: leave.nom || "Congés", actif: true };
  const code = cycleCode(date, h);
  if (!code) return { poste: null, nom: "Repos", repos: true, actif: true };
  const poste = h.postes.find((p) => p.id === code) || { nom: code };
  return { poste: code, nom: poste.nom, debut: poste.debut, fin: poste.fin, actif: true };
}

/** Couleur d'un poste : l'ordre des postes dans les horaires (matin bleu, soir orange…). */
export function shiftColor(id, settings, palette) {
  if (!id || id === "repos") return palette.base;
  const index = (settings?.horaires?.postes || []).findIndex((p) => p.id === id);
  return palette.series[(index < 0 ? 0 : index) % palette.series.length];
}

export function shiftName(id, settings) {
  if (id === "repos") return "Repos";
  return (settings?.horaires?.postes || []).find((p) => p.id === id)?.nom || id || "–";
}

/** « 2026-11-10 14:02:33 » → « 10 nov. 2026 à 14 h 02 ». */
export function dateTime(isoDateTime) {
  if (!isoDateTime) return "–";
  const text = String(isoDateTime);
  const day = parseDate(text);
  const time = text.length >= 16 ? ` à ${text.slice(11, 13)}\u00a0h\u00a0${text.slice(14, 16)}` : "";
  return `${day.getDate()}\u00a0${MONTHS[day.getMonth()]} ${day.getFullYear()}${time}`;
}

/** Taille d'un fichier ou d'un dossier : « 12,4 Mo ». */
export function size(bytes) {
  if (!isNum(bytes)) return "–";
  const units = ["o", "Ko", "Mo", "Go", "To"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return unit === 0 ? `${value} o` : `${value < 10 ? NB1.format(value) : NB.format(Math.round(value))} ${units[unit]}`;
}

export function escape(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
