// Logothèque : le menu déroulant des logos, partagé par « Fier de ton club ? » (Réglages → Mon club) et
// l'application partenaire (Réglages → Application partenaire). D'abord ceux livrés avec Foulée (l'ACCT), puis
// ceux importés : chacun est nommé à l'import et s'ajoute aux deux listes.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const MAX = 5 * 1024 * 1024;  // comme le serveur
const IMPORT = "__importer";

export function logoURL(entry) {
  return entry ? `/api/logos/${encodeURIComponent(entry.id)}/image?v=${entry.v}` : null;
}

/** La liste des logos d'une page de réglages, partagée par ses menus : un import d'un côté s'ajoute de l'autre. */
export function logoLibrary(boot) {
  let state = boot.logotheque || { logos: [], club: null, partenaire: null, accueil: true };
  const listeners = new Set();
  return {
    get: () => state,
    set(next) { state = next; listeners.forEach((fn) => fn(state)); },
    subscribe(fn) { listeners.add(fn); },
  };
}

/** Nom proposé à partir du fichier : « logo_acct-2024.png » → « logo acct 2024 ». */
function nameFromFile(name) {
  return String(name || "").replace(/\.[a-z0-9]+$/i, "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 40);
}

/**
 * Le menu d'un usage (« club » ou « partenaire ») : choisir, importer un logo nommé, le retirer de la liste.
 * none : libellé du choix sans logo ; onPreview(entry | null) : l'aperçu ; home : la case « sur l'Accueil ».
 */
export function logoChoice(box, library, { use, none, toast, onChange, onPreview, home = false }) {
  let importing = false;
  let file = null;
  let status = { text: "", error: false };
  const lib = () => library.get();
  const current = () => lib().logos.find((x) => x.id === lib()[use]) || null;

  function draw() {
    const state = lib();
    const chosen = current();
    const builtin = state.logos.filter((x) => x.integre);
    const mine = state.logos.filter((x) => !x.integre);
    const option = (x) => `<option value="${F.escape(x.id)}" ${x.id === state[use] ? "selected" : ""}>${F.escape(x.nom)}</option>`;
    box.innerHTML = `
      <div class="lc-row">
        <label class="field lc-field"><span>Logo</span><select data-lc-select>
          <option value="" ${chosen ? "" : "selected"}>${F.escape(none)}</option>
          ${builtin.length ? `<optgroup label="Livrés avec Foulée">${builtin.map(option).join("")}</optgroup>` : ""}
          ${mine.length ? `<optgroup label="Importés">${mine.map(option).join("")}</optgroup>` : ""}
          <option value="${IMPORT}">Importer un logo…</option>
        </select></label>
        ${chosen && !chosen.integre ? `<button class="btn btn-ghost btn-small btn-danger" type="button" data-lc-remove title="Le retirer des listes (club et application partenaire)">${icon("trash")}Retirer de la liste</button>` : ""}
      </div>
      ${importing ? `<div class="lc-import">
        <label class="field lc-name"><span>Nom dans la liste</span><input type="text" maxlength="40" data-lc-name value="${F.escape(file ? nameFromFile(file.name) : "")}" placeholder="Mon club, ACCT…" autocomplete="off"></label>
        <div class="inline-actions">
          <button class="btn" type="button" data-lc-pick>${icon("upload")}${file ? "Changer d'image" : "Choisir l'image…"}</button>
          ${file ? `<button class="btn btn-primary" type="button" data-lc-add>${icon("check")}Ajouter à la liste</button>` : ""}
          <button class="btn btn-ghost" type="button" data-lc-cancel>Annuler</button>
          <input type="file" accept="image/png,image/webp,image/jpeg" hidden data-lc-file>
        </div>
        <p class="hint">${file ? `Image : <b>${F.escape(file.name)}</b>. ` : ""}PNG à fond transparent de préférence, WebP ou JPEG, 5 Mo au plus. Nommé, il s'ajoute à la liste du club et à celle de l'application partenaire.</p>
      </div>` : ""}
      ${home ? `<label class="check lc-home"><input type="checkbox" data-lc-home ${state.accueil ? "checked" : ""} ${chosen ? "" : "disabled"}>Aussi dans le bandeau de l'Accueil</label>` : ""}
      <p class="hint lc-status${status.error ? " error" : ""}" role="status">${F.escape(status.text)}</p>`;
    onPreview?.(chosen);
    if (importing && file) box.querySelector("[data-lc-name]")?.focus();
  }

  const say = (text, error = false) => { status = { text, error }; };
  const apply = async (promise, message) => {
    try {
      const next = await promise;
      say("");
      library.set(next);
      if (message) toast(message);
      await onChange?.();
    } catch (err) { say(err.message, true); draw(); }
  };

  box.addEventListener("change", async (e) => {
    const t = e.target;
    if (t.matches("[data-lc-select]")) {
      if (t.value === IMPORT) { importing = true; file = null; say(""); draw(); return; }
      importing = false;
      const entry = lib().logos.find((x) => x.id === t.value);
      await apply(api.put("/api/logos/choix", { [use]: t.value || null }),
        entry ? `Logo « ${entry.nom} » choisi.` : `${none} : c'est noté.`);
    } else if (t.matches("[data-lc-file]")) {
      const picked = t.files[0];
      t.value = "";
      if (!picked) return;
      if (picked.size > MAX) { say(`Image trop lourde (${F.dec1(picked.size / 1024 / 1024)} Mo) : 5 Mo au plus.`, true); draw(); return; }
      const typed = box.querySelector("[data-lc-name]")?.value.trim();
      file = picked;
      say("");
      draw();
      if (typed) box.querySelector("[data-lc-name]").value = typed;
    } else if (t.matches("[data-lc-home]")) {
      await apply(api.put("/api/logos/choix", { accueil: t.checked }),
        t.checked ? "Le logo du club s'affiche aussi sur l'Accueil." : "Le logo du club ne s'affiche plus sur l'Accueil.");
    }
  });
  box.addEventListener("click", async (e) => {
    if (e.target.closest("[data-lc-pick]")) box.querySelector("[data-lc-file]").click();
    if (e.target.closest("[data-lc-cancel]")) { importing = false; file = null; say(""); draw(); }
    if (e.target.closest("[data-lc-add]")) {
      const name = box.querySelector("[data-lc-name]").value.trim();
      if (!name) { say("Donne-lui un nom : c'est lui qui s'affiche dans la liste.", true); draw(); box.querySelector("[data-lc-name]").focus(); return; }
      const button = e.target.closest("[data-lc-add]");
      button.disabled = true;
      try {
        const res = await api.putBlob(`/api/logos/import?nom=${encodeURIComponent(name)}&pour=${use}`, file);
        importing = false;
        file = null;
        say(res.transparent ? "" : "Ce logo n'a pas de fond transparent : il s'affichera avec son fond. Un PNG transparent se fond mieux dans la page.");
        library.set(res);
        toast(`« ${res.logos.find((x) => x.id === res.ajoute)?.nom || name} » est dans la liste et choisi.`);
        await onChange?.();
      } catch (err) { say(err.message, true); draw(); }
    }
    if (e.target.closest("[data-lc-remove]")) {
      const chosen = current();
      if (!chosen || !window.confirm(`Retirer « ${chosen.nom} » de la liste ? Il disparaît aussi de l'endroit où il sert (club ou application partenaire).`)) return;
      await apply(api.del(`/api/logos/${encodeURIComponent(chosen.id)}`), `« ${chosen.nom} » retiré de la liste.`);
    }
  });
  // Un autre menu de la page a changé la liste (import, retrait) : celui-ci suit, sans perdre un import en cours
  library.subscribe(() => draw());
  draw();
  return { redraw: draw };
}
