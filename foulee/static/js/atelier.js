// L'Atelier : je compose mes séances moi-même, avec ou sans coach. Course et sports d'endurance en blocs (comme
// un coach les propose), renfo exercice par exercice ; des séances toutes faites pour partir de quelque chose, mes
// séances gardées (reprendre, modifier, enregistrer sous un autre nom), mes séances de renfo faites à reprendre ;
// et l'envoi sur la montre, à la date choisie (calendrier Garmin Connect, par le relais du club) ou en .fit.
import * as api from "./api.js";
import { B, blockForm, clone, EXAMPLES, readBlock, SPORTS } from "./bloc-editor.js";
import { blocksHtml, sportIcon, totalMinutes } from "./coach-ui.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { takePending } from "./renfo-seance.js";
import { sketchSVG } from "./sketch.js";
import { beam, headline, targetLabel } from "./tiles-renfo.js";

const RUN_SPORTS = SPORTS.filter(([k]) => k !== "renfo");
const RUN_EXAMPLES = EXAMPLES.filter((e) => e.sport !== "renfo");
const TABS = [["course", "run", "Course et endurance"], ["renfo", "dumbbell", "Renfo"]];
function download({ blob, name }) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
}

const blankRun = () => ({ id: "", titre: "", sport: "course", consigne: "", blocs: clone(RUN_EXAMPLES[1].blocs) });
const blankRenfo = (conf) => ({ id: "", titre: "", consigne: "", echauffement: conf.echauffement !== false, etirements: conf.etirements !== false, exercices: [] });

/** Durée estimée d'une séance de renfo : 40 s par série (ou la durée écrite), la récup, 30 s entre deux exercices. */
function renfoMinutes(s) {
  let sec = (s.echauffement ? 300 : 0) + (s.etirements ? 300 : 0);
  for (const e of s.exercices) {
    const m = /^(\d+)(?:\s*à\s*\d+)?\s*s\b/i.exec(e.reps || "");
    const per = (m ? Number(m[1]) : 40) * (/par (jambe|côté|bras)/i.test(e.reps || "") ? 2 : 1);
    sec += e.series * per + Math.max(0, e.series - 1) * (e.recup_s || 0) + 30;
  }
  return Math.round(sec / 60);
}

