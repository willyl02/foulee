// Dialogues d'édition : choisir un type de tuile, régler une tuile, créer ou renommer une vue.
import * as F from "./format.js";
import { icon } from "./icons.js";

export const OPTION_LABELS = {
  fenetre: { auto: "Automatique", jour: "Le jour même", semaine: "Les 7 derniers jours", mois: "Les 30 derniers jours" },
  style: { ligne: "Courbe", barres: "Barres", aire: "Aire" },
  agregation: { jour: "Jour", semaine: "Semaine", mois: "Mois" },
  fonction: { auto: "Automatique (selon la métrique)", avg: "Moyenne", sum: "Somme", max: "Maximum", min: "Minimum" },
  disposition: { auto: "Automatique (un graphique par unité)", superposer: "Toutes sur le même graphique", empiler: "Un graphique par métrique" },
  zones: { fc: "Fréquence cardiaque", allure: "Allure (calée sur la VMA)" },
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

function openDialog(inner) {
  const dialog = el(`<dialog>${inner}</dialog>`);
  document.body.appendChild(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  dialog.showModal();
  return dialog;
}

function metricOptions(boot, selected) {
  const groups = {};
  for (const m of boot.metriques) (groups[m.category] ||= []).push(m);
  return Object.entries(groups).map(([cat, items]) => `<optgroup label="${F.escape(cat)}">${items.map((m) =>
    `<option value="${m.key}" ${m.key === selected ? "selected" : ""}>${F.escape(m.label)}</option>`).join("")}</optgroup>`).join("");
}

function fieldHTML(param, value, boot) {
  const id = `f-${param.key}`;
  const label = `<span>${F.escape(param.label)}</span>`;
  switch (param.kind) {
    case "metric":
      return `<label class="field">${label}<select id="${id}" data-key="${param.key}">${metricOptions(boot, value)}</select></label>`;
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
  return `<div class="metric-row" style="display:flex;gap:6px;margin-bottom:6px"><select style="flex:1">${metricOptions(boot, value)}</select>
    <button type="button" class="btn btn-ghost icon-btn" data-remove aria-label="Retirer cette métrique">${icon("close")}</button></div>`;
}

function readForm(form, typeDef) {
  const params = {};
  for (const param of typeDef.params) {
    if (param.kind === "metrics") {
      params[param.key] = [...form.querySelectorAll(`[data-key="${param.key}"] .metric-row select`)].map((s) => s.value);
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
          <label class="field"><span>Largeur</span><select data-w>${[3, 4, 6, 8, 12].map((w) => `<option value="${w}" ${w === tile.w ? "selected" : ""}>${{ 3: "Quart", 4: "Tiers", 6: "Moitié", 8: "Deux tiers", 12: "Toute la largeur" }[w]}</option>`).join("")}</select></label>
          <label class="field"><span>Hauteur</span><select data-h>${[1, 2, 3].map((h) => `<option value="${h}" ${h === tile.h ? "selected" : ""}>${{ 1: "Basse", 2: "Moyenne", 3: "Haute" }[h]}</option>`).join("")}</select></label>
        </div>
      </div>
      <div class="dlg-foot"><button class="btn" value="cancel" type="submit">Annuler</button><button class="btn btn-primary" value="ok" type="submit">Enregistrer</button></div>
    </form>`);
    const form = dialog.querySelector("form");
    form.addEventListener("click", (e) => {
      const add = e.target.closest("[data-add-metric]");
      if (add) add.previousElementSibling.insertAdjacentHTML("beforeend", metricRow(boot, boot.metriques[0].key));
      const remove = e.target.closest("[data-remove]");
      if (remove && remove.closest(".metric-rows").children.length > 1) remove.closest(".metric-row").remove();
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

/** Choix d'un type de tuile. Résout avec le type ou null. */
export function pickTileType(boot) {
  return new Promise((resolve) => {
    const dialog = openDialog(`<div class="dlg">
      <div class="dlg-head"><h2>Ajouter une tuile</h2><p>Choisis ce que la tuile doit montrer ; tu la régleras juste après.</p></div>
      <div class="dlg-body"><div class="type-list">${boot.tuiles.map((t) => `<button class="type-card" type="button" data-type="${t.type}">
        ${icon(t.icone)}<b>${F.escape(t.label)}</b><span>${F.escape(t.description)}</span></button>`).join("")}</div></div>
      <div class="dlg-foot"><button class="btn" type="button" data-cancel>Annuler</button></div></div>`);
    let chosen = null;
    dialog.addEventListener("click", (e) => {
      const card = e.target.closest("[data-type]");
      if (card) { chosen = card.dataset.type; dialog.close(); }
      if (e.target.closest("[data-cancel]")) dialog.close();
    });
    dialog.addEventListener("close", () => resolve(chosen));
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
