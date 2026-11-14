// Réglages → Mon club : « Je fais partie d'un club », le numéro de la licence, la fiche du club collée
// depuis athle.fr (Foulée en tire les coordonnées) et la licence. Enregistré à part du reste du formulaire.
// « Fier de ton club ? » : le logo du club, envoyé tout de suite (comme la photo de profil).
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const FIND = "https://www.athle.fr/trouver-un-club/";
const FIELDS = [  // [clé, libellé, clavier du téléphone, exemple]
  ["nom", "Nom du club", "text", ""],
  ["president", "Président(e)", "text", ""],
  ["telephone", "Téléphone", "tel", ""],
  ["email", "E-mail", "email", ""],
  ["adresse", "Adresse du siège", "text", ""],
  ["code_postal", "Code postal", "numeric", ""],
  ["ville", "Ville", "text", ""],
  ["site", "Site internet", "url", "https://…"],
  ["page", "Page du club sur athle.fr", "url", "https://www.athle.fr/clubs/…"],
];
const WIDE = new Set(["nom", "adresse", "page"]);
const LOGO_MAX = 5 * 1024 * 1024;  // comme le serveur

/** L'adresse du logo du club (la date du fichier évite l'ancienne image en cache), ou null sans logo. */
export function clubLogoURL(version) {
  return version ? `/api/club/logo?v=${version}` : null;
}

/** Saison FFA en cours : septembre 2026 → saison 2027 (« 2026-2027 »). */
function season(today = new Date()) {
  return today.getMonth() >= 8 ? today.getFullYear() + 1 : today.getFullYear();
}

function classementUrl(number, year) {
  return `https://www.athle.fr/bases/liste.aspx?frmbase=cclubs&frmmode=2&frmespace=&frmtypeclub=M&frmsaison=${year}&frmnclub=${number}&frmruptures=`;
}

