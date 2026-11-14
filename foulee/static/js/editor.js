// Dialogues d'édition : choisir un type de tuile, régler une tuile, créer ou renommer une vue.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

export const OPTION_LABELS = {
  fenetre: { auto: "Automatique", jour: "Le jour même", semaine: "Les 7 derniers jours", mois: "Les 30 derniers jours" },
  style: { ligne: "Courbe", barres: "Barres", aire: "Aire" },
  agregation: { jour: "Jour", semaine: "Semaine", mois: "Mois" },
  fonction: { auto: "Automatique (selon la métrique)", avg: "Moyenne", sum: "Somme", max: "Maximum", min: "Minimum" },
  disposition: { auto: "Automatique (un graphique par unité)", superposer: "Toutes sur le même graphique", empiler: "Un graphique par métrique" },
  zones: { fc: "Fréquence cardiaque", allure: "Allure" },
  onglet: { tableau: "Allures, vitesses et piste", vameval: "Test VAMEVAL" },
  donnee: { body_battery: "Body Battery de la journée", fc: "FC de la journée", sommeil: "Phases du sommeil", vfc: "VFC de la nuit" },
  jour: { aujourdhui: "Aujourd'hui", hier: "Hier" },
  groupe: { semaine: "Semaine", mois: "Mois", total: "Total de la période" },
  mois: { 3: "3 mois", 6: "6 mois", 12: "12 mois" },
  decalage: { 0: "Le même jour", 1: "Le lendemain", 2: "Deux jours après" },
  axe: { temps: "Temps", distance: "Distance" },
  mode: { tours: "Tours enregistrés par la montre", kilometres: "Kilomètre par kilomètre" },
  courbes: { hr: "Fréquence cardiaque", spd: "Allure / vitesse", alt: "Altitude", cad: "Cadence", pwr: "Puissance", temp: "Température" },
};

export function periodLabel(value) {
  const map = { herite: "Suivre la période de la vue", 180: "6 mois", 365: "1 an", 730: "2 ans" };
  return map[value] || `${value} jours`;
}

export function sportLabel(value, sports) {
  if (value === "tous") return "Tous les sports";
  if (value === "pied") return "Course + trail";
  return sports[value] || value;
}

