// « Ma séance de renfo » : composer une séance (par exemple avec les exercices conseillés pour rééquilibrer),
// la garder, et l'envoyer sur sa montre (par le relais du club, avec un compte élève relié) ou en fichier .fit.
import * as api from "./api.js";
import { openDialog } from "./editor.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const clone = (x) => JSON.parse(JSON.stringify(x));
const blank = () => ({ id: "", titre: "", consigne: "", echauffement: true, etirements: true, exercices: [] });

/** La séance proposée d'après les familles à rééquilibrer : le premier exercice (le plus simple) de chacune. */
export function presetFrom(compenser) {
  const fams = compenser?.familles || [];
  if (!fams.length) return null;
  const side = compenser.cote === "avant" ? "avant" : "arrière";
  return {
    ...blank(),
    titre: `Renfo rééquilibrage ${side}`,
    consigne: "Qualité d'exécution avant le nombre de répétitions.",
    exercices: fams.flatMap((f) => f.exercices.slice(0, 2)).slice(0, 5).map((e) => fromLibrary(e)),
  };
}

function fromLibrary(e) {
  const m = /^\s*(\d+)\s*[×x]\s*(.+)$/.exec(e.dosage || "");
  return { nom: e.nom, series: e.series || (m ? Number(m[1]) : 3), reps: e.reps || (m ? m[2] : ""), recup_s: /\bs$/.test(e.reps || "") ? 30 : 45 };
}

function download({ blob, name }) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  document.body.append(link);
  link.click();
  setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 1000);
}

