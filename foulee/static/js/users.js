// Profils : le prénom et son chevron en haut à droite de l'Accueil, la page « Qui utilise Foulée ? »,
// le code à 4 chiffres, et dans les Réglages : l'accès à son profil et la gestion des utilisateurs.
import * as api from "./api.js";
import { confirm, openDialog } from "./editor.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { brandMark, logoSVG } from "./logos.js";

const COLORS = ["#4b3e34", "#2f5d50", "#8a3b2f", "#3d5a80", "#6b4f2a", "#5b4a7a", "#2f6b5e", "#7a4a5e"];
const colorOf = (id) => COLORS[[...String(id)].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % COLORS.length];

/** Avatar d'un profil : sa photo, sinon son logo, sinon l'initiale de son prénom. */
export function avatar(user, size = 32) {
  if (user.photo) {
    return `<img class="avatar" src="/api/utilisateurs/${encodeURIComponent(user.id)}/photo?v=${user.photo_maj || 0}" width="${size}" height="${size}" alt="">`;
  }
  if (user.logo && user.logo !== "foulee" && user.logo !== "photo") {
    return `<span class="avatar" style="--s:${size}px">${logoSVG(user.logo, size)}</span>`;
  }
  const initial = (user.prenom || "?").trim().charAt(0).toUpperCase();
  return `<span class="avatar avatar-initial" style="--s:${size}px;--c:${colorOf(user.id)}" aria-hidden="true">${F.escape(initial)}</span>`;
}

/** Passe sur un profil (en demandant son code s'il en a un), puis recharge l'interface. */
export async function switchTo(user, { toast } = {}) {
  if (user.courant) return;
  if (user.code) {
    askCode(user);
    return;
  }
  try {
    await api.post("/api/utilisateurs/choisir", { id: user.id });
    goHome();
  } catch (err) {
    toast?.(err.message, { error: true });
  }
}

function goHome() {
  location.hash = "#/vue/accueil";
  location.reload();
}

function askCode(user) {
  const dialog = openDialog(`<form class="dlg dlg-code" method="dialog" novalidate>
      <div class="dlg-head">${avatar(user, 56)}<h2>${F.escape(user.prenom)}</h2><p>Tape le code à 4 chiffres de ce profil.</p></div>
      <div class="dlg-body">
        <input class="code-input" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="4" autocomplete="off" aria-label="Code à 4 chiffres" data-code>
        <p class="code-error" role="alert" data-error></p>
      </div>
      <div class="dlg-foot"><button class="btn" value="cancel" type="button" data-cancel>Annuler</button><button class="btn btn-primary" type="submit">${icon("check")}Entrer</button></div>
    </form>`);
  const form = dialog.querySelector("form");
  const input = dialog.querySelector("[data-code]");
  const error = dialog.querySelector("[data-error]");
  let busy = false;
  const send = async () => {
    const code = input.value.trim();
    if (busy) return;
    if (!/^\d{4}$/.test(code)) {
      error.textContent = "Le code fait 4 chiffres.";
      return;
    }
    busy = true;
    try {
      await api.post("/api/utilisateurs/choisir", { id: user.id, code });
      dialog.close();
      goHome();
    } catch (err) {
      error.textContent = err.message;
      input.value = "";
      form.classList.remove("shake");
      void form.offsetWidth;  // relance l'animation
      form.classList.add("shake");
      input.focus();
    } finally {
      busy = false;
    }
  };
  input.addEventListener("input", () => {
    input.value = input.value.replace(/\D/g, "").slice(0, 4);
    error.textContent = "";
    if (input.value.length === 4) send();
  });
  form.addEventListener("submit", (e) => { e.preventDefault(); send(); });
  dialog.querySelector("[data-cancel]").addEventListener("click", () => dialog.close());
  input.focus();
}

