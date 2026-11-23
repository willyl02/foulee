// Le déroulé d'une séance en blocs (échauffement, corps de séance répété avec sa récup, retour au calme), en % de
// VMA ou en zone de FC : le formulaire d'un bloc et sa lecture, et des séances d'exemple. Partagé par « Proposer une
// séance » (coach) et l'Atelier (mes séances à moi).
import * as F from "./format.js";
import { icon } from "./icons.js";
import { GENRES } from "./coach-ui.js";

export const SPORTS = [["course", "Course à pied"], ["trail", "Trail"], ["velo", "Vélo"], ["natation", "Natation"], ["renfo", "Renforcement"],
  ["cardio", "Cardio / HIIT"], ["souplesse", "Souplesse / yoga"], ["marche", "Marche"], ["autre", "Autre"]];

export const B = (genre, nom, extra) => ({ genre, nom, repetitions: 1, ...extra });
export const EXAMPLES = [
  { titre: "Footing en endurance fondamentale", sport: "course", consigne: "Aisance respiratoire : tu dois pouvoir parler en courant.",
    blocs: [B("corps", "Footing", { duree_min: 45, pct_vma: 65 })] },
  { titre: "Seuil 3 × 10 min", sport: "course", consigne: "Blocs réguliers plutôt que rapides : le 3e ne doit pas être plus lent que le 1er.",
    blocs: [B("echauffement", "Échauffement", { duree_min: 20, pct_vma: 65 }), B("corps", "Seuil", { repetitions: 3, duree_min: 10, pct_vma: 88, recup_min: 2, recup_texte: "trot" }),
      B("calme", "Retour au calme", { duree_min: 10, pct_vma: 60 })] },
  { titre: "VMA courte 10 × 400 m", sport: "course", consigne: "Départs maîtrisés, la dernière doit ressembler à la première.",
    blocs: [B("echauffement", "Échauffement", { duree_min: 20, pct_vma: 65, note: "avec 3 accélérations" }),
      B("corps", "400 m", { repetitions: 10, distance_m: 400, pct_vma: 100, recup_min: 1.5, recup_texte: "trot" }), B("calme", "Retour au calme", { duree_min: 10, pct_vma: 60 })] },
  { titre: "Fractionné 30/30", sport: "course", consigne: "",
    blocs: [B("echauffement", "Échauffement", { duree_min: 20, pct_vma: 65 }), B("corps", "30 s vite", { repetitions: 12, duree_min: 0.5, pct_vma: 100, recup_min: 0.5, recup_texte: "trot" }),
      B("calme", "Retour au calme", { duree_min: 10, pct_vma: 60 })] },
  { titre: "Sortie longue progressive", sport: "course", consigne: "Hydrate-toi, et garde de la marge sur la première heure.",
    blocs: [B("corps", "Endurance", { duree_min: 70, pct_vma: 65 }), B("corps", "Allure semi", { duree_min: 20, pct_vma: 82 }), B("calme", "Retour au calme", { duree_min: 10, pct_vma: 60 })] },
  { titre: "Renfo coureur 30 min", sport: "renfo", consigne: "Qualité d'exécution avant le nombre de répétitions.",
    blocs: [B("echauffement", "Mobilité", { duree_min: 5 }), B("corps", "Circuit", { repetitions: 3, duree_min: 7, recup_min: 1, note: "gainage, squats, fentes, pont fessier, mollets" }),
      B("calme", "Étirements doux", { duree_min: 4 })] },
];

export const clone = (x) => JSON.parse(JSON.stringify(x));
// « libre » : la montre passe à l'étape suivante à la touche Lap (sur piste, de ligne à ligne)
const UNITS = [["min", "min"], ["s", "s"], ["m", "m"], ["km", "km"], ["lap", "libre (Lap)"]];
const REST_UNITS = [["min", "min"], ["s", "s"], ["lap", "libre (Lap)"]];
const num = (v) => { const n = Number(String(v).replace(",", ".")); return Number.isFinite(n) && n > 0 ? n : null; };
const show = (n) => (n == null ? "" : String(Math.round(n * 100) / 100).replace(".", ","));

