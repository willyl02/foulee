// « Réglages coach » : les groupes de niveau (bornes de VMA), la VMA de chaque élève (celle du test du club, ou
// celle qu'il partage) et son groupe, et la bibliothèque des séances types (renommer, modifier, dupliquer,
// proposer, supprimer).
import * as F from "./format.js";
import { icon } from "./icons.js";
import { avatar, blockIntensity, blockRest, blockSize, fail, loading, rdel, rget, rpost, rput, totalMinutes } from "./coach-ui.js";
import { sketchSVG } from "./sketch.js";

export const LEVEL_COLORS = { bleu: "Bleu", vert: "Vert", jaune: "Jaune", orange: "Orange", rouge: "Rouge", violet: "Violet", gris: "Gris" };

/** Pastille d'un groupe (« Groupe 1 »), aux couleurs choisies par le coach. */
export function levelChip(level, { small = false } = {}) {
  if (!level) return "";
  return `<span class="lv-chip lv-${F.escape(level.couleur || "gris")}${small ? " sm" : ""}" title="${F.escape(levelRange(level))}">${F.escape(level.nom)}</span>`;
}

export function levelRange(g) {
  const lo = F.isNum(g.vma_min) ? F.dec1(g.vma_min) : null;
  const hi = F.isNum(g.vma_max) ? F.dec1(g.vma_max) : null;
  if (lo && hi) return `VMA de ${lo} à ${hi} km/h`;
  if (lo) return `VMA ${lo} km/h et plus`;
  if (hi) return `VMA sous ${hi} km/h`;
  return "toutes les VMA";
}

/** Qui va où, à l'écran, avant d'enregistrer (même règle que le relais : club.level_of). */
function levelOf(student, groups) {
  if (student.niveau_force && student.niveau) {
    const kept = groups.find((g) => g.id === student.niveau.id);
    if (kept) return kept;
  }
  const v = student.vma_kmh;
  if (!F.isNum(v)) return null;
  return groups.find((g) => (!F.isNum(g.vma_min) || v >= g.vma_min) && (!F.isNum(g.vma_max) || v < g.vma_max)) || null;
}

/** Des groupes proposés d'après les VMA du groupe : trois tranches d'effectif voisin, bornes à 0,5 km/h. */
function suggest(students) {
  const vmas = students.map((s) => s.vma_kmh).filter(F.isNum).sort((a, b) => b - a);
  const round = (x) => Math.round(x * 2) / 2;
  if (vmas.length < 3) {
    return [{ nom: "Groupe 1", vma_min: 16, vma_max: null, couleur: "rouge" }, { nom: "Groupe 2", vma_min: 14, vma_max: 16, couleur: "orange" },
      { nom: "Groupe 3", vma_min: null, vma_max: 14, couleur: "vert" }];
  }
  let a = round(vmas[Math.floor(vmas.length / 3)]);
  let b = round(vmas[Math.floor((2 * vmas.length) / 3)]);
  if (b >= a) b = a - 1;
  if (a === b) a = b + 0.5;
  return [{ nom: "Groupe 1", vma_min: a, vma_max: null, couleur: "rouge" }, { nom: "Groupe 2", vma_min: b, vma_max: a, couleur: "orange" },
    { nom: "Groupe 3", vma_min: null, vma_max: b, couleur: "vert" }];
}

const numOrNull = (v) => {
  const x = Number(String(v ?? "").replace(",", "."));
  return String(v ?? "").trim() === "" || !Number.isFinite(x) ? null : x;
};

