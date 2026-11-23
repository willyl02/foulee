// Proposer une séance (coach) : un déroulé en blocs, en % de VMA ou en zone de FC, envoyé à un ou plusieurs élèves.
// Chaque élève la reçoit dans son calendrier, avec ses allures à lui (calculées avec sa VMA).
import * as api from "./api.js";
import { levelRange } from "./coach-reglages.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { B, blockForm, clone, EXAMPLES, readBlock, SPORTS } from "./bloc-editor.js";
import {
  avatar, blockIntensity, blockRest, blockSize, blocksHtml, fail, loading, paceFor, rdel, rget, rpost, rput, totalMinutes,
  watchSummary,
} from "./coach-ui.js";

export async function renderEditor(ctx) {
  const { page, params, toast } = ctx;
  const editId = /^\d+$/.test(params.get("id") || "") ? Number(params.get("id")) : null;
  const editStudent = /^\d+$/.test(params.get("eleve") || "") ? Number(params.get("eleve")) : null;
  const tplParam = params.get("modele") || "";
  // Bibliothèque : « Nouvelle séance type » (modele=nouveau) ou « Modifier » (modele=<id>&edition=1) : on édite le
  // modèle lui-même, sans élève ni envoi
  const tplMode = tplParam === "nouveau" ? "new" : /^\d+$/.test(tplParam) && params.get("edition") === "1" ? "edit" : null;
  const tplTitle = tplMode === "new" ? "Nouvelle séance type" : tplMode === "edit" ? "Modifier la séance type" : null;
  page.innerHTML = `${ctx.head(`<h1>${tplTitle || (editId ? "Modifier une séance" : "Proposer une séance")}</h1>`)}${ctx.tabs(tplMode ? "reglages" : "proposer")}<div class="co-page wide">${loading()}</div>`;
  const [group, saved] = await Promise.all([rget("groupe"), rget("modeles").then((r) => r.modeles).catch(() => [])]);
  // Groupés par niveau (s'il y en a), puis par VMA décroissante : on coche un groupe d'un clic
  const students = [...group.eleves].sort((a, b) => (a.niveau ? 0 : 1) - (b.niveau ? 0 : 1)
    || (b.vma_kmh || 0) - (a.vma_kmh || 0) || a.nom.localeCompare(b.nom, "fr"));
  const levelList = [];
  students.forEach((s) => { if (s.niveau && !levelList.some((g) => g.id === s.niveau.id)) levelList.push(s.niveau); });
  let templates = saved;
  const tomorrow = F.isoDate(F.addDays(new Date(), 1));
  const state = { eleves: new Set(), date: /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : tomorrow, ...clone(EXAMPLES[1]) };
  (params.get("eleves") || "").split(",").map(Number).filter((id) => students.some((s) => s.id === id)).forEach((id) => state.eleves.add(id));
  const groupParam = Number(params.get("groupe")) || null;
  if (groupParam) students.filter((s) => s.niveau?.id === groupParam).forEach((s) => state.eleves.add(s.id));
  const startTpl = /^\d+$/.test(tplParam) ? templates.find((t) => t.id === Number(tplParam)) : null;
  if (tplParam && /^\d+$/.test(tplParam) && !startTpl) {
    page.innerHTML = `${ctx.head(`<h1>${tplTitle || "Proposer une séance"}</h1>`)}${ctx.tabs("reglages")}<div class="co-page">${fail("Cette séance type n'existe plus.")}</div>`;
    return;
  }
  if (startTpl) Object.assign(state, { titre: startTpl.titre, sport: startTpl.sport || "course", blocs: clone(startTpl.blocs), consigne: startTpl.consigne || "" });
  if (tplMode === "new") Object.assign(state, { titre: "", sport: "course", consigne: "", blocs: clone(EXAMPLES[1].blocs) });

  let editSent = false; // déjà sur sa montre : le relais la renvoie tout seul, modifiée
  const watchers = students.filter((s) => s.montre?.relie && s.montre.coach_peut_envoyer);
  if (editId && editStudent) {
    const fiche = await rget(`eleves/${editStudent}/fiche`);
    const p = fiche.propositions.find((x) => x.id === editId);
    if (!p) {
      page.innerHTML = `${ctx.head(`<h1>Modifier une séance</h1>`)}${ctx.tabs("proposer")}<div class="co-page">${fail("Cette séance proposée n'existe plus (ou elle est trop ancienne).")}</div>`;
      return;
    }
    Object.assign(state, { date: p.date, titre: p.titre, sport: p.sport, blocs: clone(p.blocs), consigne: p.consigne || "" });
    state.eleves = new Set([editStudent]);
    editSent = Boolean(p.montre);
  }
  if (!editId && !tplMode && students.length === 1) state.eleves.add(students[0].id);

  const headActions = tplMode
    ? `<a class="btn" href="#/coach/reglages">${icon("left")}Bibliothèque</a><button class="btn btn-primary" type="button" data-save-model>${icon("check")}Enregistrer la séance type</button>`
    : `<button class="btn" type="button" data-save-tpl>${icon("layers")}Enregistrer comme modèle</button><button class="btn btn-primary" type="button" data-send>${icon("check")}<span data-send-label>Envoyer</span></button>`;
  page.innerHTML = `${ctx.head(`<h1>${tplTitle || (editId ? "Modifier une séance" : "Proposer une séance")}</h1>`,
    `<span>${tplMode ? "Elle reste dans ta bibliothèque : tu la proposeras quand tu voudras, à un élève ou à tout un groupe." : editId ? "L'élève voit la nouvelle version dans son calendrier à sa prochaine synchro." : "Elle arrive dans le calendrier de chaque élève choisi, avec ses allures à lui."}</span>`,
    headActions)}
    ${ctx.tabs(tplMode ? "reglages" : "proposer")}
    <div class="co-grid2 editor">
      <div class="co-page">
        ${tplMode ? "" : `<section class="coach-card"><h2>${icon("club")}Pour qui</h2>
          ${students.length ? `${!editId && levelList.length ? `<div class="co-levels-pick"><span>Cocher un groupe :</span>${levelList.map((g) => `<button type="button" class="lv-pick lv-${F.escape(g.couleur || "gris")}" data-level-pick="${g.id}" title="${F.escape(levelRange(g))}">${F.escape(g.nom)}<small>${students.filter((s) => s.niveau?.id === g.id).length}</small></button>`).join("")}</div>` : ""}
            <div class="co-pick" data-pick>${students.map((s) => `<label class="co-pickone${editId ? " locked" : ""}"><input type="checkbox" value="${s.id}" ${state.eleves.has(s.id) ? "checked" : ""} ${editId ? "disabled" : ""}>
            ${avatar(s.nom, { size: "sm" })}<span>${F.escape(s.nom)}${s.montre?.relie && s.montre.coach_peut_envoyer ? `<i class="co-watchmini" title="Montre Garmin reliée">${icon("watch")}</i>` : ""}<small>${s.vma_kmh ? `VMA ${F.dec1(s.vma_kmh)}${s.vma_source === "test" ? " (test)" : ""}` : "VMA inconnue"}${s.niveau ? ` · ${F.escape(s.niveau.nom)}` : ""}</small></span></label>`).join("")}</div>
            ${!editId && students.length > 1 ? `<div class="inline-actions" style="margin:8px 0 0"><button type="button" class="btn btn-ghost btn-small" data-all>Tout le groupe</button><button type="button" class="btn btn-ghost btn-small" data-none>Personne</button></div>` : ""}`
          : `<p class="co-empty">Ton groupe est vide : <a href="#/coach">invite un élève</a> d'abord.</p>`}
          ${watchers.length && !editSent ? `<label class="co-check"><input type="checkbox" data-to-watch checked><span>${icon("watch")} Envoyer aussi sur leur montre Garmin (élèves qui l'ont reliée : ${F.escape(watchers.map((w) => w.nom.split(" ")[0]).join(", "))})</span></label>` : ""}
          ${editSent ? `<p class="hint" style="margin:8px 0 0">${icon("watch")} Déjà sur sa montre : elle y sera remplacée par la version modifiée.</p>` : ""}
        </section>`}
        <section class="coach-card"><h2>${icon("edit")}La séance</h2>
          <div class="co-form3${tplMode ? " no-date" : ""}">
            <label class="field"${tplMode ? " hidden" : ""}><span>Date</span><input type="date" data-f="date" value="${state.date}"></label>
            <label class="field"><span>Sport</span><select data-f="sport">${SPORTS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select></label>
            <label class="field co-wide"><span>Titre</span><input type="text" data-f="titre" maxlength="80" placeholder="ex. Seuil 3 × 10 min"></label>
          </div>
          <p class="co-lbl">Déroulé</p><div class="co-bforms" data-blocks></div>
          <div class="inline-actions" style="margin:10px 0 4px"><button type="button" class="btn btn-ghost" data-add>${icon("plus")}Ajouter un bloc</button><span class="muted" data-total></span></div>
          <label class="field"><span>Consigne (facultatif)</span><textarea data-f="consigne" rows="3" maxlength="1500" placeholder="Ce qui compte dans cette séance, en une ou deux phrases."></textarea></label>
        </section>
      </div>
      <div class="co-page">
        <section class="coach-card"><h2>${icon("gauge")}${tplMode ? "Les allures, pour exemple" : "Les allures de chacun"}</h2><div data-paces></div></section>
        <section class="coach-card"><h2>${icon("eye")}Ce que l'élève verra</h2><div data-preview></div></section>
        ${tplMode ? "" : `<section class="coach-card"><h2>${icon("layers")}Partir d'un modèle</h2><div data-templates></div></section>`}
      </div>
    </div>`;

  const $ = (sel) => page.querySelector(sel);
  const blocksBox = $("[data-blocks]");
  const field = (k) => page.querySelector(`[data-f="${k}"]`);
  const fill = () => {
    field("date").value = state.date;
    field("sport").value = state.sport || "course";
    field("titre").value = state.titre || "";
    field("consigne").value = state.consigne || "";
    drawBlocks();
  };
  const collect = () => {
    const old = state.blocs;
    state.blocs = [...blocksBox.querySelectorAll("[data-block]")].map((el, i) => readBlock(el, old[i]));
    state.date = field("date").value;
    state.sport = field("sport").value;
    state.titre = field("titre").value.trim();
    state.consigne = field("consigne").value.trim();
  };
  // Les allures, comme l'élève et sa montre les auront : sa VMA à lui s'il la partage, sinon celle du test du club
  const chosen = () => (tplMode ? [{ id: 0, nom: "VMA 15 km/h (exemple)", vma_kmh: 15 }]
    : students.filter((s) => state.eleves.has(s.id)).map((s) => ({ ...s, vma_kmh: s.vma_partagee || s.vma_kmh })));

  const drawSide = () => {
    const list = chosen();
    page.querySelectorAll("[data-level-pick]").forEach((btn) => {
      const members = students.filter((s) => s.niveau?.id === Number(btn.dataset.levelPick));
      btn.setAttribute("aria-pressed", String(members.length > 0 && members.every((s) => state.eleves.has(s.id))));
    });
    const label = $("[data-send-label]") || {};
    label.textContent = editId ? "Enregistrer" : list.length > 1 ? `Envoyer à ${list.length} élèves` : list.length ? `Envoyer à ${list[0].nom.split(" ")[0]}` : "Envoyer";
    const paced = state.blocs.map((b, i) => [b, i]).filter(([b]) => b.pct_vma);
    $("[data-paces]").innerHTML = !list.length ? `<p class="co-empty">Choisis au moins un élève.</p>`
      : !paced.length ? `<p class="co-empty">Aucun bloc en % de VMA : rien à calculer.</p>`
        : `<div class="co-table-wrap"><table class="co-paces"><thead><tr><th>Élève</th><th>VMA</th>${paced.map(([b]) => `<th>${F.escape(b.nom || "Bloc")}<small>${(b.repetitions || 1) > 1 ? `${b.repetitions} × ` : ""}${b.pct_vma} %</small></th>`).join("")}</tr></thead><tbody>
          ${list.map((s) => `<tr><td><b>${F.escape(s.nom)}</b></td><td>${s.vma_kmh ? F.dec1(s.vma_kmh) : "–"}</td>${paced.map(([b]) => `<td class="f">${s.vma_kmh ? paceFor(s.vma_kmh, b.pct_vma) : "–"}</td>`).join("")}</tr>`).join("")}
          </tbody></table></div>${list.some((s) => !s.vma_kmh) ? `<p class="hint" style="margin:8px 0 0">Sans VMA partagée, l'élève voit les pourcentages, sans allure.</p>` : ""}
          ${list.some((s) => s.vma_test && s.vma_partagee && Math.abs(s.vma_test - s.vma_partagee) >= 0.3) ? `<p class="hint" style="margin:8px 0 0">Allures calculées avec la VMA de l'élève, celle de son appli et de sa montre ; ton test du club sert à le classer dans un groupe.</p>` : ""}`;
    const first = list.find((s) => s.vma_kmh) || list[0];
    const t = totalMinutes(state.blocs, first?.vma_kmh);
    $("[data-total]").textContent = t.minutes ? `Durée totale : ${F.duration(t.minutes * 60, { short: true })}${t.km ? ` · environ ${F.dec1(t.km)} km${list.length > 1 && first ? ` (pour ${first.nom.split(" ")[0]})` : ""}` : ""}` : "";
    $("[data-preview]").innerHTML = `<div class="co-prevcard"><div class="co-prevhead"><b>${F.escape(state.titre || "Titre de la séance")}</b>
        <span>${F.escape(state.date && !tplMode ? F.dateLong(state.date) : "")}${first ? `${tplMode ? "" : " · "}pour ${F.escape(first.nom)}` : ""}</span></div>
      ${blocksHtml(state.blocs, first?.vma_kmh)}${state.consigne ? `<p class="co-consigne">« ${F.escape(state.consigne)} »</p>` : ""}</div>`;
  };

  function drawBlocks() {
    blocksBox.innerHTML = state.blocs.map((b, i) => blockForm(b, i, state.blocs.length)).join("");
    blocksBox.querySelectorAll("[data-block]").forEach((el) => {
      const i = Number(el.dataset.block);
      el.addEventListener("input", () => { collect(); drawSide(); });
      el.addEventListener("change", (e) => {
        collect();
        if (["effort", "repetitions", "genre", "unit", "restunit"].includes(e.target.dataset.k)) {
          if (e.target.dataset.k === "effort" && e.target.value === "vma" && !state.blocs[i].pct_vma) state.blocs[i].pct_vma = 70;
          drawBlocks();
        } else drawSide();
      });
      el.querySelector("[data-del]").addEventListener("click", () => { collect(); state.blocs.splice(i, 1); drawBlocks(); });
      el.querySelector("[data-dup]").addEventListener("click", () => { collect(); state.blocs.splice(i + 1, 0, clone(state.blocs[i])); drawBlocks(); });
      el.querySelectorAll("[data-move]").forEach((btn) => btn.addEventListener("click", () => {
        collect();
        const j = i + Number(btn.dataset.move);
        [state.blocs[i], state.blocs[j]] = [state.blocs[j], state.blocs[i]];
        drawBlocks();
      }));
    });
    drawSide();
  }

  const drawTemplates = () => {
    if (!$("[data-templates]")) return;
    const row = (t, i, mine) => `<div class="co-tpl"><span class="co-ico">${icon(t.sport === "renfo" ? "dumbbell" : "run")}</span>
      <div><b>${F.escape(t.titre)}</b><span>${F.escape(t.blocs.map((b) => [blockSize(b), blockIntensity(b), blockRest(b)].filter(Boolean).join(" ")).join(" · "))}</span></div>
      <span class="co-btools"><button type="button" class="btn btn-small btn-ghost" data-use="${mine ? "m" : "x"}${i}">Utiliser</button>
      ${mine ? `<button type="button" class="co-mini" data-drop-tpl="${t.id}" title="Supprimer ce modèle">${icon("trash")}</button>` : ""}</span></div>`;
    $("[data-templates]").innerHTML = `${templates.length ? `<p class="co-lbl">Mes modèles</p>${templates.map((t, i) => row(t, i, true)).join("")}` : `<p class="co-empty">Pas encore de modèle à toi : compose une séance, puis « Enregistrer comme modèle ».</p>`}
      <p class="co-lbl" style="margin-top:12px">Exemples</p>${EXAMPLES.map((t, i) => row(t, i, false)).join("")}`;
    $("[data-templates]").querySelectorAll("[data-use]").forEach((btn) => btn.addEventListener("click", () => {
      const id = btn.dataset.use;
      const t = id[0] === "m" ? templates[Number(id.slice(1))] : EXAMPLES[Number(id.slice(1))];
      Object.assign(state, { titre: t.titre, sport: t.sport || "course", blocs: clone(t.blocs), consigne: t.consigne || "" });
      fill();
      toast(`Modèle « ${t.titre} » chargé : ajuste-le si besoin.`);
      page.querySelector("[data-blocks]").scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    $("[data-templates]").querySelectorAll("[data-drop-tpl]").forEach((btn) => btn.addEventListener("click", async () => {
      if (!window.confirm("Supprimer ce modèle ?")) return;
      try { templates = (await rdel(`modeles/${btn.dataset.dropTpl}`)).modeles; drawTemplates(); } catch (err) { toast(err.message); }
    }));
  };

  page.querySelectorAll("[data-level-pick]").forEach((btn) => btn.addEventListener("click", () => {
    const members = students.filter((s) => s.niveau?.id === Number(btn.dataset.levelPick));
    const allIn = members.every((s) => state.eleves.has(s.id));
    members.forEach((s) => (allIn ? state.eleves.delete(s.id) : state.eleves.add(s.id)));
    page.querySelectorAll("[data-pick] input").forEach((box) => { box.checked = state.eleves.has(Number(box.value)); });
    drawSide();
  }));
  page.querySelectorAll("[data-pick] input").forEach((box) => box.addEventListener("change", () => {
    if (box.checked) state.eleves.add(Number(box.value)); else state.eleves.delete(Number(box.value));
    drawSide();
  }));
  const setAll = (on) => page.querySelectorAll("[data-pick] input").forEach((box) => { box.checked = on; if (on) state.eleves.add(Number(box.value)); else state.eleves.delete(Number(box.value)); });
  $("[data-all]")?.addEventListener("click", () => { setAll(true); drawSide(); });
  $("[data-none]")?.addEventListener("click", () => { setAll(false); drawSide(); });
  ["date", "sport", "titre", "consigne"].forEach((k) => field(k).addEventListener("input", () => { collect(); drawSide(); }));
  $("[data-add]").addEventListener("click", () => {
    collect();
    const last = state.blocs.at(-1);
    state.blocs.push(last?.genre === "calme" ? B("corps", "", { duree_min: 10, pct_vma: 75 }) : B("calme", "Retour au calme", { duree_min: 10, pct_vma: 60 }));
    drawBlocks();
  });

  $("[data-save-model]")?.addEventListener("click", async () => {
    collect();
    if (!state.titre) { toast("Donne un titre à la séance type."); field("titre").focus(); return; }
    const body = { titre: state.titre, sport: state.sport, blocs: state.blocs, consigne: state.consigne };
    try {
      if (tplMode === "edit") await rput(`modeles/${startTpl.id}`, body);
      else {
        if (templates.some((t) => t.titre === state.titre) && !window.confirm(`Tu as déjà une séance type « ${state.titre} » : la remplacer ?`)) return;
        await rpost("modeles", body);
      }
      toast(`Séance type « ${state.titre} » enregistrée.`);
      location.hash = "#/coach/reglages";
    } catch (err) { toast(err.message); }
  });

  $("[data-save-tpl]")?.addEventListener("click", async () => {
    collect();
    if (!state.titre) { toast("Donne d'abord un titre à la séance : ce sera le nom du modèle."); field("titre").focus(); return; }
    try {
      templates = (await rpost("modeles", { titre: state.titre, sport: state.sport, blocs: state.blocs, consigne: state.consigne })).modeles;
      drawTemplates();
      toast(`Modèle « ${state.titre} » enregistré.`);
    } catch (err) { toast(err.message); }
  });

  $("[data-send]")?.addEventListener("click", async () => {
    collect();
    const list = chosen();
    if (!list.length) { toast("Choisis au moins un élève."); return; }
    if (!state.titre) { toast("Donne un titre à la séance."); field("titre").focus(); return; }
    const button = $("[data-send]");
    button.disabled = true;
    const body = { eleves: list.map((s) => s.id), date: state.date, titre: state.titre, sport: state.sport, blocs: state.blocs, consigne: state.consigne };
    try {
      let ids = [];
      if (editId) { await rput(`propositions/${editId}`, body); ids = [editId]; }
      else ids = ((await rpost("propositions", body)).propositions || []).map((p) => p.id);
      const names = list.map((s) => s.nom.split(" ")[0]);
      let watched = "";
      if ($("[data-to-watch]")?.checked && list.some((s) => watchers.includes(s))) {
        try { watched = ` ${watchSummary(await api.post("/api/coach/montres", { propositions: ids }))}`; }
        catch (err) { watched = ` Montres : ${err.message}`; }
      }
      toast((editId ? "Séance modifiée." : `Séance envoyée à ${names.length > 2 ? `${names.length} élèves` : names.join(" et ")} : elle arrive dans ${names.length > 1 ? "leur" : "son"} calendrier.`) + watched);
      location.hash = list.length === 1 ? `#/coach/eleve/${list[0].id}` : "#/coach";
    } catch (err) {
      toast(err.message);
      button.disabled = false;
    }
  });

  fill();
  drawTemplates();
}
