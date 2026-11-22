// Réglages → Renfo : l'objectif de la semaine, l'équilibre avant / arrière visé (avec ses conseils), le niveau, le
// matériel à disposition, et ce que reprennent les séances composées dans l'Atelier (récup, échauffement, jours).
import * as F from "./format.js";
import { icon } from "./icons.js";

const DAYS = ["L", "M", "M", "J", "V", "S", "D"];
const RESTS = [30, 45, 60, 90, 120];
const ratio = (x) => `1 : ${String(Math.round(x * 100) / 100).replace(".", ",")}`;
const num = (v) => { const n = Number(String(v).replace(",", ".")); return Number.isFinite(n) ? n : null; };

/** La cible choisie, en clair : « 1 : 1 à 1 : 2, vise 1 : 1,5 ». */
export function targetText(t) {
  return `${ratio(t.bas)} à ${ratio(t.haut)}, vise ${ratio(t.vise ?? (t.bas + t.haut) / 2)}`;
}

export function renfoEditor(box, boot) {
  const opts = boot.renfo_options || { cibles: [], niveaux: [], materiel: [], jours: [] };
  const saved = boot.reglages.renfo || {};
  const z = {
    objectif_semaine: saved.objectif_semaine ?? 2,
    cible: saved.cible || "coureur",
    cible_bas: saved.cible_bas ?? 1,
    cible_haut: saved.cible_haut ?? 2,
    niveau: saved.niveau || "intermediaire",
    materiel: Array.isArray(saved.materiel) ? [...saved.materiel] : null,
    recup_s: saved.recup_s ?? 45,
    echauffement: saved.echauffement !== false,
    etirements: saved.etirements !== false,
    jours: Array.isArray(saved.jours) ? [...saved.jours] : [],
  };
  const touched = { any: Boolean(boot.reglages.renfo) };
  const value = () => (touched.any ? {
    ...z, cible_bas: z.cible === "perso" ? z.cible_bas : null, cible_haut: z.cible === "perso" ? z.cible_haut : null,
  } : null);
  const current = () => (z.cible === "perso"
    ? { libelle: "À ma façon", bas: z.cible_bas, haut: z.cible_haut, vise: (z.cible_bas + z.cible_haut) / 2, conseil: "Ta cible à toi, réglée à la main." }
    : opts.cibles.find((c) => c.cle === z.cible) || opts.cibles[0]);

  function render() {
    const t = current();
    const level = opts.niveaux.find((n) => n.cle === z.niveau);
    box.innerHTML = `
      <div class="rr-block">
        <h3>Objectif de la semaine</h3>
        <div class="rr-goal">
          <span class="tt-step rr-step" role="group" aria-label="Séances de renfo par semaine">
            <button type="button" data-goal="-1" aria-label="Une séance de moins" ${z.objectif_semaine <= 0 ? "disabled" : ""}>−</button>
            <b>${z.objectif_semaine || "–"}</b>
            <button type="button" data-goal="1" aria-label="Une séance de plus" ${z.objectif_semaine >= 7 ? "disabled" : ""}>+</button></span>
          <span>${z.objectif_semaine ? `séance${z.objectif_semaine > 1 ? "s" : ""} de renfo par semaine` : "pas d'objectif"}</span>
        </div>
        <p class="hint">La ligne d'objectif de la tuile « Renfo : muscles travaillés ». Pour un coureur, deux séances de 20 à 30 min par semaine suffisent à progresser et à protéger les tendons ; une seule entretient.</p>
      </div>

      <div class="rr-block">
        <h3>Équilibre avant / arrière visé</h3>
        <p class="hint rr-explain">Le rapport compare les séries faites <b>devant</b> (quadriceps, pectoraux, abdos) à celles faites <b>derrière</b> (fessiers, ischios, dos, mollets). « 1 : 1,5 », c'est 1,5 série derrière pour 1 devant.</p>
        <div class="zc-choices rr-targets" role="radiogroup" aria-label="Cible avant / arrière">
          ${opts.cibles.map((c) => `<button type="button" role="radio" class="zc-choice" data-target="${c.cle}" aria-checked="${z.cible === c.cle}">
            <span><b>${F.escape(c.libelle)}</b><small class="rr-range">${F.escape(targetText(c))}</small><small>${F.escape(c.conseil)}</small></span></button>`).join("")}
          <button type="button" role="radio" class="zc-choice" data-target="perso" aria-checked="${z.cible === "perso"}">
            <span><b>À ma façon</b><small class="rr-range">${z.cible === "perso" ? F.escape(targetText(current())) : "deux bornes, de 1 : 0,5 à 1 : 4"}</small><small>Une cible donnée par ton kiné ou ton coach, par exemple.</small></span></button>
        </div>
        ${z.cible === "perso" ? `<div class="rr-perso">
          <label class="field"><span>De 1 :</span><input type="text" inputmode="decimal" data-low value="${String(z.cible_bas).replace(".", ",")}" aria-label="Borne basse de la cible"></label>
          <label class="field"><span>à 1 :</span><input type="text" inputmode="decimal" data-high value="${String(z.cible_haut).replace(".", ",")}" aria-label="Borne haute de la cible"></label>
          <span class="hint" data-perso-msg></span></div>` : ""}
        <div class="rr-scale" aria-hidden="true">${scale(t)}</div>
        <ul class="rr-tips">
          <li>${icon("check")}<span>Les exercices de la chaîne postérieure en premier, quand tu es frais : pont fessier, soulevé de terre roumain, rowing.</span></li>
          <li>${icon("check")}<span>Pour corriger un déséquilibre, ajoute des séries du côté en retard plutôt que d'en retirer de l'autre.</span></li>
          <li>${icon("check")}<span>On juge sur 3 ou 4 semaines : une séance seule peut pencher d'un côté sans souci.</span></li>
          <li>${icon("info")}<span>Une douleur, une blessure qui revient ? Règle la cible avec ton kiné ou ton coach.</span></li>
        </ul>
      </div>

      <div class="rr-block">
        <h3>Niveau</h3>
        <div class="segmented rr-levels" role="radiogroup" aria-label="Niveau">${opts.niveaux.map((n) => `<button type="button" role="radio" data-level="${n.cle}" aria-checked="${z.niveau === n.cle}" aria-pressed="${z.niveau === n.cle}">${F.escape(n.libelle)}</button>`).join("")}</div>
        <p class="hint">${F.escape(level?.texte || "")} Le nombre de séries proposé quand tu ajoutes un exercice dans l'Atelier, et celui des séances toutes faites.</p>
      </div>

      <div class="rr-block">
        <h3>Matériel à disposition</h3>
        <div class="rr-gear-mode" role="radiogroup" aria-label="Matériel">
          <label class="check"><input type="radio" name="rr-gear" data-gear-mode="all" ${z.materiel === null ? "checked" : ""}>Tous les exercices (je ne précise pas)</label>
          <label class="check"><input type="radio" name="rr-gear" data-gear-mode="mine" ${z.materiel !== null ? "checked" : ""}>Seulement ce que je peux faire avec :</label>
        </div>
        ${z.materiel !== null ? `<div class="rr-gear">${opts.materiel.map((g) => `<label class="check"><input type="checkbox" data-gear="${g.cle}" ${z.materiel.includes(g.cle) ? "checked" : ""}>${F.escape(g.libelle)}</label>`).join("")}</div>
          <p class="hint">${z.materiel.length ? "" : "Rien de coché : au poids du corps, avec ce qu'on trouve chez soi (un mur, une chaise, une marche, une table solide). "}Les exercices conseillés pour rééquilibrer passent d'abord par ce matériel.</p>` : ""}
      </div>

      <div class="rr-block">
        <h3>Mes séances composées</h3>
        <div class="form-grid rr-defaults">
          <label class="field"><span>Récupération entre les séries</span><select data-rest>${RESTS.map((r) => `<option value="${r}" ${z.recup_s === r ? "selected" : ""}>${r} s</option>`).join("")}</select></label>
        </div>
        <div class="rr-checks">
          <label class="check"><input type="checkbox" data-warm ${z.echauffement ? "checked" : ""}>Échauffement de 5 min au début</label>
          <label class="check"><input type="checkbox" data-stretch ${z.etirements ? "checked" : ""}>Étirements de 5 min à la fin</label>
        </div>
        <p class="co-lbl rr-days-lbl">Mes jours de renfo</p>
        <div class="rr-days" role="group" aria-label="Jours de renfo">${DAYS.map((d, i) => `<button type="button" class="rr-day" data-rday="${i + 1}" aria-pressed="${z.jours.includes(i + 1)}" title="${F.escape(opts.jours[i] || "")}">${d}</button>`).join("")}</div>
        <p class="hint">Ce qu'une nouvelle séance de renfo reprend dans l'Atelier ; la date proposée pour l'envoyer sur ta montre est ton prochain jour de renfo.</p>
      </div>`;
  }

  // L'échelle de la tuile « équilibre » : la part des séries faites derrière, la bande de la cible en couleur
  function scale(t) {
    const part = (x) => (x / (1 + x)) * 100;
    const ticks = [[0.5, "1 : 0,5"], [1, "1 : 1"], [2, "1 : 2"], [4, "1 : 4"]];
    return `<div class="rr-bar"><i class="rr-band" style="left:${part(t.bas)}%;width:${part(t.haut) - part(t.bas)}%"></i>
      <i class="rr-aim" style="left:${part(t.vise ?? (t.bas + t.haut) / 2)}%"></i></div>
      <div class="rr-ticks">${ticks.map(([x, l]) => `<span style="left:${part(x)}%">${l}</span>`).join("")}</div>
      <div class="rr-ends"><span>tout devant</span><span>tout derrière</span></div>`;
  }

  const changed = () => { touched.any = true; };
  box.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.goal) z.objectif_semaine = Math.max(0, Math.min(7, z.objectif_semaine + Number(b.dataset.goal)));
    else if (b.dataset.target) z.cible = b.dataset.target;
    else if (b.dataset.level) z.niveau = b.dataset.level;
    else if (b.dataset.rday) {
      const d = Number(b.dataset.rday);
      z.jours = z.jours.includes(d) ? z.jours.filter((x) => x !== d) : [...z.jours, d].sort();
    } else return;
    changed();
    render();
  });
  box.addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.gearMode) z.materiel = t.dataset.gearMode === "all" ? null : (z.materiel || []);
    else if (t.dataset.gear) z.materiel = [...box.querySelectorAll("[data-gear]:checked")].map((x) => x.dataset.gear);
    else if (t.matches("[data-rest]")) z.recup_s = Number(t.value);
    else if (t.matches("[data-warm]")) z.echauffement = t.checked;
    else if (t.matches("[data-stretch]")) z.etirements = t.checked;
    else return;
    changed();
    if (t.dataset.gearMode) render();
  });
  box.addEventListener("input", (e) => {
    if (!e.target.matches("[data-low], [data-high]")) return;
    const low = num(box.querySelector("[data-low]").value);
    const high = num(box.querySelector("[data-high]").value);
    const msg = box.querySelector("[data-perso-msg]");
    if (low == null || high == null || low < 0.5 || high > 4 || low >= high) {
      msg.textContent = "De 1 : 0,5 à 1 : 4, la borne basse avant la haute.";
      return;
    }
    msg.textContent = "";
    z.cible_bas = low;
    z.cible_haut = high;
    changed();
    box.querySelector(".rr-scale").innerHTML = scale(current());
    box.querySelector('[data-target="perso"] .rr-range').textContent = targetText(current());
  });
  render();
  return { value };
}
