// Réglages → Profil (prénom, logo, photo) et sauvegarde des réglages (export / import entre le PC et le serveur).
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { LOGOS, logoSVG } from "./logos.js";

const MAX_FILE = 15 * 1024 * 1024;  // avant réduction dans le navigateur
const OUT = 256;                    // côté de la photo envoyée

/** Rubrique « Profil et logo » : chaque choix s'enregistre tout de suite. */
export function profilePanel(box, boot, { toast, onProfile }) {
  let state = { ...boot.profil };
  let crop = null;  // { bitmap, zoom, dx, dy }

  const photoURL = () => `/api/profil/photo?v=${state.photo_maj || 0}`;

  function render() {
    box.innerHTML = `
      <div class="profile-grid">
        <div class="profile-photo">
          ${state.photo ? `<img src="${photoURL()}" alt="Ta photo de profil" width="96" height="96">` : `<span class="photo-empty">${icon("user")}</span>`}
          <div class="inline-actions">
            <button class="btn" type="button" data-pick>${icon("camera")}${state.photo ? "Changer de photo" : "Ajouter une photo"}</button>
            ${state.garmin ? `<button class="btn btn-ghost" type="button" data-garmin>${icon("download")}Prendre ma photo Garmin</button>` : ""}
            ${state.photo ? `<button class="btn btn-ghost btn-danger" type="button" data-remove>${icon("trash")}Retirer</button>` : ""}
          </div>
          <p class="hint">${F.escape(state.regles || "")}</p>
          <input type="file" accept="image/jpeg,image/png,image/webp" hidden data-file>
          <div class="cropper" data-cropper hidden></div>
        </div>
        <div class="profile-fields">
          <label class="field"><span>Prénom affiché</span><input type="text" maxlength="40" data-name value="${F.escape(state.prenom || "")}" placeholder="${F.escape(state.prenom_affiche || "Ton prénom")}"></label>
          <div class="field"><span>Logo de l'application</span>
            <div class="logo-pick" role="radiogroup" aria-label="Logo">${Object.entries(LOGOS).map(([id, l]) => `
              <button type="button" role="radio" aria-checked="${state.logo === id}" data-logo="${id}" title="${F.escape(l.label)}">${logoSVG(id, 36)}<span>${F.escape(l.label)}</span></button>`).join("")}
              <button type="button" role="radio" aria-checked="${state.logo === "photo"}" data-logo="photo" ${state.photo ? "" : "disabled"} title="${state.photo ? "Ma photo" : "Ajoute d'abord une photo"}">
                ${state.photo ? `<img src="${photoURL()}" alt="" width="36" height="36">` : `<span class="photo-empty small">${icon("user")}</span>`}<span>Ma photo</span></button>
            </div></div>
        </div>
      </div>`;
  }

  async function update(payload, message) {
    try {
      state = await api.put("/api/profil", payload);
      onProfile(state);
      render();
      if (message) toast(message);
    } catch (err) { toast(err.message, { error: true }); }
  }

  function drawCrop() {
    const canvas = box.querySelector("[data-cropper] canvas");
    const { bitmap, zoom, dx, dy } = crop;
    const ctx = canvas.getContext("2d");
    const side = Math.min(bitmap.width, bitmap.height) / zoom;
    const sx = Math.max(0, Math.min(bitmap.width - side, (bitmap.width - side) / 2 + dx));
    const sy = Math.max(0, Math.min(bitmap.height - side, (bitmap.height - side) / 2 + dy));
    crop.sx = sx; crop.sy = sy; crop.side = side;
    ctx.clearRect(0, 0, OUT, OUT);
    ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, OUT, OUT);
  }

  async function openCropper(file) {
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { toast("Choisis une image JPEG, PNG ou WebP.", { error: true }); return; }
    if (file.size > MAX_FILE) { toast(`Image trop lourde (${F.size(file.size)}) : 15 Mo au plus.`, { error: true }); return; }
    let bitmap;
    try { bitmap = await createImageBitmap(file); } catch (e) { toast("Image illisible.", { error: true }); return; }
    if (bitmap.width < 32 || bitmap.height < 32) { toast("Image trop petite : 32 pixels de côté au moins.", { error: true }); return; }
    crop = { bitmap, zoom: 1, dx: 0, dy: 0 };
    const holder = box.querySelector("[data-cropper]");
    holder.hidden = false;
    holder.innerHTML = `<p class="computed">Recadre ta photo : fais-la glisser, zoome avec le curseur.</p>
      <canvas width="${OUT}" height="${OUT}" aria-label="Aperçu du recadrage"></canvas>
      <label class="inline-field"><span>Zoom</span><input type="range" min="1" max="4" step="0.05" value="1" data-zoom></label>
      <div class="inline-actions"><button class="btn btn-primary" type="button" data-save-photo>${icon("check")}Enregistrer la photo</button>
        <button class="btn btn-ghost" type="button" data-cancel-photo>Annuler</button></div>`;
    drawCrop();
    const canvas = holder.querySelector("canvas");
    let drag = null;
    canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, dx: crop.dx, dy: crop.dy }; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const scale = crop.side / canvas.getBoundingClientRect().width;
      crop.dx = drag.dx - (e.clientX - drag.x) * scale;
      crop.dy = drag.dy - (e.clientY - drag.y) * scale;
      drawCrop();
    });
    canvas.addEventListener("pointerup", () => { drag = null; crop.dx = crop.sx - (crop.bitmap.width - crop.side) / 2; crop.dy = crop.sy - (crop.bitmap.height - crop.side) / 2; });
    holder.querySelector("[data-zoom]").addEventListener("input", (e) => { crop.zoom = Number(e.target.value); drawCrop(); });
    holder.querySelector("[data-cancel-photo]").addEventListener("click", () => { holder.hidden = true; crop = null; });
    holder.querySelector("[data-save-photo]").addEventListener("click", async (e) => {
      e.currentTarget.disabled = true;
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
      try {
        state = await api.putBlob("/api/profil/photo", blob);
        if (state.logo !== "photo") state = await api.put("/api/profil", { logo: "photo" });
        onProfile(state);
        crop = null;
        render();
        toast("Photo enregistrée : elle sert aussi de logo (change-le ci-dessous si tu préfères).");
      } catch (err) { toast(err.message, { error: true }); e.currentTarget.disabled = false; }
    });
  }

  box.addEventListener("click", async (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    if (t.dataset.logo) update({ logo: t.dataset.logo });
    else if ("pick" in t.dataset) box.querySelector("[data-file]").click();
    else if ("remove" in t.dataset) {
      try { state = await api.del("/api/profil/photo"); onProfile(state); render(); toast("Photo retirée."); } catch (err) { toast(err.message, { error: true }); }
    } else if ("garmin" in t.dataset) {
      t.disabled = true;
      try { state = await api.post("/api/profil/photo/garmin"); onProfile(state); render(); toast("Photo Garmin récupérée."); } catch (err) { toast(err.message, { error: true }); t.disabled = false; }
    }
  });
  box.addEventListener("change", (e) => {
    if ("file" in e.target.dataset && e.target.files[0]) openCropper(e.target.files[0]);
    if ("name" in e.target.dataset) update({ prenom: e.target.value.trim() }, "Prénom enregistré.");
  });
  render();
}

