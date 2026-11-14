// Proposer une séance (coach) : un déroulé en blocs, en % de VMA ou en zone de FC, envoyé à un ou plusieurs élèves.
// Chaque élève la reçoit dans son calendrier, avec ses allures à lui (calculées avec sa VMA).
import * as F from "./format.js";
import { icon } from "./icons.js";
import {
  avatar, blockIntensity, blockRest, blockSize, blocksHtml, fail, GENRES, loading, paceFor, rdel, rget, rpost, rput, totalMinutes,
} from "./coach-ui.js";

const SPORTS = [["course", "Course à pied"], ["trail", "Trail"], ["velo", "Vélo"], ["natation", "Natation"], ["renfo", "Renforcement"],
  ["cardio", "Cardio / HIIT"], ["souplesse", "Souplesse / yoga"], ["marche", "Marche"], ["autre", "Autre"]];

const B = (genre, nom, extra) => ({ genre, nom, repetitions: 1, ...extra });
const EXAMPLES = [
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

const clone = (x) => JSON.parse(JSON.stringify(x));
const num = (v) => { const n = Number(String(v).replace(",", ".")); return Number.isFinite(n) && n > 0 ? n : null; };
const show = (n) => (n == null ? "" : String(Math.round(n * 100) / 100).replace(".", ","));

function blockForm(b, i, n) {
  const genre = GENRES[b.genre] || GENRES.corps;
  const qtyUnit = b.distance_m ? (b.distance_m >= 1000 && b.distance_m % 100 === 0 ? "km" : "m") : (b.duree_min && b.duree_min < 1 ? "s" : "min");
  const qty = qtyUnit === "km" ? b.distance_m / 1000 : qtyUnit === "m" ? b.distance_m : qtyUnit === "s" ? Math.round((b.duree_min || 0) * 60) : b.duree_min;
  const effort = b.pct_vma ? "vma" : b.zone_fc ? "fc" : "aucune";
  const restUnit = b.recup_min && b.recup_min < 1 ? "s" : "min";
  const rest = restUnit === "s" ? Math.round(b.recup_min * 60) : b.recup_min;
  return `<div class="co-bform" data-block="${i}" style="--genre:${genre.color}">
    <div class="co-brow">
      <select data-k="genre" aria-label="Type de bloc">${Object.entries(GENRES).map(([k, g]) => `<option value="${k}" ${k === (b.genre || "corps") ? "selected" : ""}>${g.label}</option>`).join("")}</select>
      <input data-k="nom" type="text" maxlength="60" value="${F.escape(b.nom || "")}" placeholder="Nom du bloc" aria-label="Nom du bloc">
      <span class="co-reps"><input data-k="repetitions" type="number" min="1" max="50" value="${b.repetitions || 1}" aria-label="Répétitions"><span>×</span></span>
      <span class="co-qty"><input data-k="qty" type="text" inputmode="decimal" value="${F.escape(show(qty))}" placeholder="durée" aria-label="Durée ou distance">
        <select data-k="unit" aria-label="Unité">${["min", "s", "m", "km"].map((u) => `<option ${u === qtyUnit ? "selected" : ""}>${u}</option>`).join("")}</select></span>
    </div>
    <div class="co-brow sub">
      <span class="co-effort"><select data-k="effort" aria-label="Intensité"><option value="vma" ${effort === "vma" ? "selected" : ""}>% VMA</option><option value="fc" ${effort === "fc" ? "selected" : ""}>Zone FC</option><option value="aucune" ${effort === "aucune" ? "selected" : ""}>Sans intensité</option></select>
        ${effort === "vma" ? `<input data-k="pct_vma" type="number" min="30" max="140" value="${b.pct_vma ?? ""}" aria-label="Pourcentage de VMA"><span>%</span>`
          : effort === "fc" ? `<input data-k="zone_fc" type="number" min="1" max="5" value="${b.zone_fc ?? ""}" aria-label="Zone de FC">` : ""}</span>
      ${(b.repetitions || 1) > 1 ? `<span class="co-rest"><span>récup</span><input data-k="rest" type="text" inputmode="decimal" value="${F.escape(show(rest))}" aria-label="Récupération">
        <select data-k="restunit" aria-label="Unité de récupération">${["min", "s"].map((u) => `<option ${u === restUnit ? "selected" : ""}>${u}</option>`).join("")}</select>
        <input data-k="recup_texte" type="text" maxlength="40" value="${F.escape(b.recup_texte || "")}" placeholder="trot, marche…" aria-label="Façon de récupérer"></span>` : ""}
      <input data-k="note" class="co-note" type="text" maxlength="200" value="${F.escape(b.note || "")}" placeholder="Précision (facultatif)" aria-label="Précision">
    </div>
    <span class="co-bside">
      <button type="button" class="co-mini co-flip" data-move="-1" ${i === 0 ? "disabled" : ""} title="Monter">${icon("chevron")}</button>
      <button type="button" class="co-mini" data-dup title="Dupliquer">${icon("copy")}</button>
      <button type="button" class="co-mini" data-move="1" ${i === n - 1 ? "disabled" : ""} title="Descendre">${icon("chevron")}</button>
      <button type="button" class="co-mini" data-del ${n === 1 ? "disabled" : ""} title="Supprimer">${icon("trash")}</button></span></div>`;
}

function readBlock(el, old) {
  const v = (k) => el.querySelector(`[data-k="${k}"]`)?.value ?? "";
  const unit = v("unit");
  const qty = num(v("qty"));
  const effort = v("effort");
  const b = { genre: v("genre"), nom: v("nom").trim(), repetitions: Math.max(1, Math.min(50, Math.round(Number(v("repetitions")) || 1))) };
  if (qty) {
    if (unit === "km") b.distance_m = Math.round(qty * 1000);
    else if (unit === "m") b.distance_m = Math.round(qty);
    else b.duree_min = unit === "s" ? Math.round(qty) / 60 : qty;
  }
  if (effort === "vma") { const p = num(v("pct_vma")); if (p) b.pct_vma = Math.round(p); else if (old?.pct_vma && !el.querySelector('[data-k="pct_vma"]')) b.pct_vma = old.pct_vma; }
  if (effort === "fc") { const z = num(v("zone_fc")); if (z) b.zone_fc = Math.round(z); else if (!el.querySelector('[data-k="zone_fc"]')) b.zone_fc = old?.zone_fc || 2; }
  if (effort === "vma" && !b.pct_vma && !el.querySelector('[data-k="pct_vma"]')) b.pct_vma = 70;
  const rest = num(v("rest"));
  if (b.repetitions > 1 && rest) b.recup_min = v("restunit") === "s" ? Math.round(rest) / 60 : rest;
  else if (b.repetitions > 1 && !el.querySelector('[data-k="rest"]') && old?.recup_min) b.recup_min = old.recup_min;
  if (b.repetitions > 1 && (v("recup_texte").trim() || (!el.querySelector('[data-k="recup_texte"]') && old?.recup_texte))) b.recup_texte = v("recup_texte").trim() || old.recup_texte;
  if (v("note").trim()) b.note = v("note").trim();
  return b;
}

export async function renderEditor(ctx) {
  const { page, params, toast } = ctx;
  const editId = /^\d+$/.test(params.get("id") || "") ? Number(params.get("id")) : null;
  const editStudent = /^\d+$/.test(params.get("eleve") || "") ? Number(params.get("eleve")) : null;
  page.innerHTML = `${ctx.head(`<h1>${editId ? "Modifier une séance" : "Proposer une séance"}</h1>`)}${ctx.tabs("proposer")}<div class="co-page wide">${loading()}</div>`;
  const [group, saved] = await Promise.all([rget("groupe"), rget("modeles").then((r) => r.modeles).catch(() => [])]);
  const students = group.eleves;
  let templates = saved;
  const tomorrow = F.isoDate(F.addDays(new Date(), 1));
  const state = { eleves: new Set(), date: /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : tomorrow, ...clone(EXAMPLES[1]) };
  (params.get("eleves") || "").split(",").map(Number).filter((id) => students.some((s) => s.id === id)).forEach((id) => state.eleves.add(id));

  if (editId && editStudent) {
    const fiche = await rget(`eleves/${editStudent}/fiche`);
    const p = fiche.propositions.find((x) => x.id === editId);
    if (!p) {
      page.innerHTML = `${ctx.head(`<h1>Modifier une séance</h1>`)}${ctx.tabs("proposer")}<div class="co-page">${fail("Cette séance proposée n'existe plus (ou elle est trop ancienne).")}</div>`;
      return;
    }
    Object.assign(state, { date: p.date, titre: p.titre, sport: p.sport, blocs: clone(p.blocs), consigne: p.consigne || "" });
    state.eleves = new Set([editStudent]);
  }
  if (!editId && students.length === 1) state.eleves.add(students[0].id);

  page.innerHTML = `${ctx.head(`<h1>${editId ? "Modifier une séance" : "Proposer une séance"}</h1>`,
    `<span>${editId ? "L'élève voit la nouvelle version dans son calendrier à sa prochaine synchro." : "Elle arrive dans le calendrier de chaque élève choisi, avec ses allures à lui."}</span>`,
    `<button class="btn" type="button" data-save-tpl>${icon("layers")}Enregistrer comme modèle</button><button class="btn btn-primary" type="button" data-send>${icon("check")}<span data-send-label>Envoyer</span></button>`)}
    ${ctx.tabs("proposer")}
    <div class="co-grid2 editor">
      <div class="co-page">
        <section class="coach-card"><h2>${icon("club")}Pour qui</h2>
          ${students.length ? `<div class="co-pick" data-pick>${students.map((s) => `<label class="co-pickone${editId ? " locked" : ""}"><input type="checkbox" value="${s.id}" ${state.eleves.has(s.id) ? "checked" : ""} ${editId ? "disabled" : ""}>
            ${avatar(s.nom, { size: "sm" })}<span>${F.escape(s.nom)}<small>${s.vma_kmh ? `VMA ${F.dec1(s.vma_kmh)}` : "VMA inconnue"}</small></span></label>`).join("")}</div>
            ${!editId && students.length > 1 ? `<div class="inline-actions" style="margin:8px 0 0"><button type="button" class="btn btn-ghost btn-small" data-all>Tout le groupe</button><button type="button" class="btn btn-ghost btn-small" data-none>Personne</button></div>` : ""}`
          : `<p class="co-empty">Ton groupe est vide : <a href="#/coach">invite un élève</a> d'abord.</p>`}
        </section>
        <section class="coach-card"><h2>${icon("edit")}La séance</h2>
          <div class="co-form3">
            <label class="field"><span>Date</span><input type="date" data-f="date" value="${state.date}"></label>
            <label class="field"><span>Sport</span><select data-f="sport">${SPORTS.map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select></label>
            <label class="field co-wide"><span>Titre</span><input type="text" data-f="titre" maxlength="80" placeholder="ex. Seuil 3 × 10 min"></label>
          </div>
          <p class="co-lbl">Déroulé</p><div class="co-bforms" data-blocks></div>
          <div class="inline-actions" style="margin:10px 0 4px"><button type="button" class="btn btn-ghost" data-add>${icon("plus")}Ajouter un bloc</button><span class="muted" data-total></span></div>
          <label class="field"><span>Consigne (facultatif)</span><textarea data-f="consigne" rows="3" maxlength="1500" placeholder="Ce qui compte dans cette séance, en une ou deux phrases."></textarea></label>
        </section>
      </div>
      <div class="co-page">
        <section class="coach-card"><h2>${icon("gauge")}Les allures de chacun</h2><div data-paces></div></section>
        <section class="coach-card"><h2>${icon("eye")}Ce que l'élève verra</h2><div data-preview></div></section>
        <section class="coach-card"><h2>${icon("layers")}Partir d'un modèle</h2><div data-templates></div></section>
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
  const chosen = () => students.filter((s) => state.eleves.has(s.id));

  const drawSide = () => {
    const list = chosen();
    const label = $("[data-send-label]");
    label.textContent = editId ? "Enregistrer" : list.length > 1 ? `Envoyer à ${list.length} élèves` : list.length ? `Envoyer à ${list[0].nom.split(" ")[0]}` : "Envoyer";
    const paced = state.blocs.map((b, i) => [b, i]).filter(([b]) => b.pct_vma);
    $("[data-paces]").innerHTML = !list.length ? `<p class="co-empty">Choisis au moins un élève.</p>`
      : !paced.length ? `<p class="co-empty">Aucun bloc en % de VMA : rien à calculer.</p>`
        : `<div class="co-table-wrap"><table class="co-paces"><thead><tr><th>Élève</th><th>VMA</th>${paced.map(([b]) => `<th>${F.escape(b.nom || "Bloc")}<small>${(b.repetitions || 1) > 1 ? `${b.repetitions} × ` : ""}${b.pct_vma} %</small></th>`).join("")}</tr></thead><tbody>
          ${list.map((s) => `<tr><td><b>${F.escape(s.nom)}</b></td><td>${s.vma_kmh ? F.dec1(s.vma_kmh) : "–"}</td>${paced.map(([b]) => `<td class="f">${s.vma_kmh ? paceFor(s.vma_kmh, b.pct_vma) : "–"}</td>`).join("")}</tr>`).join("")}
          </tbody></table></div>${list.some((s) => !s.vma_kmh) ? `<p class="hint" style="margin:8px 0 0">Sans VMA partagée, l'élève voit les pourcentages, sans allure.</p>` : ""}`;
    const first = list.find((s) => s.vma_kmh) || list[0];
    const t = totalMinutes(state.blocs, first?.vma_kmh);
    $("[data-total]").textContent = t.minutes ? `Durée totale : ${F.duration(t.minutes * 60, { short: true })}${t.km ? ` · environ ${F.dec1(t.km)} km${list.length > 1 && first ? ` (pour ${first.nom.split(" ")[0]})` : ""}` : ""}` : "";
    $("[data-preview]").innerHTML = `<div class="co-prevcard"><div class="co-prevhead"><b>${F.escape(state.titre || "Titre de la séance")}</b>
        <span>${F.escape(state.date ? F.dateLong(state.date) : "")}${first ? ` · pour ${F.escape(first.nom)}` : ""}</span></div>
      ${blocksHtml(state.blocs, first?.vma_kmh)}${state.consigne ? `<p class="co-consigne">« ${F.escape(state.consigne)} »</p>` : ""}</div>`;
  };

  function drawBlocks() {
    blocksBox.innerHTML = state.blocs.map((b, i) => blockForm(b, i, state.blocs.length)).join("");
    blocksBox.querySelectorAll("[data-block]").forEach((el) => {
      const i = Number(el.dataset.block);
      el.addEventListener("input", () => { collect(); drawSide(); });
      el.addEventListener("change", (e) => {
        collect();
        if (["effort", "repetitions", "genre"].includes(e.target.dataset.k)) {
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

  $("[data-save-tpl]").addEventListener("click", async () => {
    collect();
    if (!state.titre) { toast("Donne d'abord un titre à la séance : ce sera le nom du modèle."); field("titre").focus(); return; }
    try {
      templates = (await rpost("modeles", { titre: state.titre, sport: state.sport, blocs: state.blocs, consigne: state.consigne })).modeles;
      drawTemplates();
      toast(`Modèle « ${state.titre} » enregistré.`);
    } catch (err) { toast(err.message); }
  });

  $("[data-send]").addEventListener("click", async () => {
    collect();
    const list = chosen();
    if (!list.length) { toast("Choisis au moins un élève."); return; }
    if (!state.titre) { toast("Donne un titre à la séance."); field("titre").focus(); return; }
    const button = $("[data-send]");
    button.disabled = true;
    const body = { eleves: list.map((s) => s.id), date: state.date, titre: state.titre, sport: state.sport, blocs: state.blocs, consigne: state.consigne };
    try {
      if (editId) await rput(`propositions/${editId}`, body);
      else await rpost("propositions", body);
      const names = list.map((s) => s.nom.split(" ")[0]);
      toast(editId ? "Séance modifiée." : `Séance envoyée à ${names.length > 2 ? `${names.length} élèves` : names.join(" et ")} : elle arrive dans ${names.length > 1 ? "leur" : "son"} calendrier.`);
      location.hash = list.length === 1 ? `#/coach/eleve/${list[0].id}` : "#/coach";
    } catch (err) {
      toast(err.message);
      button.disabled = false;
    }
  });

  fill();
  drawTemplates();
}