export function clubPanel(box, boot, { toast, onChange }) {
  const saved = boot.reglages?.club || {};
  const lic = saved.licence || {};
  const year = season();
  let active = Boolean(saved.actif && saved.numero);
  box.classList.add("club-panel");
  box.innerHTML = `
    <label class="check club-toggle"><input type="checkbox" data-on ${saved.actif ? "checked" : ""}>
      <span><b>Je fais partie d'un club</b><span class="hint">La vue « Mon club » s'ajoute dans la colonne de gauche, juste après l'Accueil.</span></span></label>
    <div class="club-form" data-form ${saved.actif ? "" : "hidden"}>
      <div class="club-step">
        <span class="club-step-num" aria-hidden="true">1</span>
        <div class="club-step-body">
          <b>Le numéro du club</b>
          <label class="field club-number"><span>N° de club (sur ta licence)</span>
            <input type="text" name="numero" inputmode="numeric" maxlength="6" autocomplete="off" placeholder="012345" value="${F.escape(saved.numero || "")}"></label>
          <p class="hint">Il figure sur ta licence, à la ligne « N° Club ». C'est lui qui retrouve le classement de ton club sur le site de la FFA. <span data-check></span></p>
        </div>
      </div>
      <div class="club-step">
        <span class="club-step-num" aria-hidden="true">2</span>
        <div class="club-step-body">
          <b>Les coordonnées, en un copier-coller <small>(facultatif)</small></b>
          <ol class="club-howto">
            <li>Ouvre la page de ton club sur athle.fr (<a href="${FIND}" target="_blank" rel="noopener">Trouver un club${icon("external")}</a>).</li>
            <li>Sélectionne du nom du club jusqu'à la fin du cadre « Coordonnées et contacts », puis copie (<kbd>Ctrl</kbd>&nbsp;+&nbsp;<kbd>C</kbd>).</li>
            <li>Colle ici : Foulée remplit les champs tout seul. Tu peux aussi coller l'adresse de la page, pour un lien direct.</li>
          </ol>
          <textarea class="club-paste" data-paste rows="3" placeholder="Colle ici la fiche du club…" aria-label="Fiche du club copiée depuis athle.fr"></textarea>
          <p class="hint club-paste-status" data-paste-status role="status"></p>
          <div class="form-grid club-fields">${FIELDS.map(([key, label, mode, placeholder]) => `<label class="field${WIDE.has(key) ? " wide" : ""}"><span>${label}</span>
              <input type="text" inputmode="${mode === "numeric" ? "numeric" : mode}" name="${key}" value="${F.escape(saved[key] || "")}" ${placeholder ? `placeholder="${F.escape(placeholder)}"` : ""} autocomplete="off"></label>`).join("")}</div>
        </div>
      </div>
      <div class="club-step">
        <span class="club-step-num" aria-hidden="true">3</span>
        <div class="club-step-body">
          <b>Ma licence <small>(facultatif)</small></b>
          <p class="hint">Foulée l'affiche dans « Mon club » et te prévient un mois avant la fin. Sans date, il compte jusqu'au 31 août, fin de la saison.</p>
          <div class="form-grid club-fields">
            <label class="field"><span>N° de licence</span><input type="text" name="licence_numero" inputmode="numeric" maxlength="20" autocomplete="off" value="${F.escape(lic.numero || "")}"></label>
            <label class="field"><span>Type de licence</span><select name="licence_type"><option value="">—</option>${(boot.club_licences || []).map((t) => `<option ${lic.type === t ? "selected" : ""}>${F.escape(t)}</option>`).join("")}</select></label>
            <label class="field"><span>Valable jusqu'au</span><input type="date" name="licence_expire" value="${F.escape(lic.expire || "")}"></label>
          </div>
        </div>
      </div>
      <div class="inline-actions club-save">
        <button class="btn btn-primary" type="button" data-save>${icon("check")}Enregistrer mon club</button>
        <a class="btn" href="#/vue/club" data-open ${active ? "" : "hidden"}>${icon("club")}Ouvrir « Mon club »</a>
        <span class="hint" data-status role="status"></span>
      </div>
      <div class="club-logo-box" data-logo-box></div>
    </div>`;

  const form = box.querySelector("[data-form]");
  const toggle = box.querySelector("[data-on]");
  const number = box.querySelector('[name="numero"]');
  const check = box.querySelector("[data-check]");
  const status = box.querySelector("[data-status]");
  const open = box.querySelector("[data-open]");
  const field = (name) => box.querySelector(`[name="${name}"]`);

  const paintCheck = () => {
    const digits = number.value.replace(/\D/g, "");
    const full = digits.padStart(6, "0");
    check.innerHTML = digits ? `<a href="${F.escape(classementUrl(full, year))}" target="_blank" rel="noopener">Vérifier : classement ${year - 1}-${year} du club ${F.escape(full)}${icon("external")}</a>` : "";
  };
  number.addEventListener("input", () => { number.value = number.value.replace(/\D/g, "").slice(0, 6); paintCheck(); });
  number.addEventListener("blur", () => { if (number.value) number.value = number.value.padStart(6, "0"); paintCheck(); });
  paintCheck();

  const payload = (actif) => ({
    actif,
    numero: number.value,
    ...Object.fromEntries(FIELDS.map(([key]) => [key, field(key).value])),
    licence: { numero: field("licence_numero").value, type: field("licence_type").value, expire: field("licence_expire").value },
  });
  const save = async (actif, message) => {
    status.textContent = "Enregistrement…";
    status.classList.remove("error");
    try {
      const res = await api.put("/api/settings", { club: payload(actif) });
      status.textContent = "";
      boot.reglages = res.reglages;
      active = actif;
      open.hidden = !active;
      toast(message);
      await onChange?.(res);
      return true;
    } catch (err) {
      status.textContent = err.message;
      status.classList.add("error");
      return false;
    }
  };

  toggle.addEventListener("change", async () => {
    form.hidden = !toggle.checked;
    if (!toggle.checked) {
      // Ce qui a été saisi est gardé : recocher la case remet la vue telle quelle
      if (active && !(await save(false, "Vue « Mon club » retirée. Tes informations sont gardées si tu recoches la case."))) {
        toggle.checked = true;
        form.hidden = false;
      }
      return;
    }
    if (number.value) await save(true, "La vue « Mon club » est de retour dans la colonne de gauche.");
    else number.focus();
  });

  box.querySelector("[data-save]").addEventListener("click", async () => {
    if (!number.value) {
      status.textContent = "Indique d'abord le numéro de club : il figure sur ta licence.";
      status.classList.add("error");
      number.focus();
      return;
    }
    await save(true, "Club enregistré : retrouve-le dans la vue « Mon club », dans la colonne de gauche.");
  });

  // « Fier de ton club ? » : le logo, enregistré dès qu'il est choisi
  const logoBox = box.querySelector("[data-logo-box]");
  let logo = boot.club_logo || null;
  const paintLogo = (message = "", error = false) => {
    const url = clubLogoURL(logo);
    logoBox.innerHTML = `
      <div class="club-logo-preview${url ? "" : " empty"}" title="${url ? "Le damier montre les parties transparentes" : ""}">
        ${url ? `<img src="${url}" alt="Logo du club">` : icon("club")}</div>
      <div class="club-logo-body">
        <b>Fier de ton club ?</b>
        <p class="hint">Ajoute son logo : il s'affiche dans « Mon club » et, si ton coach en fait partie (Réglages → Coach et élèves), sur la page « Mon coach ». Idéal : un <b>PNG à fond transparent</b>, carré, <b>500 × 500 pixels</b> (5 Mo au plus).</p>
        <div class="inline-actions">
          <button class="btn" type="button" data-logo-pick>${icon("upload")}${url ? "Changer le logo" : "Importer le logo"}</button>
          ${url ? `<button class="btn btn-ghost btn-danger" type="button" data-logo-remove>${icon("trash")}Retirer</button>` : ""}
          <input type="file" accept="image/png,image/webp,image/jpeg" hidden data-logo-file>
        </div>
        <p class="hint club-logo-status${error ? " error" : ""}" role="status">${F.escape(message)}</p>
      </div>`;
  };
  paintLogo();
  logoBox.addEventListener("click", async (e) => {
    if (e.target.closest("[data-logo-pick]")) logoBox.querySelector("[data-logo-file]").click();
    if (e.target.closest("[data-logo-remove]")) {
      try {
        await api.del("/api/club/logo");
        logo = null;
        paintLogo();
        toast("Logo du club retiré.");
        await onChange?.();
      } catch (err) { paintLogo(err.message, true); }
    }
  });
  logoBox.addEventListener("change", async (e) => {
    const file = e.target.closest("[data-logo-file]")?.files[0];
    if (!file) return;
    if (file.size > LOGO_MAX) { paintLogo(`Image trop lourde (${F.dec1(file.size / 1024 / 1024)} Mo) : 5 Mo au plus.`, true); return; }
    logoBox.querySelector("[data-logo-pick]").disabled = true;
    try {
      const res = await api.putBlob("/api/club/logo", file);
      logo = res.logo_maj;
      paintLogo(res.transparent ? "" : "Ce logo n'a pas de fond transparent : il s'affichera avec son fond. Un PNG transparent se fond mieux dans la page.");
      toast("Logo enregistré : il s'affiche dans « Mon club ».");
      await onChange?.();
    } catch (err) { paintLogo(err.message, true); }
  });

  // La fiche collée : Foulée en tire les coordonnées
  const paste = box.querySelector("[data-paste]");
  const pasteStatus = box.querySelector("[data-paste-status]");
  const LABELS = { numero: "n° de club", ...Object.fromEntries(FIELDS.map(([key, label]) => [key, label.toLowerCase()])) };
  let timer = null;
  const readSheet = async () => {
    const text = paste.value.trim();
    pasteStatus.classList.remove("ok");
    if (!text) { pasteStatus.textContent = ""; return; }
    try {
      const { champs } = await api.post("/api/club/fiche", { texte: text });
      const keys = Object.keys(champs).filter((key) => field(key));
      keys.forEach((key) => {
        const input = field(key);
        input.value = champs[key];
        input.classList.remove("filled");
        void input.offsetWidth;  // relance l'animation
        input.classList.add("filled");
      });
      if (keys.includes("numero")) paintCheck();
      if (keys.length) {
        pasteStatus.innerHTML = `${icon("check")}<span>${keys.length} information${keys.length > 1 ? "s" : ""} reprise${keys.length > 1 ? "s" : ""} : ${F.escape(keys.map((k) => LABELS[k]).join(", "))}. Vérifie-les, puis enregistre.</span>`;
        pasteStatus.classList.add("ok");
      } else {
        pasteStatus.textContent = "Rien reconnu : copie bien le cadre « Coordonnées et contacts » de la page du club.";
      }
    } catch (err) {
      pasteStatus.textContent = err.message;
    }
  };
  paste.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(readSheet, 300); });
}