export function blockForm(b, i, n) {
  const genre = GENRES[b.genre] || GENRES.corps;
  const qtyUnit = b.libre ? "lap" : b.distance_m ? (b.distance_m >= 1000 && b.distance_m % 100 === 0 ? "km" : "m") : (b.duree_min && b.duree_min < 1 ? "s" : "min");
  const qty = qtyUnit === "km" ? b.distance_m / 1000 : qtyUnit === "m" ? b.distance_m : qtyUnit === "s" ? Math.round((b.duree_min || 0) * 60) : b.duree_min;
  const effort = b.pct_vma ? "vma" : b.zone_fc ? "fc" : "aucune";
  const restUnit = b.recup_libre ? "lap" : b.recup_min && b.recup_min < 1 ? "s" : "min";
  const rest = restUnit === "s" ? Math.round(b.recup_min * 60) : b.recup_min;
  return `<div class="co-bform" data-block="${i}" style="--genre:${genre.color}">
    <div class="co-brow">
      <select data-k="genre" aria-label="Type de bloc">${Object.entries(GENRES).map(([k, g]) => `<option value="${k}" ${k === (b.genre || "corps") ? "selected" : ""}>${g.label}</option>`).join("")}</select>
      <input data-k="nom" type="text" maxlength="60" value="${F.escape(b.nom || "")}" placeholder="Nom du bloc" aria-label="Nom du bloc">
      <span class="co-reps"><input data-k="repetitions" type="number" min="1" max="50" value="${b.repetitions || 1}" aria-label="Répétitions"><span>×</span></span>
      <span class="co-qty"><input data-k="qty" type="text" inputmode="decimal" value="${F.escape(qtyUnit === "lap" ? "" : show(qty))}" placeholder="${qtyUnit === "lap" ? "touche Lap" : "durée"}" aria-label="Durée ou distance" ${qtyUnit === "lap" ? "disabled" : ""}>
        <select data-k="unit" aria-label="Unité">${UNITS.map(([u, label]) => `<option value="${u}" ${u === qtyUnit ? "selected" : ""}>${label}</option>`).join("")}</select></span>
    </div>
    <div class="co-brow sub">
      <span class="co-effort"><select data-k="effort" aria-label="Intensité"><option value="vma" ${effort === "vma" ? "selected" : ""}>% VMA</option><option value="fc" ${effort === "fc" ? "selected" : ""}>Zone FC</option><option value="aucune" ${effort === "aucune" ? "selected" : ""}>Sans intensité</option></select>
        ${effort === "vma" ? `<input data-k="pct_vma" type="number" min="30" max="140" value="${b.pct_vma ?? ""}" aria-label="Pourcentage de VMA"><span>%</span>`
          : effort === "fc" ? `<input data-k="zone_fc" type="number" min="1" max="5" value="${b.zone_fc ?? ""}" aria-label="Zone de FC">` : ""}</span>
      ${(b.repetitions || 1) > 1 ? `<span class="co-rest"><span>récup</span><input data-k="rest" type="text" inputmode="decimal" value="${F.escape(restUnit === "lap" ? "" : show(rest))}" placeholder="${restUnit === "lap" ? "Lap" : ""}" aria-label="Récupération" ${restUnit === "lap" ? "disabled" : ""}>
        <select data-k="restunit" aria-label="Unité de récupération">${REST_UNITS.map(([u, label]) => `<option value="${u}" ${u === restUnit ? "selected" : ""}>${label}</option>`).join("")}</select>
        <input data-k="recup_texte" type="text" maxlength="40" value="${F.escape(b.recup_texte || "")}" placeholder="trot, marche…" aria-label="Façon de récupérer"></span>` : ""}
      <input data-k="note" class="co-note" type="text" maxlength="200" value="${F.escape(b.note || "")}" placeholder="Précision (facultatif)" aria-label="Précision">
    </div>
    <span class="co-bside">
      <button type="button" class="co-mini co-flip" data-move="-1" ${i === 0 ? "disabled" : ""} title="Monter">${icon("chevron")}</button>
      <button type="button" class="co-mini" data-dup title="Dupliquer">${icon("copy")}</button>
      <button type="button" class="co-mini" data-move="1" ${i === n - 1 ? "disabled" : ""} title="Descendre">${icon("chevron")}</button>
      <button type="button" class="co-mini" data-del ${n === 1 ? "disabled" : ""} title="Supprimer">${icon("trash")}</button></span></div>`;
}

export function readBlock(el, old) {
  const v = (k) => el.querySelector(`[data-k="${k}"]`)?.value ?? "";
  const unit = v("unit");
  const qty = num(v("qty"));
  const effort = v("effort");
  const b = { genre: v("genre"), nom: v("nom").trim(), repetitions: Math.max(1, Math.min(50, Math.round(Number(v("repetitions")) || 1))) };
  if (unit === "lap") b.libre = true;  // jusqu'à la touche Lap : ni durée ni distance
  else if (qty) {
    if (unit === "km") b.distance_m = Math.round(qty * 1000);
    else if (unit === "m") b.distance_m = Math.round(qty);
    else b.duree_min = unit === "s" ? Math.round(qty) / 60 : qty;
  }
  if (effort === "vma") { const p = num(v("pct_vma")); if (p) b.pct_vma = Math.round(p); else if (old?.pct_vma && !el.querySelector('[data-k="pct_vma"]')) b.pct_vma = old.pct_vma; }
  if (effort === "fc") { const z = num(v("zone_fc")); if (z) b.zone_fc = Math.round(z); else if (!el.querySelector('[data-k="zone_fc"]')) b.zone_fc = old?.zone_fc || 2; }
  if (effort === "vma" && !b.pct_vma && !el.querySelector('[data-k="pct_vma"]')) b.pct_vma = 70;
  const rest = num(v("rest"));
  if (b.repetitions > 1 && v("restunit") === "lap") b.recup_libre = true;
  else if (b.repetitions > 1 && rest) b.recup_min = v("restunit") === "s" ? Math.round(rest) / 60 : rest;
  else if (b.repetitions > 1 && !el.querySelector('[data-k="rest"]') && old?.recup_min) b.recup_min = old.recup_min;
  if (b.repetitions > 1 && (v("recup_texte").trim() || (!el.querySelector('[data-k="recup_texte"]') && old?.recup_texte))) b.recup_texte = v("recup_texte").trim() || old.recup_texte;
  if (v("note").trim()) b.note = v("note").trim();
  return b;
}