// ======================================================= prénom + chevron (Accueil)
/** Bouton « prénom + chevron » qui ouvre la liste des profils. */
export function whoButton(boot) {
  const me = (boot.utilisateurs || []).find((u) => u.courant) || { id: "?", prenom: boot.profil?.prenom_affiche || "Moi" };
  return `<div class="who" data-who>
      <button class="who-btn" type="button" aria-haspopup="true" aria-expanded="false" data-who-toggle title="Changer de profil">
        ${avatar(me, 28)}<span class="who-name">${F.escape(me.prenom)}</span>${icon("chevron")}</button>
      <div class="who-menu" data-who-menu hidden></div>
    </div>`;
}

export function wireWho(root, boot, { toast }) {
  const box = root.querySelector("[data-who]");
  if (!box) return;
  const toggle = box.querySelector("[data-who-toggle]");
  const menu = box.querySelector("[data-who-menu]");
  const users = boot.utilisateurs || [];
  const principal = boot.utilisateur?.principal;
  menu.innerHTML = `
    <p class="who-title">${users.length > 1 ? "Changer de profil" : "Profils"}</p>
    <ul class="who-list">${users.map((u) => `<li><button type="button" class="who-item${u.courant ? " current" : ""}" data-user="${F.escape(u.id)}" ${u.courant ? 'aria-current="true"' : ""}>
        ${avatar(u, 30)}<span class="who-item-name">${F.escape(u.prenom)}${u.principal ? `<small>principal</small>` : ""}</span>
        ${u.courant ? icon("check") : u.code ? `<span class="who-lock" title="Protégé par un code">${icon("lock")}</span>` : ""}</button></li>`).join("")}</ul>
    ${users.length < 2 ? `<p class="who-note">${principal ? "Tu es seul sur Foulée. Ajoute un profil par personne qui a une montre Garmin : chacun aura ses données, ses vues et ses réglages." : ""}</p>` : ""}
    ${principal ? `<a class="who-manage" href="#/reglages?section=utilisateurs">${icon("settings")}Gérer les utilisateurs</a>` : ""}`;
  const close = (focus = false) => {
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    if (focus) toggle.focus();
  };
  const open = () => {
    menu.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    (menu.querySelector(".who-item:not(.current)") || menu.querySelector("a, button"))?.focus();
  };
  toggle.addEventListener("click", () => (menu.hidden ? open() : close()));
  menu.addEventListener("click", (e) => {
    const item = e.target.closest("[data-user]");
    if (item) {
      close();
      switchTo(users.find((u) => u.id === item.dataset.user), { toast });
    }
    if (e.target.closest(".who-manage")) close();
  });
  box.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !menu.hidden) { e.stopPropagation(); close(true); }
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !menu.hidden) {
      e.preventDefault();
      const items = [...menu.querySelectorAll("button, a")];
      const index = items.indexOf(document.activeElement);
      items[(index + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
    }
  });
  const outside = (e) => { if (!box.contains(e.target)) close(); };
  document.addEventListener("click", outside);
  return { dispose: () => document.removeEventListener("click", outside) };
}

// ===================================================== « Qui utilise Foulée ? »
export function renderChooser(page, boot, { toast }) {
  const users = boot.utilisateurs || [];
  page.innerHTML = `
    <div class="chooser">
      <div class="chooser-brand">${brandMark({}, 30)}<span>Foulée</span></div>
      <h1>Qui utilise Foulée ?</h1>
      <p class="chooser-sub">Chacun retrouve ses données Garmin, ses vues et ses réglages.</p>
      <ul class="chooser-grid">${users.map((u) => `<li><button class="chooser-card" type="button" data-user="${F.escape(u.id)}">
          ${avatar(u, 96)}<span class="chooser-name">${F.escape(u.prenom)}</span>
          ${u.code ? `<span class="chooser-lock">${icon("lock")}Code</span>` : ""}</button></li>`).join("")}</ul>
      <p class="chooser-hint">${icon("info")}<span>Ce choix est retenu sur cet appareil. Pour changer ensuite : ton prénom, en haut à droite de l'Accueil.</span></p>
    </div>`;
  page.querySelectorAll("[data-user]").forEach((button) => button.addEventListener("click", () => {
    switchTo(users.find((u) => u.id === button.dataset.user), { toast });
  }));
  page.querySelector("[data-user]")?.focus();
}