export async function openRenfoSession({ toast, preset = null } = {}) {
  let data;
  try { data = await api.get("/api/renfo/seances", null, { fresh: true }); } catch (err) { toast(err.message, { error: true }); return; }
  let saved = data.seances;
  let state = clone(preset || saved[0] || blank());
  if (!state.exercices.length && !preset) state.titre = state.titre || "Ma séance de renfo";
  const today = F.isoDate(new Date());
  const lib = data.bibliotheque;
  const names = [...new Set(lib.flatMap((f) => f.exercices.map((e) => e.nom)))];

  const dialog = openDialog(`<div class="dlg dlg-wide rs">
    <div class="dlg-head"><h2>${icon("dumbbell")} Ma séance de renfo</h2>
      <p>Compose-la avec les exercices conseillés, garde-la, et envoie-la sur ta montre${data.montre ? "" : " (fichier .fit)"} : chaque série s'affiche avec ses répétitions ; appuie sur Lap quand elle est finie, la récup suit.</p></div>
    <div class="dlg-body">
      <div class="rs-top">
        <label class="field"><span>Mes séances</span><select data-pick><option value="">Nouvelle séance</option>${saved.map((s) => `<option value="${F.escape(s.id)}">${F.escape(s.titre)}</option>`).join("")}</select></label>
        <label class="field rs-title"><span>Nom</span><input type="text" data-k="titre" maxlength="80" placeholder="ex. Renfo arrière"></label>
        <label class="field"><span>Date sur la montre</span><input type="date" data-date value="${today}" min="${today}"></label>
      </div>
      <div class="rs-list" data-list></div>
      <div class="rs-add"><select data-add aria-label="Ajouter un exercice"><option value="">Ajouter un exercice…</option>
        ${lib.map((f) => `<optgroup label="${F.escape(`${f.nom} (${f.chaine})`)}">${f.exercices.map((e) => `<option value="${F.escape(e.nom)}">${F.escape(`${e.nom} · ${e.dosage}`)}</option>`).join("")}</optgroup>`).join("")}
        <option value="__libre">Un autre exercice (à écrire)</option></select></div>
      <div class="rs-opts"><label class="check"><input type="checkbox" data-k="echauffement"> Échauffement de 5 min au début</label>
        <label class="check"><input type="checkbox" data-k="etirements"> Étirements de 5 min à la fin</label></div>
      <label class="field"><span>Consigne (facultatif)</span><input type="text" data-k="consigne" maxlength="500" placeholder="Ce qui compte, en une phrase"></label>
      <datalist id="rs-names">${names.map((n) => `<option value="${F.escape(n)}">`).join("")}</datalist>
      <p class="rs-link" data-link hidden></p>
    </div>
    <div class="dlg-foot rs-foot">
      <button class="btn btn-ghost btn-danger" type="button" data-drop hidden>${icon("trash")}Supprimer</button>
      <span class="rs-spacer"></span>
      <button class="btn" type="button" data-save>${icon("check")}Enregistrer</button>
      <button class="btn" type="button" data-fit>${icon("download")}Fichier .fit</button>
      ${data.montre ? `<button class="btn btn-primary" type="button" data-watch>${icon("watch")}Envoyer sur ma montre</button>` : ""}
    </div></div>`);
  const $ = (sel) => dialog.querySelector(sel);
  const list = $("[data-list]");

  const fill = () => {
    $("[data-k=titre]").value = state.titre || "";
    $("[data-k=consigne]").value = state.consigne || "";
    $("[data-k=echauffement]").checked = state.echauffement !== false;
    $("[data-k=etirements]").checked = state.etirements !== false;
    $("[data-pick]").value = saved.some((s) => s.id === state.id) ? state.id : "";
    $("[data-drop]").hidden = !saved.some((s) => s.id === state.id);
    drawList();
  };
  const read = () => {
    state.titre = $("[data-k=titre]").value.trim();
    state.consigne = $("[data-k=consigne]").value.trim();
    state.echauffement = $("[data-k=echauffement]").checked;
    state.etirements = $("[data-k=etirements]").checked;
    state.exercices = [...list.querySelectorAll("[data-row]")].map((row) => ({
      nom: row.querySelector("[data-f=nom]").value.trim(),
      series: Number(row.querySelector("[data-f=series]").value) || 1,
      reps: row.querySelector("[data-f=reps]").value.trim(),
      recup_s: Number(row.querySelector("[data-f=recup]").value) || 0,
    })).filter((e) => e.nom);
    return state;
  };
  function drawList() {
    list.innerHTML = state.exercices.length ? `<div class="rs-head"><span>Exercice</span><span>Séries</span><span>Répétitions ou durée</span><span>Récup (s)</span><span></span></div>
      ${state.exercices.map((e, i) => `<div class="rs-row" data-row="${i}">
        <input type="text" data-f="nom" list="rs-names" maxlength="60" value="${F.escape(e.nom)}" aria-label="Exercice">
        <input type="number" data-f="series" min="1" max="10" value="${e.series}" aria-label="Séries">
        <input type="text" data-f="reps" maxlength="40" value="${F.escape(e.reps || "")}" placeholder="15, 10 par jambe, 30 s" aria-label="Répétitions ou durée">
        <input type="number" data-f="recup" min="0" max="600" step="15" value="${e.recup_s ?? 45}" aria-label="Récupération en secondes">
        <span class="rs-tools">${i ? `<button type="button" class="co-mini" data-up title="Monter">${icon("moveup")}</button>` : ""}<button type="button" class="co-mini" data-del title="Retirer">${icon("trash")}</button></span>
      </div>`).join("")}` : `<p class="co-empty">Aucun exercice : ajoute-en avec la liste ci-dessous.</p>`;
    list.querySelectorAll("[data-row]").forEach((row) => {
      const i = Number(row.dataset.row);
      row.querySelector("[data-del]").addEventListener("click", () => { read(); state.exercices.splice(i, 1); drawList(); });
      row.querySelector("[data-up]")?.addEventListener("click", () => { read(); [state.exercices[i - 1], state.exercices[i]] = [state.exercices[i], state.exercices[i - 1]]; drawList(); });
    });
  }
  const valid = () => {
    read();
    if (!state.titre) { toast("Donne un nom à ta séance."); $("[data-k=titre]").focus(); return false; }
    if (!state.exercices.length) { toast("Ajoute au moins un exercice."); return false; }
    return true;
  };

  $("[data-pick]").addEventListener("change", (e) => {
    const s = saved.find((x) => x.id === e.target.value);
    state = s ? clone(s) : { ...blank(), titre: "Ma séance de renfo" };
    fill();
  });
  $("[data-add]").addEventListener("change", (e) => {
    const value = e.target.value;
    e.target.value = "";
    if (!value) return;
    read();
    const found = lib.flatMap((f) => f.exercices).find((x) => x.nom === value);
    state.exercices.push(found ? fromLibrary(found) : { nom: "", series: 3, reps: "12", recup_s: 45 });
    drawList();
    if (!found) list.querySelector("[data-row]:last-child [data-f=nom]")?.focus();
  });
  $("[data-save]").addEventListener("click", async () => {
    if (!valid()) return;
    const others = saved.filter((s) => s.id !== state.id);
    try {
      const res = await api.put("/api/renfo/seances", { seances: [...others, state] });
      saved = res.seances;
      state = clone(saved.find((s) => s.titre === state.titre && !others.some((o) => o.id === s.id)) || saved.at(-1));
      $("[data-pick]").innerHTML = `<option value="">Nouvelle séance</option>${saved.map((s) => `<option value="${F.escape(s.id)}">${F.escape(s.titre)}</option>`).join("")}`;
      fill();
      toast(`« ${state.titre} » est dans tes séances.`);
    } catch (err) { toast(err.message, { error: true }); }
  });
  $("[data-drop]").addEventListener("click", async () => {
    if (!window.confirm(`Supprimer « ${state.titre} » de tes séances ?`)) return;
    try {
      saved = (await api.put("/api/renfo/seances", { seances: saved.filter((s) => s.id !== state.id) })).seances;
      $("[data-pick]").innerHTML = `<option value="">Nouvelle séance</option>${saved.map((s) => `<option value="${F.escape(s.id)}">${F.escape(s.titre)}</option>`).join("")}`;
      state = { ...blank(), titre: "Ma séance de renfo" };
      fill();
    } catch (err) { toast(err.message, { error: true }); }
  });
  $("[data-fit]").addEventListener("click", async () => {
    if (!valid()) return;
    try {
      download(await api.postForFile("/api/renfo/seance.fit", { seance: state }));
      toast("Fichier .fit téléchargé : montre branchée en USB, copie-le dans le dossier GARMIN\\NewFiles.");
    } catch (err) { toast(err.message, { error: true }); }
  });
  $("[data-watch]")?.addEventListener("click", async (e) => {
    if (!valid()) return;
    const button = e.currentTarget;
    button.disabled = true;
    try {
      const res = await api.post("/api/renfo/seance/montre", { seance: state, date: $("[data-date]").value });
      if (res.envoi) {
        toast(`« ${state.titre} » est dans ton calendrier Garmin pour le ${F.dateLong(res.envoi.date, { weekday: false })} : synchronise ta montre.`);
        dialog.close();
        return;
      }
      if (res.a_relier) {
        const link = $("[data-link]");
        link.hidden = false;
        link.innerHTML = `${icon("watch")}<span>${F.escape(res.raison || "Relie d'abord ton compte Garmin Connect (une seule fois) :")} <a href="${F.escape(res.adresse)}" target="_blank" rel="noopener">ouvrir Garmin Connect</a>, accepte, puis renvoie la séance.</span>`;
      }
    } catch (err) { toast(err.message, { error: true }); }
    button.disabled = false;
  });
  fill();
}