export async function renderCoachSettings(ctx) {
  const { page, toast } = ctx;
  page.innerHTML = `${ctx.head(`<h1>Réglages coach</h1>`, "<span>Tes groupes de niveau et ta bibliothèque de séances</span>")}${ctx.tabs("reglages")}<div class="co-page wide">${loading()}</div>`;
  let data;
  let templates;
  try {
    [data, templates] = await Promise.all([rget("niveaux"), rget("modeles").then((r) => r.modeles)]);
  } catch (err) {
    page.querySelector(".co-page").innerHTML = fail(err.message);
    return;
  }
  let groups = data.niveaux.map((g) => ({ ...g }));
  let dirty = false;

  page.querySelector(".co-page").outerHTML = `<div class="co-page wide">
    <section class="coach-card"><div class="co-card-head"><h2>${icon("club")}Groupes de niveau</h2>
      <span class="co-btools"><button type="button" class="btn btn-ghost btn-small" data-suggest>${icon("bulb")}Proposer des groupes</button>
      <button type="button" class="btn btn-ghost btn-small" data-add-level>${icon("plus")}Ajouter un groupe</button>
      <button type="button" class="btn btn-primary btn-small" data-save-levels disabled>${icon("check")}Enregistrer</button></span></div>
      <p class="hint">Un élève va dans le premier groupe dont les bornes contiennent sa VMA (mini comprise, maxi non comprise ; une case vide ne limite pas). Sa VMA : celle de ton test au club si tu l'as notée, sinon celle qu'il partage depuis Foulée. Tu peux aussi le placer à la main, plus bas.</p>
      <div data-levels></div>
      <div class="lv-preview" data-preview></div>
    </section>
    <section class="coach-card"><h2>${icon("gauge")}VMA et groupe de chaque élève</h2><div data-students></div></section>
    <section class="coach-card"><div class="co-card-head"><h2>${icon("layers")}Bibliothèque de séances <span class="co-count" data-tcount></span></h2>
      <span class="co-btools"><a class="btn btn-small" href="#/coach/proposer?modele=nouveau">${icon("plus")}Nouvelle séance type</a></span></div>
      <p class="hint">Tes séances types : renomme-les, modifie-les, duplique-les pour en faire une variante, ou propose-les en un clic (à un élève ou à tout un groupe). « Enregistrer comme modèle », dans « Proposer une séance », les range ici.</p>
      <div data-library></div></section>
  </div>`;
  const $ = (sel) => page.querySelector(sel);

  // ---------------------------------------------------------------- groupes
  const drawPreview = () => {
    const by = new Map(groups.map((g, i) => [i, []]));
    const none = [];
    data.eleves.forEach((s) => {
      const g = levelOf(s, groups.map((x, i) => ({ ...x, id: x.id ?? `n${i}` })));
      const index = g ? groups.findIndex((x, i) => (x.id ?? `n${i}`) === g.id) : -1;
      if (index >= 0) by.get(index).push(s); else none.push(s);
    });
    const col = (title, chip, list, range) => `<div class="lv-col"><header>${chip || `<b>${F.escape(title)}</b>`}<small>${F.escape(range)} · ${list.length} élève${list.length > 1 ? "s" : ""}</small></header>
      ${list.length ? list.map((s) => `<span class="lv-who">${avatar(s.nom, { size: "sm" })}${F.escape(s.nom)}<small>${F.isNum(s.vma_kmh) ? F.dec1(s.vma_kmh) : "–"}</small></span>`).join("") : `<span class="muted">personne</span>`}</div>`;
    $("[data-preview]").innerHTML = groups.length || none.length
      ? `${groups.map((g, i) => col(g.nom, levelChip(g), by.get(i), levelRange(g))).join("")}${none.length ? col("Sans groupe", "", none, "VMA inconnue ou hors des bornes") : ""}` : "";
  };
  const drawLevels = () => {
    $("[data-levels]").innerHTML = groups.length ? `<div class="co-table-wrap"><table class="coach-table lv-table"><thead><tr><th>Nom</th><th>VMA mini</th><th>VMA maxi</th><th>Couleur</th><th></th></tr></thead><tbody>
      ${groups.map((g, i) => `<tr data-level="${i}">
        <td><input type="text" data-k="nom" maxlength="40" value="${F.escape(g.nom || "")}" placeholder="ex. Groupe 1"></td>
        <td><input type="text" inputmode="decimal" data-k="vma_min" value="${F.isNum(g.vma_min) ? F.dec1(g.vma_min) : ""}" placeholder="aucune"></td>
        <td><input type="text" inputmode="decimal" data-k="vma_max" value="${F.isNum(g.vma_max) ? F.dec1(g.vma_max) : ""}" placeholder="aucune"></td>
        <td><select data-k="couleur">${Object.entries(LEVEL_COLORS).map(([k, l]) => `<option value="${k}" ${k === g.couleur ? "selected" : ""}>${l}</option>`).join("")}</select></td>
        <td><span class="co-btools">${i ? `<button type="button" class="co-mini" data-up title="Monter ce groupe d'un cran" aria-label="Monter">${icon("moveup")}</button>` : ""}<button type="button" class="co-mini" data-drop title="Supprimer ce groupe" aria-label="Supprimer">${icon("trash")}</button></span></td></tr>`).join("")}
      </tbody></table></div>`
      : `<p class="co-empty">Pas encore de groupe. « Proposer des groupes » en crée trois d'après les VMA de tes élèves ; tu pourras les renommer et ajuster leurs bornes.</p>`;
    $("[data-levels]").querySelectorAll("[data-level]").forEach((tr) => {
      const i = Number(tr.dataset.level);
      tr.addEventListener("input", (e) => {
        const k = e.target.dataset.k;
        if (!k) return;
        groups[i][k] = k.startsWith("vma") ? numOrNull(e.target.value) : e.target.value;
        setDirty();
        drawPreview();
      });
      tr.querySelector("[data-drop]").addEventListener("click", () => { groups.splice(i, 1); setDirty(); drawLevels(); });
      tr.querySelector("[data-up]")?.addEventListener("click", () => { [groups[i - 1], groups[i]] = [groups[i], groups[i - 1]]; setDirty(); drawLevels(); });
    });
    drawPreview();
  };
  const setDirty = () => { dirty = true; $("[data-save-levels]").disabled = false; };
  $("[data-add-level]").addEventListener("click", () => {
    const colors = Object.keys(LEVEL_COLORS);
    groups.push({ nom: `Groupe ${groups.length + 1}`, vma_min: null, vma_max: null, couleur: colors[groups.length % colors.length] });
    setDirty();
    drawLevels();
  });
  $("[data-suggest]").addEventListener("click", () => {
    if (groups.length && !window.confirm("Remplacer tes groupes par trois groupes calculés d'après les VMA de tes élèves ?")) return;
    groups = suggest(data.eleves).map((g, i) => ({ ...g, id: groups[i]?.id }));
    setDirty();
    drawLevels();
  });
  $("[data-save-levels]").addEventListener("click", async () => {
    const button = $("[data-save-levels]");
    button.disabled = true;
    try {
      data = await rput("niveaux", { niveaux: groups });
      groups = data.niveaux.map((g) => ({ ...g }));
      dirty = false;
      drawLevels();
      drawStudents();
      toast("Groupes enregistrés.");
    } catch (err) { toast(err.message); button.disabled = false; }
  });

  // ---------------------------------------------------------------- élèves
  function drawStudents() {
    const saved = data.niveaux;
    $("[data-students]").innerHTML = data.eleves.length ? `<div class="co-table-wrap"><table class="coach-table lv-students"><thead><tr><th>Élève</th><th>VMA partagée</th><th>VMA du test club</th><th>VMA retenue</th><th>Groupe</th></tr></thead><tbody>
      ${data.eleves.map((s) => `<tr data-sid="${s.id}">
        <td><a href="#/coach/eleve/${s.id}" class="lv-who">${avatar(s.nom, { size: "sm" })}<b>${F.escape(s.nom)}</b></a></td>
        <td>${F.isNum(s.vma_partagee) ? `${F.dec1(s.vma_partagee)} km/h` : `<span class="muted">non partagée</span>`}</td>
        <td><span class="lv-test"><input type="text" inputmode="decimal" data-test value="${F.isNum(s.vma_test) ? F.dec1(s.vma_test) : ""}" placeholder="ex. 15,5" aria-label="VMA du test club de ${F.escape(s.nom)}">
          <small>${s.vma_test_le ? `notée le ${F.escape(F.dateShort(s.vma_test_le))}` : ""}</small></span></td>
        <td>${F.isNum(s.vma_kmh) ? `<b>${F.dec1(s.vma_kmh)}</b> <small class="muted">${s.vma_source === "test" ? "test club" : "partagée"}</small>` : "–"}</td>
        <td><select data-level aria-label="Groupe de ${F.escape(s.nom)}"><option value="">${s.niveau && !s.niveau_force ? `Selon sa VMA : ${F.escape(s.niveau.nom)}` : "Selon sa VMA"}</option>
          ${saved.map((g) => `<option value="${g.id}" ${s.niveau_force && s.niveau?.id === g.id ? "selected" : ""}>${F.escape(g.nom)} (à la main)</option>`).join("")}</select></td>
      </tr>`).join("")}</tbody></table></div>
      <p class="hint">La VMA de ton test (VAMEVAL, demi-Cooper…) passe avant celle que l'élève partage : c'est elle qui range l'élève dans un groupe, et elle sert à ses allures sur la montre s'il n'a pas de VMA dans Foulée. Laisse vide pour reprendre la sienne.</p>`
      : `<p class="co-empty">Ton groupe est vide : <a href="#/coach">invite un élève</a> d'abord.</p>`;
    $("[data-students]").querySelectorAll("[data-sid]").forEach((tr) => {
      const sid = tr.dataset.sid;
      const save = async (body, what) => {
        try {
          data = await rput(`eleves/${sid}/niveau`, body);
          if (!dirty) groups = data.niveaux.map((g) => ({ ...g }));
          drawStudents();
          drawPreview();
          toast(what);
        } catch (err) { toast(err.message); }
      };
      const test = tr.querySelector("[data-test]");
      test.addEventListener("change", () => save({ vma_test: test.value.trim() }, test.value.trim() ? "VMA du test enregistrée." : "VMA du test retirée : on reprend la sienne."));
      tr.querySelector("[data-level]").addEventListener("change", (e) => save({ niveau: e.target.value }, e.target.value ? "Élève placé dans ce groupe." : "Groupe selon sa VMA."));
    });
  }

  // ---------------------------------------------------------------- bibliothèque
  function drawLibrary() {
    $("[data-tcount]").textContent = templates.length || "";
    $("[data-library]").innerHTML = templates.length ? `<div class="lib">${templates.map((t) => {
      const total = totalMinutes(t.blocs, 15);
      return `<article class="lib-item" data-tid="${t.id}">
        <div class="lib-main"><span class="co-ico">${icon(t.sport === "renfo" ? "dumbbell" : "run")}</span>
          <div class="lib-text"><b data-title>${F.escape(t.titre)}</b>
            <span>${F.escape(t.blocs.map((b) => [blockSize(b), blockIntensity(b), blockRest(b)].filter(Boolean).join(" ")).join(" · "))}</span>
            ${total.minutes ? `<small>≈ ${F.escape(F.duration(total.minutes * 60, { short: true }))}${t.consigne ? ` · « ${F.escape(t.consigne)} »` : ""}</small>` : ""}</div></div>
        <div class="lib-sk">${t.sport !== "renfo" ? sketchSVG(t.blocs, { height: 26 }) : ""}</div>
        <div class="co-btools lib-tools">
          <a class="btn btn-small btn-primary" href="#/coach/proposer?modele=${t.id}">${icon("plus")}Proposer</a>
          <a class="btn btn-small btn-ghost" href="#/coach/proposer?modele=${t.id}&edition=1">${icon("layers")}Modifier</a>
          <button type="button" class="btn btn-small btn-ghost" data-rename>${icon("edit")}Renommer</button>
          <button type="button" class="btn btn-small btn-ghost" data-copy>${icon("copy")}Dupliquer</button>
          <button type="button" class="co-mini" data-drop title="Supprimer ce modèle">${icon("trash")}</button></div>
      </article>`;
    }).join("")}</div>`
      : `<p class="co-empty">Ta bibliothèque est vide. Compose une séance dans « Proposer une séance », puis « Enregistrer comme modèle » ; ou crée directement une « Nouvelle séance type ».</p>`;
    $("[data-library]").querySelectorAll("[data-tid]").forEach((el) => {
      const t = templates.find((x) => String(x.id) === el.dataset.tid);
      el.querySelector("[data-rename]").addEventListener("click", () => {
        // Renommer sur place : Entrée enregistre, Échap annule
        const title = el.querySelector("[data-title]");
        title.outerHTML = `<form class="lib-rename" data-rename-form><input type="text" maxlength="80" value="${F.escape(t.titre)}" aria-label="Nouveau nom">
          <button type="submit" class="btn btn-small btn-primary">${icon("check")}OK</button><button type="button" class="btn btn-small btn-ghost" data-cancel>Annuler</button></form>`;
        const form = el.querySelector("[data-rename-form]");
        const input = form.querySelector("input");
        input.focus();
        input.select();
        form.querySelector("[data-cancel]").addEventListener("click", drawLibrary);
        input.addEventListener("keydown", (e) => { if (e.key === "Escape") drawLibrary(); });
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          const name = input.value.trim();
          if (!name || name === t.titre) { drawLibrary(); return; }
          try { templates = (await rput(`modeles/${t.id}`, { titre: name })).modeles; drawLibrary(); toast("Séance type renommée."); }
          catch (err) { toast(err.message); input.focus(); }
        });
      });
      el.querySelector("[data-copy]").addEventListener("click", async () => {
        let name = `${t.titre} (copie)`;
        for (let n = 2; templates.some((x) => x.titre === name); n += 1) name = `${t.titre} (copie ${n})`;
        try {
          templates = (await rpost("modeles", { titre: name.slice(0, 80), sport: t.sport, blocs: t.blocs, consigne: t.consigne })).modeles;
          drawLibrary();
          toast(`« ${name} » ajoutée : modifie-la pour en faire une variante.`);
        } catch (err) { toast(err.message); }
      });
      el.querySelector("[data-drop]").addEventListener("click", async () => {
        if (!window.confirm(`Supprimer la séance type « ${t.titre} » ? Les séances déjà proposées ne changent pas.`)) return;
        try { templates = (await rdel(`modeles/${t.id}`)).modeles; drawLibrary(); } catch (err) { toast(err.message); }
      });
    });
  }

  drawLevels();
  drawStudents();
  drawLibrary();
}