/** Rubrique « Sauvegarde des réglages » : export et import d'un fichier. */
export function transferPanel(box, boot, { toast, onImported }) {
  box.innerHTML = `
    <div class="inline-actions">
      <a class="btn" href="/api/reglages/export" download>${icon("download")}Exporter mes réglages</a>
      <button class="btn" type="button" data-import>${icon("upload")}Importer des réglages…</button>
      <input type="file" accept="application/json,.json" hidden data-file>
    </div>
    <fieldset class="import-parts" data-parts hidden><legend>Reprendre de ce fichier :</legend>
      <label class="check"><input type="checkbox" value="reglages" checked>Les réglages (VMA, FC, objectif, horaires, zones…)</label>
      <label class="check"><input type="checkbox" value="vues" checked>Les vues (même nom = remplacée, les autres sont ajoutées)</label>
      <label class="check"><input type="checkbox" value="photo" checked>La photo de profil</label>
      <label class="check"><input type="checkbox" value="logo" checked>Le logo du club</label>
      <div class="inline-actions"><button class="btn btn-primary" type="button" data-go>${icon("check")}Importer</button>
        <button class="btn btn-ghost" type="button" data-cancel>Annuler</button><span class="hint" data-file-name></span></div>
    </fieldset>
    <p class="hint">Le fichier ne contient ni ta clé Garmin, ni tes mots de passe ou jetons. Le dossier des données et le canal de mises à jour restent propres à chaque installation.</p>`;
  let data = null;
  const parts = box.querySelector("[data-parts]");
  box.querySelector("[data-import]").addEventListener("click", () => box.querySelector("[data-file]").click());
  box.querySelector("[data-file]").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      data = JSON.parse(await file.text());
      if (data?.foulee_reglages !== 1) throw new Error("ce fichier n'est pas un export de réglages Foulée");
    } catch (err) {
      toast(`Import impossible : ${err.message}`, { error: true });
      return;
    }
    parts.hidden = false;
    parts.querySelector('[value="photo"]').closest("label").hidden = !data.photo;
    parts.querySelector('[value="logo"]').closest("label").hidden = !data.logo_club;
    parts.querySelector('[value="vues"]').closest("label").hidden = !data.vues;
    box.querySelector("[data-file-name]").textContent = `${file.name} : Foulée ${data.version || "?"}, exporté le ${F.dateTime(data.exporte_le)}`;
  });
  box.querySelector("[data-cancel]").addEventListener("click", () => { parts.hidden = true; data = null; });
  box.querySelector("[data-go]").addEventListener("click", async () => {
    const chosen = [...parts.querySelectorAll("input:checked")].filter((c) => !c.closest("label").hidden).map((c) => c.value);
    try {
      const report = await api.post("/api/reglages/import", { donnees: data, parties: chosen });
      toast(`Importé : ${report.reglages} réglage(s), ${report.vues} vue(s)${report.photo ? ", la photo" : ""}${report.logo ? ", le logo du club" : ""}.${report.ignores.length ? ` Ignoré : ${report.ignores.join(", ")}.` : ""}`);
      parts.hidden = true;
      onImported?.();
    } catch (err) { toast(`Import impossible : ${err.message}`, { error: true }); }
  });
}
