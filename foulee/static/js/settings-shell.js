// Réglages rangés comme ceux de Windows et du Mac : les thèmes à gauche, leurs rubriques à droite, une recherche
// qui fouille toutes les rubriques. Sur téléphone : la liste des thèmes, puis le thème choisi (avec « ← Réglages »).
// Les rubriques restent dans la page (chacune garde ses propres panneaux) : on montre seulement celles du thème.
import * as F from "./format.js";
import { icon } from "./icons.js";

export const THEMES = [
  { id: "moi", label: "Moi", icon: "user", hint: "Profil, VMA et FC, objectifs, horaires",
    sections: ["profil", "coureur", "objectif", "horaires"] },
  { id: "entrainement", label: "Entraînement", icon: "activity", hint: "Zones, allures, synchro, vues",
    sections: ["zones-fc", "zones", "synchro", "vues"] },
  { id: "connexions", label: "Connexions", icon: "sync", hint: "Garmin, Withings, Strava, calendrier",
    sections: ["cle", "withings", "strava", "calendrier"] },
  { id: "club", label: "Club et coach", icon: "club", hint: "Mon club, application partenaire, sites externes, coach, notifications",
    sections: ["club", "partenaire", "sites", "coach", "notifications"] },
  { id: "application", label: "Application", icon: "settings", hint: "Utilisateurs, sauvegarde, données, mises à jour",
    sections: ["utilisateurs", "sauvegarde", "dossier", "claude", "app", "telephone", "lan", "maj", "installation", "distant", "apropos"] },
];
const KEY = "foulee-reglages-theme";
const NARROW = "(max-width: 860px)";

export function themeOf(section) {
  return THEMES.find((t) => t.sections.includes(section))?.id || "application";
}

const fold = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function remembered() {
  try { return sessionStorage.getItem(KEY); } catch (e) { return null; }
}
function remember(id) {
  try { sessionStorage.setItem(KEY, id); } catch (e) { /* rien à retenir */ }
}

/** Range les rubriques déjà dessinées dans `main` ; `side` reçoit la recherche et les thèmes. */
export function settingsShell(shell, { section = null } = {}) {
  const side = shell.querySelector("[data-side]");
  const main = shell.querySelector("[data-main]");
  const sections = [...main.querySelectorAll("section[data-section]")];
  const present = THEMES.filter((t) => sections.some((s) => themeOf(s.dataset.section) === t.id));
  side.innerHTML = `
    <label class="st-search">${icon("search")}<input type="search" placeholder="Rechercher un réglage" aria-label="Rechercher dans les réglages" data-search></label>
    <nav class="st-themes" aria-label="Thèmes des réglages">${present.map((t) => `<button type="button" class="st-theme" data-theme="${t.id}">
      ${icon(t.icon)}<span><b>${t.label}</b><small>${t.hint}</small></span><em data-count hidden></em>${icon("right")}</button>`).join("")}</nav>`;
  const title = main.querySelector("[data-theme-title]");
  const search = side.querySelector("[data-search]");
  const empty = main.querySelector("[data-empty]");
  const wanted = section ? themeOf(section) : themeFromHash() || remembered();
  let current = present.some((t) => t.id === wanted) ? wanted : present[0]?.id;

  const markFirst = () => {
    sections.forEach((s) => s.classList.remove("st-first"));
    sections.find((s) => !s.hidden)?.classList.add("st-first");  // la première rubrique visible : sans trait au-dessus
    // un formulaire ou un bloc sans rubrique visible disparaît
    main.querySelectorAll(".settings").forEach((box) => { box.hidden = !box.querySelector(":scope > section:not([hidden])"); });
  };
  const showTheme = (id, { scroll = true } = {}) => {
    current = id;
    remember(id);
    const theme = THEMES.find((t) => t.id === id);
    sections.forEach((s) => { s.hidden = themeOf(s.dataset.section) !== id; s.classList.remove("st-hit"); });
    side.querySelectorAll("[data-theme]").forEach((b) => {
      b.setAttribute("aria-current", b.dataset.theme === id ? "page" : "false");
      b.querySelector("[data-count]").hidden = true;
    });
    title.innerHTML = `${icon(theme.icon)}${theme.label}`;
    empty.hidden = true;
    markFirst();
    try { history.replaceState(null, "", `#/reglages?theme=${id}`); } catch (e) { /* adresse inchangée */ }
    if (scroll) window.scrollTo(0, 0);
  };
  const filter = () => {
    const q = fold(search.value.trim());
    if (!q) { showTheme(current, { scroll: false }); return; }
    const words = q.split(/\s+/);
    const counts = {};
    sections.forEach((s) => {
      const hit = words.every((w) => fold(s.textContent).includes(w)
        || [...s.querySelectorAll("input, select, textarea")].some((el) => fold(el.value || "").includes(w)));
      s.hidden = !hit;
      s.classList.toggle("st-hit", hit);
      if (hit) counts[themeOf(s.dataset.section)] = (counts[themeOf(s.dataset.section)] || 0) + 1;
    });
    side.querySelectorAll("[data-theme]").forEach((b) => {
      b.setAttribute("aria-current", "false");
      const n = counts[b.dataset.theme] || 0;
      const badge = b.querySelector("[data-count]");
      badge.textContent = n;
      badge.hidden = !n;
    });
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    title.innerHTML = `${icon("search")}${total ? `${total} rubrique${total > 1 ? "s" : ""} pour « ${F.escape(search.value.trim())} »` : "Aucune rubrique"}`;
    empty.hidden = Boolean(total);
    markFirst();
    shell.dataset.mode = "detail";
  };

  side.querySelector(".st-themes").addEventListener("click", (e) => {
    const id = e.target.closest("[data-theme]")?.dataset.theme;
    if (!id) return;
    search.value = "";
    showTheme(id);
    shell.dataset.mode = "detail";
  });
  let timer = null;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(filter, 120); });
  search.addEventListener("keydown", (e) => { if (e.key === "Escape") { search.value = ""; filter(); } });
  main.querySelector("[data-back]").addEventListener("click", () => {
    shell.dataset.mode = "list";
    search.value = "";
    window.scrollTo(0, 0);
  });

  // Sur téléphone, on arrive sur la liste des thèmes, sauf si un lien vise une rubrique ou un thème précis
  const aimed = Boolean(section || themeFromHash());
  if (current) showTheme(current, { scroll: false });
  shell.dataset.mode = matchMedia(NARROW).matches && !aimed ? "list" : "detail";
  return { showTheme, current: () => current };
}

/** Le thème demandé par l'adresse (« #/reglages?theme=connexions »), s'il y en a un. */
export function themeFromHash() {
  const id = new URLSearchParams(location.hash.split("?")[1] || "").get("theme");
  return THEMES.some((t) => t.id === id) ? id : null;
}