export async function renderAtelier(page, boot, { toast, params = new URLSearchParams() }) {
  page.innerHTML = `<div class="at"><p class="hint">Ouverture de l'Atelier…</p></div>`;
  let data;
  try { data = await api.get("/api/atelier", null, { fresh: true }); } catch (err) {
    page.innerHTML = `<div class="at"><p class="error">${F.escape(err.message)}</p></div>`;
    return;
  }
  const pending = takePending();  // une séance proposée par la tuile « exercices pour rééquilibrer »
  const conf = data.renfo_reglages || {};
  const levelSeries = (data.niveaux || []).find((n) => n.cle === conf.niveau)?.series || 3;
  const today = F.isoDate(new Date());
  const tomorrow = F.isoDate(F.addDays(new Date(), 1));
  const S = {
    tab: params.get("onglet") === "renfo" || pending ? "renfo" : "course",
    course: blankRun(),
    renfo: blankRenfo(conf),
    date: { course: tomorrow, renfo: data.date_renfo || today },
    link: null,
  };
  if (data.seances.length) S.course = clone(data.seances[0]);
  if (pending) S.renfo = { ...blankRenfo(conf), ...pending, id: "" };
  else if (data.renfo.length) S.renfo = clone(data.renfo[0]);
  if (!S.renfo.exercices.length && !S.renfo.titre && data.modeles_renfo.length) S.renfo = fromTemplate(data.modeles_renfo[0]);

  function fromTemplate(t) {
    return { id: "", titre: t.titre, consigne: t.consigne || "", echauffement: t.echauffement !== false, etirements: t.etirements !== false,
      exercices: clone(t.exercices) };
  }

  page.innerHTML = `<div class="at">
    <header class="at-head">
      <div class="at-title"><h1>${icon("atelier")}Atelier</h1>
        <p>Compose tes séances, de course ou de renfo : garde-les, reprends-les, et envoie-les sur ta montre au jour de ton choix.</p></div>
      <div class="segmented at-tabs" role="tablist" aria-label="Sorte de séance">${TABS.map(([k, ico, label]) => `<button type="button" role="tab" data-tab="${k}" aria-selected="${S.tab === k}" aria-pressed="${S.tab === k}">${icon(ico)}${label}</button>`).join("")}</div>
    </header>
    <div class="at-grid">
      <aside class="at-lib" data-lib></aside>
      <section class="at-edit coach-card" data-edit></section>
      <aside class="at-side" data-side></aside>
    </div>
  </div>`;
  const $ = (sel) => page.querySelector(sel);

  // ------------------------------------------------------------ bibliothèque (colonne de gauche)
  function drawLib() {
    const course = S.tab === "course";
    const mine = course ? data.seances : data.renfo;
    const current = course ? S.course : S.renfo;
    const item = (attrs, ico, title, sub, active) => `<button type="button" class="at-item${active ? " active" : ""}" ${attrs}>
      <span class="co-ico">${ico}</span><span><b>${F.escape(title)}</b>${sub ? `<small>${F.escape(sub)}</small>` : ""}</span></button>`;
    $("[data-lib]").innerHTML = `
      <section class="at-box"><div class="at-box-h"><h2>Mes séances</h2><button type="button" class="btn btn-small btn-ghost" data-new>${icon("plus")}Nouvelle</button></div>
        ${mine.length ? mine.map((s) => item(`data-mine="${F.escape(s.id)}"`, course ? sportIcon(s.sport) : icon("dumbbell"), s.titre,
          course ? `${s.blocs.length} bloc${s.blocs.length > 1 ? "s" : ""} · ≈ ${F.duration(totalMinutes(s.blocs, data.vma).minutes * 60, { short: true })}`
            : `${s.exercices.length} exercice${s.exercices.length > 1 ? "s" : ""} · ≈ ${renfoMinutes(s)} min`, s.id === current.id)).join("")
          : `<p class="hint">Pas encore de séance à toi : pars d'une séance toute faite, ajuste-la, puis « Enregistrer ».</p>`}
      </section>
      <section class="at-box"><div class="at-box-h"><h2>Toutes faites</h2></div>
        ${course ? RUN_EXAMPLES.map((e, i) => item(`data-example="${i}"`, sportIcon(e.sport), e.titre, `≈ ${F.duration(totalMinutes(e.blocs, data.vma).minutes * 60, { short: true })}`)).join("")
          : data.modeles_renfo.map((t, i) => item(`data-template="${i}"`, icon("dumbbell"), t.titre,
            `≈ ${t.duree_min} min${t.materiel_manquant.length ? " · matériel à prévoir" : ""}`)).join("")}
      </section>
      ${!course ? `<section class="at-box"><div class="at-box-h"><h2>D'après une séance faite</h2></div>
        ${data.faites.length ? data.faites.slice(0, 8).map((f, i) => item(`data-done="${i}"`, icon("activity"), f.nom,
          `${F.dateShort(f.date)} · ${f.exercices.length} exercice${f.exercices.length > 1 ? "s" : ""}`)).join("")
          : `<p class="hint">Tes séances de renfo enregistrées exercice par exercice par ta montre apparaîtront ici, à reprendre telles quelles.</p>`}
      </section>` : ""}`;
  }

  // ------------------------------------------------------------ éditeur (colonne du milieu)
  function actionsHTML(course) {
    const current = course ? S.course : S.renfo;
    const mine = (course ? data.seances : data.renfo).some((s) => s.id === current.id);
    return `<div class="at-actions">
      <div class="at-save">
        <button type="button" class="btn btn-primary" data-save>${icon("check")}${mine ? "Enregistrer" : "Garder dans mes séances"}</button>
        ${mine ? `<button type="button" class="btn" data-save-as>${icon("copy")}Enregistrer sous…</button>
          <button type="button" class="btn btn-ghost btn-danger" data-drop>${icon("trash")}Supprimer</button>` : ""}
      </div>
      <div class="at-send">
        <label class="field"><span>Date sur la montre</span><input type="date" data-date value="${S.date[S.tab]}" min="${today}"></label>
        ${data.montre ? `<button type="button" class="btn btn-primary" data-watch>${icon("watch")}Envoyer sur ma montre</button>` : ""}
        <button type="button" class="btn" data-fit>${icon("download")}Fichier .fit</button>
      </div>
      <p class="hint at-send-hint">${data.montre
        ? "Elle arrive dans ton calendrier Garmin Connect au jour choisi ; ta montre la récupère à sa synchro."
        : `L'envoi direct dans ton calendrier Garmin passe par le relais du club, avec un compte élève relié (${data.relie ? "ton compte n'est pas un compte élève" : "Réglages → Coach et élèves"}). En attendant : le fichier .fit, à copier dans le dossier GARMIN\\NewFiles de ta montre branchée en USB.`}</p>
      <p class="at-link" data-link ${S.link ? "" : "hidden"}>${S.link || ""}</p>
    </div>`;
  }

  function drawEdit() {
    const course = S.tab === "course";
    const box = $("[data-edit]");
    if (course) {
      const s = S.course;
      box.innerHTML = `<h2>${icon("edit")}${s.id && data.seances.some((x) => x.id === s.id) ? "Ma séance" : "Nouvelle séance"}</h2>
        <div class="co-form3 at-form">
          <label class="field co-wide"><span>Nom</span><input type="text" data-f="titre" maxlength="80" value="${F.escape(s.titre)}" placeholder="ex. Seuil 3 × 10 min"></label>
          <label class="field"><span>Sport</span><select data-f="sport">${RUN_SPORTS.map(([k, l]) => `<option value="${k}" ${k === s.sport ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        </div>
        <p class="co-lbl">Déroulé</p><div class="co-bforms" data-blocks></div>
        <div class="inline-actions" style="margin:10px 0 4px"><button type="button" class="btn btn-ghost" data-add-block>${icon("plus")}Ajouter un bloc</button><span class="muted" data-total></span></div>
        <label class="field"><span>Consigne (facultatif)</span><textarea data-f="consigne" rows="2" maxlength="1500" placeholder="Ce qui compte dans cette séance, en une ou deux phrases.">${F.escape(s.consigne || "")}</textarea></label>
        ${actionsHTML(true)}`;
      drawBlocks();
    } else {
      const s = S.renfo;
      const names = [...new Set(data.bibliotheque.flatMap((f) => f.exercices.map((e) => e.nom)))];
      box.innerHTML = `<h2>${icon("dumbbell")}${s.id && data.renfo.some((x) => x.id === s.id) ? "Ma séance de renfo" : "Nouvelle séance de renfo"}</h2>
        <label class="field"><span>Nom</span><input type="text" data-f="titre" maxlength="80" value="${F.escape(s.titre)}" placeholder="ex. Renfo arrière"></label>
        <div class="rs-list" data-list></div>
        <div class="rs-add"><select data-add aria-label="Ajouter un exercice"><option value="">Ajouter un exercice…</option>
          ${data.bibliotheque.map((f) => `<optgroup label="${F.escape(`${f.nom} (${f.chaine})`)}">${f.exercices.map((e) => `<option value="${F.escape(e.nom)}">${F.escape(`${e.nom} · ${e.dosage}${e.materiel_ok === false ? " · matériel : " + e.materiel : ""}`)}</option>`).join("")}</optgroup>`).join("")}
          <option value="__libre">Un autre exercice (à écrire)</option></select></div>
        <div class="rs-opts"><label class="check"><input type="checkbox" data-f="echauffement" ${s.echauffement !== false ? "checked" : ""}> Échauffement de 5 min au début</label>
          <label class="check"><input type="checkbox" data-f="etirements" ${s.etirements !== false ? "checked" : ""}> Étirements de 5 min à la fin</label></div>
        <label class="field"><span>Consigne (facultatif)</span><input type="text" data-f="consigne" maxlength="500" value="${F.escape(s.consigne || "")}" placeholder="Ce qui compte, en une phrase"></label>
        <datalist id="at-names">${names.map((n) => `<option value="${F.escape(n)}">`).join("")}</datalist>
        ${actionsHTML(false)}`;
      drawRows();
    }
    wireEdit();
  }

  // Course : les blocs (formulaire partagé avec « Proposer une séance »)
  function readRun() {
    const s = S.course;
    const box = $("[data-blocks]");
    const old = s.blocs;
    s.blocs = [...box.querySelectorAll("[data-block]")].map((el, i) => readBlock(el, old[i]));
    s.titre = $('[data-f="titre"]').value.trim();
    s.sport = $('[data-f="sport"]').value;
    s.consigne = $('[data-f="consigne"]').value.trim();
  }
  function drawBlocks() {
    const s = S.course;
    const box = $("[data-blocks]");
    box.innerHTML = s.blocs.map((b, i) => blockForm(b, i, s.blocs.length)).join("");
    box.querySelectorAll("[data-block]").forEach((el) => {
      const i = Number(el.dataset.block);
      el.addEventListener("input", () => { readRun(); drawSide(); });
      el.addEventListener("change", (e) => {
        readRun();
        if (["effort", "repetitions", "genre", "unit", "restunit"].includes(e.target.dataset.k)) {
          if (e.target.dataset.k === "effort" && e.target.value === "vma" && !s.blocs[i].pct_vma) s.blocs[i].pct_vma = 70;
          drawBlocks();
        } else drawSide();
      });
      el.querySelector("[data-del]").addEventListener("click", () => { readRun(); s.blocs.splice(i, 1); drawBlocks(); });
      el.querySelector("[data-dup]").addEventListener("click", () => { readRun(); s.blocs.splice(i + 1, 0, clone(s.blocs[i])); drawBlocks(); });
      el.querySelectorAll("[data-move]").forEach((btn) => btn.addEventListener("click", () => {
        readRun();
        const j = i + Number(btn.dataset.move);
        [s.blocs[i], s.blocs[j]] = [s.blocs[j], s.blocs[i]];
        drawBlocks();
      }));
    });
    drawSide();
  }

  // Renfo : les exercices
  function readRenfo() {
    const s = S.renfo;
    s.titre = $('[data-f="titre"]').value.trim();
    s.consigne = $('[data-f="consigne"]').value.trim();
    s.echauffement = $('[data-f="echauffement"]').checked;
    s.etirements = $('[data-f="etirements"]').checked;
    s.exercices = [...$("[data-list]").querySelectorAll("[data-row]")].map((row) => ({
      nom: row.querySelector("[data-r=nom]").value.trim(),
      series: Math.max(1, Math.min(10, Number(row.querySelector("[data-r=series]").value) || 1)),
      reps: row.querySelector("[data-r=reps]").value.trim(),
      recup_s: Math.max(0, Math.min(600, Number(row.querySelector("[data-r=recup]").value) || 0)),
    })).filter((e) => e.nom);
  }
  function drawRows() {
    const s = S.renfo;
    const list = $("[data-list]");
    list.innerHTML = s.exercices.length ? `<div class="rs-head"><span>Exercice</span><span>Séries</span><span>Répétitions ou durée</span><span>Récup (s)</span><span></span></div>
      ${s.exercices.map((e, i) => `<div class="rs-row" data-row="${i}">
        <input type="text" data-r="nom" list="at-names" maxlength="60" value="${F.escape(e.nom)}" aria-label="Exercice">
        <input type="number" data-r="series" min="1" max="10" value="${e.series}" aria-label="Séries">
        <input type="text" data-r="reps" maxlength="40" value="${F.escape(e.reps || "")}" placeholder="15, 10 par jambe, 30 s" aria-label="Répétitions ou durée">
        <input type="number" data-r="recup" min="0" max="600" step="15" value="${e.recup_s ?? conf.recup_s ?? 45}" aria-label="Récupération en secondes">
        <span class="rs-tools">${i ? `<button type="button" class="co-mini" data-up="${i}" title="Monter">${icon("moveup")}</button>` : ""}<button type="button" class="co-mini" data-del-row="${i}" title="Retirer">${icon("trash")}</button></span>
      </div>`).join("")}` : `<p class="co-empty">Aucun exercice : ajoute-en avec la liste ci-dessous, ou pars d'une séance toute faite.</p>`;
    drawSide();
  }

  // ------------------------------------------------------------ aperçu (colonne de droite)
  let balanceTimer = null;
  function drawSide() {
    const side = $("[data-side]");
    if (S.tab === "course") {
      const s = S.course;
      const t = totalMinutes(s.blocs, data.vma);
      side.innerHTML = `<section class="coach-card at-preview"><h2>${icon("eye")}Sur ta montre</h2>
        <div class="co-prevcard"><div class="co-prevhead"><b>${F.escape(s.titre || "Nom de la séance")}</b>
          <span>${F.escape([t.minutes ? `≈ ${F.duration(t.minutes * 60, { short: true })}` : "", t.km ? `≈ ${F.dec1(t.km)} km` : ""].filter(Boolean).join(" · "))}</span></div>
          <div class="at-sketch">${sketchSVG(s.blocs, { vma: data.vma, height: 34 })}</div>
          ${blocksHtml(s.blocs, data.vma)}${s.consigne ? `<p class="co-consigne">« ${F.escape(s.consigne)} »</p>` : ""}</div>
        <p class="hint">${data.vma ? `Allures calculées sur ta VMA de ${F.dec1(data.vma)} km/h (Réglages → Moi) : sur la montre, une fourchette de ± 3 %.` : "Donne ta VMA dans Réglages → Moi pour voir les allures."}</p></section>`;
      $("[data-total]") && ($("[data-total]").textContent = t.minutes ? `Durée totale : ${F.duration(t.minutes * 60, { short: true })}${t.km ? ` · environ ${F.dec1(t.km)} km` : ""}` : "");
      return;
    }
    const s = S.renfo;
    side.innerHTML = `<section class="coach-card at-preview"><h2>${icon("balance")}Ta séance</h2>
      <p class="at-sum">${s.exercices.length} exercice${s.exercices.length > 1 ? "s" : ""} · ${s.exercices.reduce((a, e) => a + e.series, 0)} séries · ≈ ${renfoMinutes(s)} min</p>
      <div data-balance><p class="hint">Calcul de l'équilibre…</p></div></section>`;
    clearTimeout(balanceTimer);
    balanceTimer = setTimeout(async () => {
      const box = $("[data-balance]");
      if (!box) return;
      try {
        const r = await api.post("/api/atelier/renfo/bilan", { seance: s });
        const b = r.equilibre;
        box.innerHTML = `${b.zone === "vide" ? `<p class="hint">Rien à ranger devant ou derrière pour l'instant.</p>`
          : `${headline(b, { compact: true })}${beam(b, { compact: true, target: r.cible })}<p class="hint">${F.escape(targetLabel(r.cible))} (Réglages → Renfo).</p>`}
          ${r.muscles.length ? `<p class="co-lbl" style="margin-top:12px">Muscles travaillés</p><div class="at-muscles">${r.muscles.sort((a, c) => c.series - a.series).slice(0, 8).map((m) => `<span>${F.escape(m.nom)}<small>${String(m.series).replace(".", ",")}</small></span>`).join("")}</div>` : ""}`;
      } catch (err) { box.innerHTML = `<p class="hint">${F.escape(err.message)}</p>`; }
    }, 250);
  }

  // ------------------------------------------------------------ actions
  const current = () => (S.tab === "course" ? S.course : S.renfo);
  const read = () => (S.tab === "course" ? readRun() : readRenfo());
  const valid = () => {
    read();
    const s = current();
    if (!s.titre) { toast("Donne un nom à ta séance."); $('[data-f="titre"]').focus(); return false; }
    if (S.tab === "renfo" && !s.exercices.length) { toast("Ajoute au moins un exercice."); return false; }
    if (S.tab === "course" && !s.blocs.length) { toast("Ajoute au moins un bloc."); return false; }
    return true;
  };
  async function store(list) {
    if (S.tab === "course") data.seances = (await api.put("/api/atelier/seances", { seances: list })).seances;
    else data.renfo = (await api.put("/api/renfo/seances", { seances: list })).seances;
    return S.tab === "course" ? data.seances : data.renfo;
  }
  async function save(asNew = false) {
    if (!valid()) return;
    const s = current();
    const mine = S.tab === "course" ? data.seances : data.renfo;
    let target = { ...clone(s) };
    if (asNew) {
      const name = window.prompt("Nom de la nouvelle séance :", `${s.titre} (2)`);
      if (!name || !name.trim()) return;
      target = { ...target, id: "", titre: name.trim().slice(0, 80) };
    }
    const same = mine.find((x) => x.titre.toLowerCase() === target.titre.toLowerCase() && x.id !== target.id);
    if (same && !window.confirm(`Tu as déjà une séance « ${same.titre} » : la remplacer ?`)) return;
    if (same) target.id = same.id;
    const known = mine.some((x) => x.id === target.id);
    const list = known ? mine.map((x) => (x.id === target.id ? target : x)) : [...mine, target];
    try {
      const after = await store(list);
      const kept = after.find((x) => x.titre === target.titre) || after.at(-1);
      if (S.tab === "course") S.course = clone(kept); else S.renfo = clone(kept);
      toast(`« ${kept.titre} » est dans tes séances.`);
      drawLib();
      drawEdit();
    } catch (err) { toast(err.message, { error: true }); }
  }
  async function drop() {
    const s = current();
    if (!window.confirm(`Supprimer « ${s.titre} » de tes séances ?`)) return;
    try {
      const mine = S.tab === "course" ? data.seances : data.renfo;
      await store(mine.filter((x) => x.id !== s.id));
      if (S.tab === "course") S.course = { ...clone(S.course), id: "" }; else S.renfo = { ...clone(S.renfo), id: "" };
      toast(`« ${s.titre} » supprimée (elle reste à l'écran, tu peux encore la garder).`);
      drawLib();
      drawEdit();
    } catch (err) { toast(err.message, { error: true }); }
  }
  async function toWatch(button) {
    if (!valid()) return;
    const s = current();
    const day = $("[data-date]").value || today;
    button.disabled = true;
    try {
      const res = await api.post(S.tab === "course" ? "/api/atelier/seance/montre" : "/api/renfo/seance/montre", { seance: s, date: day });
      if (res.envoi) {
        S.link = null;
        toast(`« ${s.titre} » est dans ton calendrier Garmin pour le ${F.dateLong(res.envoi.date, { weekday: true })} : synchronise ta montre.`);
      } else if (res.a_relier) {
        S.link = `${icon("watch")}<span>${F.escape(res.raison || "Relie d'abord ton compte Garmin Connect (une seule fois) :")} <a href="${F.escape(res.adresse)}" target="_blank" rel="noopener">ouvrir Garmin Connect</a>, accepte, puis renvoie la séance.</span>`;
        const link = $("[data-link]");
        link.hidden = false;
        link.innerHTML = S.link;
      }
    } catch (err) { toast(err.message, { error: true }); }
    button.disabled = false;
  }
  async function toFit() {
    if (!valid()) return;
    try {
      download(await api.postForFile(S.tab === "course" ? "/api/atelier/seance.fit" : "/api/renfo/seance.fit", { seance: current() }));
      toast("Fichier .fit téléchargé : montre branchée en USB, copie-le dans le dossier GARMIN\\NewFiles.");
    } catch (err) { toast(err.message, { error: true }); }
  }

  function wireEdit() {
    const box = $("[data-edit]");
    box.querySelector("[data-save]").addEventListener("click", () => save(false));
    box.querySelector("[data-save-as]")?.addEventListener("click", () => save(true));
    box.querySelector("[data-drop]")?.addEventListener("click", drop);
    box.querySelector("[data-watch]")?.addEventListener("click", (e) => toWatch(e.currentTarget));
    box.querySelector("[data-fit]").addEventListener("click", toFit);
    box.querySelector("[data-date]").addEventListener("change", (e) => { S.date[S.tab] = e.target.value; });
    ["titre", "consigne"].forEach((k) => box.querySelector(`[data-f="${k}"]`).addEventListener("input", () => { read(); drawSide(); }));
    if (S.tab === "course") {
      box.querySelector('[data-f="sport"]').addEventListener("change", () => { readRun(); drawSide(); });
      box.querySelector("[data-add-block]").addEventListener("click", () => {
        readRun();
        const last = S.course.blocs.at(-1);
        S.course.blocs.push(last?.genre === "calme" ? B("corps", "", { duree_min: 10, pct_vma: 75 }) : B("calme", "Retour au calme", { duree_min: 10, pct_vma: 60 }));
        drawBlocks();
      });
      return;
    }
    const list = box.querySelector("[data-list]");
    list.addEventListener("input", () => { readRenfo(); drawSide(); });
    list.addEventListener("click", (e) => {
      const up = e.target.closest("[data-up]");
      const del = e.target.closest("[data-del-row]");
      if (!up && !del) return;
      readRenfo();
      const ex = S.renfo.exercices;
      if (up) { const i = Number(up.dataset.up); [ex[i - 1], ex[i]] = [ex[i], ex[i - 1]]; }
      if (del) ex.splice(Number(del.dataset.delRow), 1);
      drawRows();
    });
    box.querySelectorAll('[data-f="echauffement"], [data-f="etirements"]').forEach((c) => c.addEventListener("change", () => { readRenfo(); drawSide(); }));
    box.querySelector("[data-add]").addEventListener("change", (e) => {
      const value = e.target.value;
      e.target.value = "";
      if (!value) return;
      readRenfo();
      const found = data.bibliotheque.flatMap((f) => f.exercices).find((x) => x.nom === value);
      const timed = found && /\bs$/.test(found.reps || "");
      S.renfo.exercices.push(found
        ? { nom: found.nom, series: found.series === 3 ? levelSeries : found.series, reps: found.reps, recup_s: timed ? Math.min(30, conf.recup_s ?? 45) : (conf.recup_s ?? 45) }
        : { nom: "", series: levelSeries, reps: "12", recup_s: conf.recup_s ?? 45 });
      drawRows();
      if (!found) list.querySelector("[data-row]:last-child [data-r=nom]")?.focus();
    });
  }

  // ------------------------------------------------------------ bibliothèque et onglets
  $("[data-lib]").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const course = S.tab === "course";
    let next = null;
    let note = "";
    if (b.dataset.new !== undefined) next = course ? { ...blankRun(), blocs: [B("echauffement", "Échauffement", { duree_min: 15, pct_vma: 65 }), B("corps", "", { duree_min: 20, pct_vma: 75 }), B("calme", "Retour au calme", { duree_min: 10, pct_vma: 60 })] } : blankRenfo(conf);
    else if (b.dataset.mine) next = clone((course ? data.seances : data.renfo).find((x) => x.id === b.dataset.mine));
    else if (b.dataset.example) { const ex = RUN_EXAMPLES[Number(b.dataset.example)]; next = { id: "", titre: ex.titre, sport: ex.sport, consigne: ex.consigne || "", blocs: clone(ex.blocs) }; note = `« ${ex.titre} » chargée : ajuste-la, puis garde-la dans tes séances si tu veux la refaire.`; }
    else if (b.dataset.template) {
      const t = data.modeles_renfo[Number(b.dataset.template)];
      next = fromTemplate(t);
      note = t.materiel_manquant.length ? `Matériel à prévoir pour : ${t.materiel_manquant.join(", ")}. Remplace-les si besoin.` : `« ${t.titre} » chargée : ${t.pour}`;
    } else if (b.dataset.done) {
      const f = data.faites[Number(b.dataset.done)];
      next = { ...blankRenfo(conf), titre: `${f.nom}`.slice(0, 80), exercices: clone(f.exercices) };
      note = `Les exercices de ta séance du ${F.dateLong(f.date, { weekday: false })} : ajuste-les, puis garde-la sous un nom à toi.`;
    }
    if (!next) return;
    if (course) S.course = next; else S.renfo = next;
    S.link = null;
    drawLib();
    drawEdit();
    if (note) toast(note);
    if (window.innerWidth < 900) $("[data-edit]").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  page.querySelectorAll("[data-tab]").forEach((btn) => btn.addEventListener("click", () => {
    if (btn.dataset.tab === S.tab) return;
    read();
    S.tab = btn.dataset.tab;
    S.link = null;
    if (S.tab === "renfo" && !S.renfo.exercices.length && data.renfo.length) S.renfo = clone(data.renfo[0]);
    page.querySelectorAll("[data-tab]").forEach((x) => { const on = x.dataset.tab === S.tab; x.setAttribute("aria-selected", String(on)); x.setAttribute("aria-pressed", String(on)); });
    history.replaceState(null, "", `#/atelier${S.tab === "renfo" ? "?onglet=renfo" : ""}`);
    drawLib();
    drawEdit();
  }));

  drawLib();
  drawEdit();
}