// ============================================ Réglages : accès à son propre profil
/** Code du profil et accès de Claude Desktop : chacun règle le sien. */
export function accessPanel(box, boot, { toast, onChange }) {
  let me = { ...boot.utilisateur };
  const render = () => {
    box.innerHTML = `
      <div class="access-row">
        <div class="access-text">${icon("lock")}<div><b>Code du profil</b>
          <span>${me.code ? "Ton profil est protégé : son code est demandé pour y entrer depuis un autre profil ou un nouvel appareil."
            : "Aucun code : on entre dans ton profil sans rien taper. Un code à 4 chiffres le protège."}</span></div></div>
        <div class="inline-actions">${me.code
          ? `<button class="btn" type="button" data-code-set>${icon("edit")}Changer le code</button><button class="btn btn-ghost btn-danger" type="button" data-code-remove>Retirer le code</button>`
          : `<button class="btn" type="button" data-code-set>${icon("lock")}Ajouter un code</button>`}</div>
      </div>
      ${boot.claude_possible ? `<label class="check access-claude"><input type="checkbox" data-claude ${me.claude ? "checked" : ""}>
        <span><b>Claude Desktop peut lire mes données</b>
        <span class="hint">Séances, sommeil, poids… quand quelqu'un le lui demande sur ce PC. ${me.principal ? "Coché d'office pour l'utilisateur principal." : "Décoché d'office pour les autres profils."}</span></span></label>` : ""}`;
    box.querySelector("[data-code-set]")?.addEventListener("click", () => codeDialog(me.code ? "change" : "add"));
    box.querySelector("[data-code-remove]")?.addEventListener("click", () => codeDialog("remove"));
    box.querySelector("[data-claude]")?.addEventListener("change", async (e) => {
      try {
        const res = await api.put("/api/utilisateurs/moi", { claude: e.target.checked });
        me = res.utilisateur;
        toast(me.claude ? "Claude Desktop peut lire tes données." : "Claude Desktop ne lit plus tes données.");
        onChange?.(res);
      } catch (err) {
        e.target.checked = !e.target.checked;
        toast(err.message, { error: true });
      }
    });
  };

  const codeDialog = (mode) => {
    const titles = { add: "Ajouter un code", change: "Changer le code", remove: "Retirer le code" };
    const dialog = openDialog(`<form class="dlg dlg-code-edit" method="dialog" novalidate>
        <div class="dlg-head"><h2>${titles[mode]}</h2><p>${mode === "remove" ? "Ton profil s'ouvrira sans code." : "4 chiffres, à retenir : il sera demandé pour entrer dans ton profil."}</p></div>
        <div class="dlg-body form-grid">
          ${mode !== "add" ? `<label class="field"><span>Code actuel</span><input type="password" inputmode="numeric" maxlength="4" autocomplete="off" name="ancien"></label>` : ""}
          ${mode !== "remove" ? `<label class="field"><span>Nouveau code</span><input type="password" inputmode="numeric" maxlength="4" autocomplete="off" name="code"></label>
          <label class="field"><span>Encore une fois</span><input type="password" inputmode="numeric" maxlength="4" autocomplete="off" name="encore"></label>` : ""}
          <p class="code-error" role="alert" data-error></p>
        </div>
        <div class="dlg-foot"><button class="btn" type="button" data-cancel>Annuler</button><button class="btn btn-primary" type="submit">${icon("check")}${mode === "remove" ? "Retirer" : "Enregistrer"}</button></div>
      </form>`);
    const form = dialog.querySelector("form");
    const error = dialog.querySelector("[data-error]");
    form.querySelectorAll("input").forEach((input) => input.addEventListener("input", () => {
      input.value = input.value.replace(/\D/g, "").slice(0, 4);
      error.textContent = "";
    }));
    dialog.querySelector("[data-cancel]").addEventListener("click", () => dialog.close());
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const value = (name) => form.elements[name]?.value || "";
      if (mode !== "remove") {
        if (!/^\d{4}$/.test(value("code"))) { error.textContent = "Le code fait 4 chiffres."; return; }
        if (value("code") !== value("encore")) { error.textContent = "Les deux codes ne sont pas identiques."; return; }
      }
      try {
        const res = await api.put("/api/utilisateurs/moi", { code: mode === "remove" ? null : value("code"), ancien: value("ancien") });
        me = res.utilisateur;
        dialog.close();
        toast(mode === "remove" ? "Code retiré." : "Code enregistré.");
        render();
        onChange?.(res);
      } catch (err) {
        error.textContent = err.message;
      }
    });
    form.querySelector("input")?.focus();
  };
  render();
}