function el(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

export function openDialog(inner) {
  const dialog = el(`<dialog>${inner}</dialog>`);
  document.body.appendChild(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  dialog.showModal();
  return dialog;
}

const fold = (text) => String(text || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");

function metricLabel(boot, key) {
  return boot.metriques.find((m) => m.key === key)?.label || key;
}

function metricButton(boot, value) {
  return `<button type="button" class="metric-btn" data-metric="${F.escape(value)}">${icon("search")}<span>${F.escape(metricLabel(boot, value))}</span></button>`;
}

let rawFields = null;  // valeurs brutes de Garmin, chargées une fois à la demande

/** Choix d'une métrique : catalogue par catégories + toutes les valeurs brutes de Garmin, avec recherche. */
export function pickMetric(boot, current) {
  return new Promise((resolve) => {
    const dialog = openDialog(`<div class="dlg dlg-wide">
      <div class="dlg-head"><h2>Choisir une métrique</h2>
        <p>Les métriques de Foulée d'abord, puis toutes les valeurs que Garmin renvoie (données brutes).</p>
        <label class="search-field">${icon("search")}<input type="search" data-search placeholder="Chercher : sommeil, SpO2, foulée, puissance…" aria-label="Chercher une métrique"></label></div>
      <div class="dlg-body" data-list><p class="tile-msg" style="position:static">Chargement…</p></div>
      <div class="dlg-foot"><button class="btn" type="button" data-cancel>Annuler</button></div></div>`);
    let chosen = null;
    const list = dialog.querySelector("[data-list]");
    const search = dialog.querySelector("[data-search]");
    const groups = () => {
      const order = boot.categories_metriques || [];
      const byCat = {};
      for (const m of boot.metriques) if (m.kind !== "raw") (byCat[m.category] ||= []).push(m);
      const cats = [...order.filter((c) => byCat[c]), ...Object.keys(byCat).filter((c) => !order.includes(c))];
      const result = cats.map((c) => [c, byCat[c]]);
      const raw = {};
      for (const f of rawFields || []) (raw[f.category] ||= []).push(f);
      return result.concat(Object.entries(raw));
    };
    const draw = () => {
      const q = fold(search.value.trim());
      const html = groups().map(([cat, items]) => {
        const shown = items.filter((m) => !q || fold(`${m.label} ${m.key} ${m.category} ${m.description || ""}`).includes(q));
        if (!shown.length) return "";
        return `<section class="type-group"><h3>${F.escape(cat)}</h3><div class="metric-list">${shown.map((m) => `
          <button type="button" class="metric-item" data-key="${F.escape(m.key)}" aria-pressed="${m.key === current}">
            <b>${F.escape(m.label)}</b><span>${m.kind === "raw" ? `exemple : ${F.escape(m.exemple)}` : F.escape(m.description || m.unit || "")}</span></button>`).join("")}</div></section>`;
      }).join("");
      list.innerHTML = html || `<p class="tile-msg" style="position:static">Aucune métrique ne correspond.</p>`;
    };
    search.addEventListener("input", draw);
    dialog.addEventListener("click", (e) => {
      const item = e.target.closest("[data-key]");
      if (item) {
        chosen = item.dataset.key;
        const raw = (rawFields || []).find((f) => f.key === chosen);
        if (raw && !boot.metriques.some((m) => m.key === chosen)) boot.metriques.push(raw);
        dialog.close();
      }
      if (e.target.closest("[data-cancel]")) dialog.close();
    });
    dialog.addEventListener("close", () => resolve(chosen));
    draw();
    search.focus();
    if (!rawFields) {
      api.get("/api/garmin/champs").then((d) => { rawFields = d.champs; if (dialog.open) draw(); }).catch(() => { rawFields = []; });
    }
  });
}

function fieldHTML(param, value, boot) {
  const id = `f-${param.key}`;
  const label = `<span>${F.escape(param.label)}</span>`;
  switch (param.kind) {
    case "metric":
      return `<div class="field" data-key="${param.key}" data-kind="metric">${label}${metricButton(boot, value)}</div>`;
    case "metrics":
      return `<div class="field" data-key="${param.key}" data-kind="metrics">${label}
        <div class="metric-rows">${(value || []).map((v) => metricRow(boot, v)).join("")}</div>
        <button type="button" class="btn btn-ghost" data-add-metric style="justify-self:start">${icon("plus")}Ajouter une métrique</button></div>`;
    case "select":
    case "periode":
    case "sport": {
      const options = param.kind === "periode" ? boot.periodes : param.kind === "sport" ? ["tous", "pied", ...Object.keys(boot.sports)] : param.options;
      const labelOf = (o) => (param.kind === "periode" ? periodLabel(o) : param.kind === "sport" ? sportLabel(o, boot.sports) : (OPTION_LABELS[param.key]?.[o] ?? o));
      return `<label class="field">${label}<select id="${id}" data-key="${param.key}">${options.map((o) =>
        `<option value="${o}" ${String(o) === String(value) ? "selected" : ""}>${F.escape(labelOf(o))}</option>`).join("")}</select></label>`;
    }
    case "multi":
      return `<div class="field" data-key="${param.key}" data-kind="multi">${label}${param.options.map((o) =>
        `<label class="check"><input type="checkbox" value="${o}" ${(value || []).includes(o) ? "checked" : ""}>${F.escape(OPTION_LABELS[param.key]?.[o] ?? o)}</label>`).join("")}</div>`;
    case "number":
      return `<label class="field">${label}<input type="number" id="${id}" data-key="${param.key}" value="${F.escape(value)}" step="1"></label>`;
    case "bool":
      return `<label class="check"><input type="checkbox" id="${id}" data-key="${param.key}" ${value ? "checked" : ""}>${F.escape(param.label)}</label>`;
    case "textarea":
      return `<label class="field">${label}<textarea id="${id}" data-key="${param.key}">${F.escape(value)}</textarea><span class="hint">Astuce : **texte** s'affiche en gras.</span></label>`;
    default:
      return `<label class="field">${label}<input type="text" id="${id}" data-key="${param.key}" value="${F.escape(value)}"></label>`;
  }
}

function metricRow(boot, value) {
  return `<div class="metric-row">${metricButton(boot, value)}
    <button type="button" class="btn btn-ghost icon-btn" data-remove aria-label="Retirer cette métrique">${icon("close")}</button></div>`;
}

function readForm(form, typeDef) {
  const params = {};
  for (const param of typeDef.params) {
    if (param.kind === "metrics") {
      params[param.key] = [...form.querySelectorAll(`[data-key="${param.key}"] .metric-row [data-metric]`)].map((b) => b.dataset.metric);
    } else if (param.kind === "metric") {
      params[param.key] = form.querySelector(`[data-key="${param.key}"] [data-metric]`).dataset.metric;
    } else if (param.kind === "multi") {
      params[param.key] = [...form.querySelectorAll(`[data-key="${param.key}"] input:checked`)].map((c) => c.value);
    } else {
      const input = form.querySelector(`[data-key="${param.key}"]`);
      if (!input) continue;
      params[param.key] = param.kind === "bool" ? input.checked : param.kind === "number" ? Number(input.value) : input.value;
    }
  }
  return params;
}

/** Réglages d'une tuile. Résout avec {titre, params, w, h} ou null. */
export function editTile(tile, typeDef, boot) {
  return new Promise((resolve) => {
    const dialog = openDialog(`<form class="dlg" method="dialog">
      <div class="dlg-head"><h2>${F.escape(typeDef.label)}</h2><p>${F.escape(typeDef.description)}</p></div>
      <div class="dlg-body">
        <label class="field"><span>Titre (laisse vide pour le titre automatique)</span><input type="text" data-title value="${F.escape(tile.titre || "")}"></label>
        ${typeDef.params.map((p) => fieldHTML(p, tile.params?.[p.key] ?? p.default, boot)).join("")}
        <div class="form-grid" style="grid-template-columns:1fr 1fr">
          <label class="field"><span>Largeur</span><select data-w>${[3, 4, 6, 8, 9, 12].map((w) => `<option value="${w}" ${w === tile.w ? "selected" : ""}>${{ 3: "Quart", 4: "Tiers", 6: "Moitié", 8: "Deux tiers", 9: "Trois quarts", 12: "Toute la largeur" }[w]}</option>`).join("")}</select></label>
          <label class="field"><span>Hauteur</span><select data-h>${[1, 2, 3].map((h) => `<option value="${h}" ${h === tile.h ? "selected" : ""}>${{ 1: "Basse", 2: "Moyenne", 3: "Haute" }[h]}</option>`).join("")}</select></label>
        </div>
      </div>
      <div class="dlg-foot"><button class="btn" value="cancel" type="submit">Annuler</button><button class="btn btn-primary" value="ok" type="submit">Enregistrer</button></div>
    </form>`);
    const form = dialog.querySelector("form");
    form.addEventListener("click", async (e) => {
      const add = e.target.closest("[data-add-metric]");
      if (add) {
        const key = await pickMetric(boot, null);
        if (key) add.previousElementSibling.insertAdjacentHTML("beforeend", metricRow(boot, key));
        return;
      }
      const remove = e.target.closest("[data-remove]");
      if (remove && remove.closest(".metric-rows").children.length > 1) remove.closest(".metric-row").remove();
      const pick = e.target.closest("[data-metric]");
      if (pick) {
        const key = await pickMetric(boot, pick.dataset.metric);
        if (key) {
          pick.dataset.metric = key;
          pick.querySelector("span").textContent = metricLabel(boot, key);
        }
      }
    });
    dialog.addEventListener("close", () => {
      if (dialog.returnValue !== "ok") return resolve(null);
      resolve({
        titre: form.querySelector("[data-title]").value.trim(),
        params: readForm(form, typeDef),
        w: Number(form.querySelector("[data-w]").value),
        h: Number(form.querySelector("[data-h]").value),
      });
    });
  });
}

/** Choix d'un type de tuile, rangés par catégories, avec recherche. Résout avec le type ou null. */
export function pickTileType(boot) {
  return new Promise((resolve) => {
    const cats = boot.categories_tuiles || [...new Set(boot.tuiles.map((t) => t.categorie || "Divers"))];
    const dialog = openDialog(`<div class="dlg dlg-wide">
      <div class="dlg-head"><h2>Ajouter une tuile</h2><p>Choisis ce que la tuile doit montrer ; tu la régleras juste après. Les tuiles à métrique proposent toutes les données de Garmin.</p>
        <label class="search-field">${icon("search")}<input type="search" data-search placeholder="Chercher : records, sommeil, allure, poste…" aria-label="Chercher une tuile"></label></div>
      <div class="dlg-body">${cats.map((cat) => `<section class="type-group" data-group><h3>${F.escape(cat)}</h3><div class="type-list">${boot.tuiles.filter((t) => (t.categorie || "Divers") === cat).map((t) => `
        <button class="type-card" type="button" data-type="${t.type}" data-text="${F.escape(fold(`${t.label} ${t.description} ${cat}`))}">
        ${icon(t.icone)}<b>${F.escape(t.label)}</b><span>${F.escape(t.description)}</span></button>`).join("")}</div></section>`).join("")}
        <p class="tile-msg" style="position:static" data-empty hidden>Aucune tuile ne correspond.</p></div>
      <div class="dlg-foot"><button class="btn" type="button" data-cancel>Annuler</button></div></div>`);
    let chosen = null;
    const search = dialog.querySelector("[data-search]");
    search.addEventListener("input", () => {
      const q = fold(search.value.trim());
      let any = false;
      dialog.querySelectorAll("[data-group]").forEach((group) => {
        let shown = 0;
        group.querySelectorAll("[data-type]").forEach((card) => {
          const ok = !q || card.dataset.text.includes(q);
          card.hidden = !ok;
          if (ok) shown += 1;
        });
        group.hidden = !shown;
        any ||= shown > 0;
      });
      dialog.querySelector("[data-empty]").hidden = any;
    });
    dialog.addEventListener("click", (e) => {
      const card = e.target.closest("[data-type]");
      if (card) { chosen = card.dataset.type; dialog.close(); }
      if (e.target.closest("[data-cancel]")) dialog.close();
    });
    dialog.addEventListener("close", () => resolve(chosen));
    search.focus();
  });
}

/** Création ou renommage d'une vue. Résout avec {name, icon} ou null. */
export function editView(view, boot) {
  return new Promise((resolve) => {
    let chosenIcon = view?.icon || "chart";
    const dialog = openDialog(`<form class="dlg" method="dialog">
      <div class="dlg-head"><h2>${view ? "Renommer la vue" : "Nouvelle vue"}</h2>
        <p>${view ? "Change le nom ou l'icône." : "Une vue vide, à remplir avec les tuiles de ton choix."}</p></div>
      <div class="dlg-body">
        <label class="field"><span>Nom</span><input type="text" data-name required maxlength="60" value="${F.escape(view?.name || "")}" placeholder="Par exemple : Bloc trail d'hiver"></label>
        <div class="field"><span>Icône</span><div class="icon-pick">${boot.icones.map((i) => `<button type="button" data-icon="${i}" aria-pressed="${i === chosenIcon}" aria-label="${i}">${icon(i)}</button>`).join("")}</div></div>
      </div>
      <div class="dlg-foot"><button class="btn" value="cancel" type="submit" formnovalidate>Annuler</button><button class="btn btn-primary" value="ok" type="submit">${view ? "Enregistrer" : "Créer la vue"}</button></div>
    </form>`);
    dialog.addEventListener("click", (e) => {
      const b = e.target.closest("[data-icon]");
      if (!b) return;
      chosenIcon = b.dataset.icon;
      dialog.querySelectorAll("[data-icon]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    });
    dialog.addEventListener("close", () => {
      const name = dialog.querySelector("[data-name]").value.trim();
      resolve(dialog.returnValue === "ok" && name ? { name, icon: chosenIcon } : null);
    });
  });
}

export function confirm(title, text, okLabel = "Confirmer") {
  return new Promise((resolve) => {
    const dialog = openDialog(`<form class="dlg" method="dialog">
      <div class="dlg-head"><h2>${F.escape(title)}</h2><p>${F.escape(text)}</p></div>
      <div class="dlg-foot"><button class="btn" value="cancel" type="submit">Annuler</button><button class="btn btn-primary" value="ok" type="submit">${F.escape(okLabel)}</button></div>
    </form>`);
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"));
  });
}