// ====================================================== Réglages : gestion des utilisateurs
export async function usersPanel(box, boot, { toast, onChange }) {
  let state;
  const load = async () => {
    try {
      state = await api.get("/api/utilisateurs", null, { fresh: true });
    } catch (err) {
      box.innerHTML = `<p class="computed warn">${icon("warning")}<span>Liste des profils indisponible : ${F.escape(err.message)}</span></p>`;
      return;
    }
    render();
  };
  const summary = (u) => {
    const parts = [u.seances ? `${F.int(u.seances)} séance${u.seances > 1 ? "s" : ""}` : "aucune séance"];
    if (u.cle_refusee) parts.push("clé refusée par Garmin");
    else parts.push(u.cle ? (u.derniere_synchro ? `synchro ${F.relative(u.derniere_synchro)}` : "clé enregistrée") : "pas encore de clé");
    return parts.join(" · ");
  };
  const render = () => {
    const users = state.utilisateurs;
    box.innerHTML = `
      <ul class="users-list">${users.map((u) => `<li class="user-row" data-id="${F.escape(u.id)}">
          ${avatar(u, 40)}
          <div class="user-text"><b>${F.escape(u.prenom)}${u.courant ? " <small>(toi)</small>" : ""}</b>
            <span class="user-badges">${u.principal ? `<span class="badge-soft">Principal</span>` : ""}${u.code ? `<span class="badge-soft">${icon("lock")}Code</span>` : ""}${boot.claude_possible && u.claude ? `<span class="badge-soft">${icon("chat")}Claude</span>` : ""}</span>
            <span class="user-sum">${F.escape(summary(u))}</span></div>
          <div class="user-actions">
            <button class="btn btn-ghost" type="button" data-rename>${icon("edit")}Renommer</button>
            ${u.code && !u.courant ? `<button class="btn btn-ghost" type="button" data-clear-code>${icon("lock")}Effacer le code</button>` : ""}
            ${!u.courant ? `<button class="btn btn-ghost" type="button" data-switch>${icon("user")}Ouvrir</button>` : ""}
            ${!u.principal ? `<button class="btn btn-ghost btn-danger icon-btn" type="button" data-delete title="Supprimer ce profil" aria-label="Supprimer le profil de ${F.escape(u.prenom)}">${icon("trash")}</button>` : ""}
          </div></li>`).join("")}</ul>
      ${users.length < state.max ? `<form class="user-add" data-add novalidate>
          <label class="field"><span>Prénom</span><input type="text" name="prenom" maxlength="30" autocomplete="off" required></label>
          <label class="field"><span>Code <small>(facultatif)</small></span><input type="password" name="code" inputmode="numeric" maxlength="4" autocomplete="off" placeholder="4 chiffres"></label>
          <button class="btn btn-primary" type="submit">${icon("plus")}Ajouter un utilisateur</button>
          <p class="hint" data-add-status role="status"></p>
        </form>` : `<p class="hint">${F.int(state.max)} profils au plus.</p>`}`;
    wire();
  };
  const wire = () => {
    const users = state.utilisateurs;
    const row = (el) => users.find((u) => u.id === el.closest("[data-id]").dataset.id);
    box.querySelectorAll("[data-rename]").forEach((b) => b.addEventListener("click", () => {
      const u = row(b);
      const dialog = openDialog(`<form class="dlg" method="dialog" novalidate>
          <div class="dlg-head"><h2>Renommer ${F.escape(u.prenom)}</h2></div>
          <div class="dlg-body"><label class="field"><span>Prénom</span><input type="text" name="prenom" maxlength="30" value="${F.escape(u.prenom)}"></label><p class="code-error" role="alert" data-error></p></div>
          <div class="dlg-foot"><button class="btn" type="button" data-cancel>Annuler</button><button class="btn btn-primary" type="submit">${icon("check")}Renommer</button></div>
        </form>`);
      dialog.querySelector("[data-cancel]").addEventListener("click", () => dialog.close());
      dialog.querySelector("form").addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          state = await api.put(`/api/utilisateurs/${encodeURIComponent(u.id)}`, { prenom: e.target.elements.prenom.value });
          dialog.close();
          render();
          onChange?.();
        } catch (err) {
          dialog.querySelector("[data-error]").textContent = err.message;
        }
      });
      dialog.querySelector("input").select();
    }));
    box.querySelectorAll("[data-clear-code]").forEach((b) => b.addEventListener("click", async () => {
      const u = row(b);
      if (!(await confirm(`Effacer le code de ${u.prenom} ?`, "Son profil s'ouvrira sans code ; il pourra en choisir un nouveau dans ses réglages.", "Effacer le code"))) return;
      try {
        state = await api.del(`/api/utilisateurs/${encodeURIComponent(u.id)}/code`);
        toast(`Code de ${u.prenom} effacé.`);
        render();
      } catch (err) {
        toast(err.message, { error: true });
      }
    }));
    box.querySelectorAll("[data-switch]").forEach((b) => b.addEventListener("click", () => switchTo(row(b), { toast })));
    box.querySelectorAll("[data-delete]").forEach((b) => b.addEventListener("click", async () => {
      const u = row(b);
      const ok = await confirm(`Supprimer le profil de ${u.prenom} ?`,
        `Ses séances, ses mesures, ses vues, ses réglages et sa clé Garmin seront effacés de cette installation (${summary(u)}). Ses données restent chez Garmin : il pourra tout réimporter dans un nouveau profil.`,
        "Supprimer le profil");
      if (!ok) return;
      try {
        state = await api.del(`/api/utilisateurs/${encodeURIComponent(u.id)}`);
        toast(`Profil de ${u.prenom} supprimé.`);
        render();
        onChange?.();
      } catch (err) {
        toast(err.message, { error: true });
      }
    }));
    const form = box.querySelector("[data-add]");
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const status = form.querySelector("[data-add-status]");
      const prenom = form.elements.prenom.value.trim();
      const code = form.elements.code.value.trim();
      if (!prenom) { status.textContent = "Indique un prénom."; form.elements.prenom.focus(); return; }
      if (code && !/^\d{4}$/.test(code)) { status.textContent = "Le code fait 4 chiffres (ou laisse-le vide)."; return; }
      try {
        const res = await api.post("/api/utilisateurs", { prenom, code: code || null });
        state = res;
        render();
        onChange?.();
        const created = res.cree;
        const added = box.querySelector(`[data-id="${CSS.escape(created.id)}"]`);
        added?.classList.add("just-added");
        added?.insertAdjacentHTML("beforeend", `<p class="user-next">${icon("info")}<span>Profil de ${F.escape(created.prenom)} créé. Ouvre-le pour y ajouter sa clé Garmin et lancer son premier import${boot.acces === "local" ? "" : " (depuis le serveur ou par Tailscale)"}.</span></p>`);
        toast(`Profil de ${created.prenom} créé.`);
      } catch (err) {
        status.textContent = err.message;
      }
    });
    form?.querySelector('[name="code"]')?.addEventListener("input", (e) => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 4); });
  };
  await load();
}
