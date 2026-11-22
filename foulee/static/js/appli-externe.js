// L'application partenaire (Réglages → Application partenaire ; par défaut Club en ligne) et les sites externes
// (Réglages → Sites externes) : un site dans Foulée, dans un cadre, avec précédent, suivant, recharger et « ouvrir
// dans le navigateur ». Chaque site externe peut avoir son logo (un PNG), sinon le petit globe ; celui de
// l'application partenaire se choisit dans la logothèque (voir logo-choice.js), comme le logo du club.
// Le nom du fichier évite « partner », que certains bloqueurs de pub arrêtent.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { logoChoice, logoLibrary, logoURL } from "./logo-choice.js";

function host(url) {
  try { return new URL(url).host; } catch (e) { return url; }
}

/** Le logo d'un site externe ou de l'application partenaire (id « partenaire »), ou le globe. */
export function siteIcon(site, id = site?.id) {
  return site?.logo ? `<img class="site-logo" src="/api/sites/${encodeURIComponent(id)}/logo?v=${site.logo}" alt="" width="18" height="18">` : icon("globe");
}

const LOGO_RULES = "PNG carré (ou presque), entre 64 × 64 et 512 × 512 pixels, 200 Ko au plus, fond transparent conseillé ; sans logo, le petit globe.";

/** Importer ou retirer un logo (application partenaire ou site externe) ; renvoie la nouvelle date du logo. */
async function sendLogo(id, file, toast) {
  if (file.size > 200 * 1024) throw new Error(`Logo trop lourd (${Math.round(file.size / 1024)} Ko) : 200 Ko au plus.`);
  const body = await api.putBlob(`/api/sites/${encodeURIComponent(id)}/logo`, file);
  toast("Logo enregistré.");
  return body.logo;
}

/** La page : barre d'outils et cadre, qui prend toute la hauteur restante de la fenêtre. siteId : un site externe. */
export function renderPartnerPage(page, boot, { keep, siteId = null }) {
  const site = siteId ? (boot.sites_externes || []).find((x) => x.id === siteId) : null;
  const app = siteId ? (site || {}) : (boot.partenaire || {});
  const section = siteId ? "sites" : "partenaire";
  if (!app.actif) {
    page.innerHTML = siteId
      ? `<header class="head"><div><h1>Site externe</h1></div></header>
      <p class="co-empty">Ce site n'est plus dans le menu : <a href="#/reglages?section=sites">Réglages → Sites externes</a>.</p>`
      : `<header class="head"><div><h1>Application partenaire</h1></div></header>
      <p class="co-empty">Elle n'est pas activée : <a href="#/reglages?section=partenaire">Réglages → Application partenaire</a>.</p>`;
    return;
  }
  page.innerHTML = `
    <header class="head xa-head">
      <div><h1><span class="site-title-logo">${siteId ? siteIcon(site) : siteIcon(app, "partenaire")}</span>${F.escape(app.nom)}</h1><div class="head-sub"><span>${F.escape(host(app.adresse))}</span></div></div>
      <div class="xa-bar" role="toolbar" aria-label="Navigation dans ${F.escape(app.nom)}">
        <button class="btn icon-btn" type="button" data-back title="Précédent" aria-label="Précédent">${icon("left")}</button>
        <button class="btn icon-btn" type="button" data-forward title="Suivant" aria-label="Suivant">${icon("right")}</button>
        <button class="btn icon-btn" type="button" data-reload title="Recharger (revient à la page de départ)" aria-label="Recharger">${icon("sync")}</button>
        <a class="btn" href="${F.escape(app.adresse)}" target="_blank" rel="noopener" title="Ouvrir dans le navigateur, si la connexion ne tient pas ici">${icon("external")}<span class="xa-label">Ouvrir dans le navigateur</span></a>
        <a class="btn btn-ghost icon-btn" href="#/reglages?section=${section}" title="${siteId ? "Régler les sites externes" : "Régler l'application partenaire"}" aria-label="Réglages">${icon("settings")}</a>
      </div>
    </header>
    <div class="xa-frame"><iframe src="${F.escape(app.adresse)}" title="${F.escape(app.nom)}" referrerpolicy="strict-origin-when-cross-origin"
      allow="clipboard-read; clipboard-write; fullscreen"></iframe></div>`;
  const frame = page.querySelector("iframe");
  // Précédent et suivant : l'historique de la fenêtre comprend celui du cadre (le navigateur n'en laisse pas
  // lire davantage d'un autre site). Recharger repart de l'adresse réglée : la page courante d'un autre site
  // n'est pas lisible depuis Foulée.
  page.querySelector("[data-back]").addEventListener("click", () => history.back());
  page.querySelector("[data-forward]").addEventListener("click", () => history.forward());
  page.querySelector("[data-reload]").addEventListener("click", () => { frame.src = app.adresse; });
  const fit = () => {
    const top = frame.getBoundingClientRect().top + window.scrollY;
    frame.style.height = `${Math.max(420, window.innerHeight - top - 18)}px`;
  };
  fit();
  window.addEventListener("resize", fit);
  keep?.({ dispose: () => window.removeEventListener("resize", fit) });
}

/** Réglages → Application partenaire. */
export function partnerPanel(box, boot, { toast, onChange, logos = logoLibrary(boot) }) {
  const app = { ...(boot.partenaire || {}) };
  box.innerHTML = `
    <label class="check club-toggle"><input type="checkbox" data-on ${app.actif ? "checked" : ""}>
      <span><b>Afficher l'application dans la colonne de gauche</b><span class="hint">Elle s'ajoute sous « Nouvelle vue » et s'ouvre dans Foulée, avec précédent, suivant et recharger.</span></span></label>
    <div class="form-grid xa-form">
      <label class="field"><span>Nom dans le menu</span><input type="text" data-k="nom" maxlength="30" value="${F.escape(app.nom || "")}" placeholder="Club en ligne"></label>
      <label class="field xa-url"><span>Adresse</span><input type="text" inputmode="url" data-k="adresse" maxlength="500" value="${F.escape(app.adresse || "")}" placeholder="https://app.clubenligne.fr/"
        spellcheck="false" autocomplete="off"><span class="hint">Tu peux viser une page précise en ajoutant la fin de son adresse, par exemple <code>https://app.clubenligne.fr/entrainements</code> (copie-la depuis ton navigateur).</span></label>
    </div>
    <div class="site-logo-line">
      <div class="site-logo-box" data-logo-preview>${siteIcon(app, "partenaire")}</div>
      <div class="site-logo-choice"><b>Logo dans le menu</b><span class="hint">Choisis-le dans la liste (la même que pour le logo du club), ou importe le tien en lui donnant un nom. Sans logo, le petit globe.</span>
        <div data-logo-choice></div></div>
    </div>
    <div class="inline-actions">
      <button class="btn btn-primary" type="button" data-save>${icon("check")}Enregistrer</button>
      <a class="btn" data-try href="${F.escape(app.adresse || "")}" target="_blank" rel="noopener">${icon("external")}Essayer l'adresse</a>
      <button class="btn btn-ghost" type="button" data-default>${icon("reset")}Remettre Club en ligne</button>
    </div>
    <p class="hint">Si la connexion au site ne tient pas dans Foulée (certains sites refusent d'être ouverts dans une autre application), le bouton « Ouvrir dans le navigateur » de la page l'ouvre à part.</p>`;
  const input = (k) => box.querySelector(`[data-k=${k}]`);
  const save = async (message) => {
    const body = { actif: box.querySelector("[data-on]").checked, nom: input("nom").value.trim(), adresse: input("adresse").value.trim() };
    try {
      const res = await api.put("/api/settings", { partenaire: body });
      const saved = res.reglages.partenaire;
      input("nom").value = saved?.nom || "";
      input("adresse").value = saved?.adresse || "";
      box.querySelector("[data-try]").href = saved?.adresse || "#";
      toast(message || "Application partenaire enregistrée.");
      await onChange?.();
    } catch (err) { toast(err.message, { error: true }); }
  };
  box.querySelector("[data-on]").addEventListener("change", (e) => save(e.target.checked
    ? `« ${input("nom").value.trim() || "Club en ligne"} » s'ajoute dans la colonne de gauche.` : "Application partenaire retirée du menu."));
  box.querySelector("[data-save]").addEventListener("click", () => save());
  box.querySelector("[data-default]").addEventListener("click", () => {
    input("nom").value = "Club en ligne";
    input("adresse").value = "https://app.clubenligne.fr/";
    save("Club en ligne remis par défaut.");
  });
  input("adresse").addEventListener("input", () => { box.querySelector("[data-try]").href = input("adresse").value.trim() || "#"; });
  // Le logo du menu : la logothèque (logos de l'ACCT livrés avec Foulée, logos importés et nommés)
  logoChoice(box.querySelector("[data-logo-choice]"), logos, {
    use: "partenaire", none: "Le petit globe", toast, onChange,
    onPreview: (entry) => {
      box.querySelector("[data-logo-preview]").innerHTML = entry ? `<img class="site-logo" src="${logoURL(entry)}" alt="">` : icon("globe");
    },
  });
}

/** Réglages → Sites externes : d'autres sites, chacun avec son entrée dans la colonne de gauche et son logo. */
export function sitesPanel(box, boot, { toast, onChange, rules = LOGO_RULES }) {
  let sites = (boot.sites_externes || []).map((x) => ({ ...x }));
  const send = async (list, message) => {
    const res = await api.put("/api/settings", { sites_externes: list.map(({ id, nom, adresse, actif }) => ({ id, nom, adresse, actif })) });
    const kept = res.reglages.sites_externes || [];
    sites = kept.map((x) => ({ ...x, logo: sites.find((old) => old.id === x.id)?.logo || null }));
    if (message) toast(message);
    await onChange?.();
    draw();
  };
  const save = (list, message) => send(list, message).catch((err) => { toast(err.message, { error: true }); draw(); });
  const row = (x, i) => `
    <li class="site-row" data-id="${F.escape(x.id)}">
      <div class="site-logo-box" title="Logo (${F.escape(rules)})">${siteIcon(x)}</div>
      <div class="site-fields">
        <input type="text" data-k="nom" maxlength="30" value="${F.escape(x.nom)}" aria-label="Nom dans le menu">
        <input type="text" inputmode="url" data-k="adresse" maxlength="500" value="${F.escape(x.adresse)}" aria-label="Adresse" spellcheck="false" autocomplete="off">
        <div class="site-actions">
          <label class="check"><input type="checkbox" data-k="actif" ${x.actif ? "checked" : ""}><span>Dans la colonne de gauche</span></label>
          <label class="btn btn-small btn-ghost">${icon("upload")}${x.logo ? "Changer le logo" : "Importer un logo"}<input type="file" accept="image/png" data-logo hidden></label>
          ${x.logo ? `<button class="btn btn-small btn-ghost" type="button" data-nologo>${icon("globe")}Remettre le globe</button>` : ""}
          <a class="btn btn-small btn-ghost" href="${F.escape(x.adresse)}" target="_blank" rel="noopener">${icon("external")}Essayer</a>
          <span class="site-move">
            <button class="btn btn-small btn-ghost icon-btn" type="button" data-up ${i === 0 ? "disabled" : ""} title="Monter" aria-label="Monter">${icon("moveup")}</button>
            <button class="btn btn-small btn-ghost icon-btn" type="button" data-remove title="Supprimer ce site" aria-label="Supprimer ce site">${icon("trash")}</button>
          </span>
        </div>
      </div>
    </li>`;
  const draw = () => {
    box.innerHTML = `
      ${sites.length ? `<ol class="site-list">${sites.map(row).join("")}</ol>` : `<p class="hint">Aucun site pour l'instant.</p>`}
      <div class="form-grid xa-form site-add" ${sites.length >= 8 ? "hidden" : ""}>
        <label class="field"><span>Nom dans le menu</span><input type="text" data-new="nom" maxlength="30" placeholder="FFA, Strava, ma ligue…"></label>
        <label class="field xa-url"><span>Adresse</span><input type="text" inputmode="url" data-new="adresse" maxlength="500" placeholder="https://www.athle.fr/" spellcheck="false" autocomplete="off"></label>
      </div>
      <div class="inline-actions" ${sites.length >= 8 ? "hidden" : ""}><button class="btn btn-primary" type="button" data-add>${icon("plus")}Ajouter le site</button></div>
      <p class="hint">Logo : ${F.escape(rules)} Il reste sur ta machine. Huit sites au plus.</p>`;
    const add = box.querySelector("[data-add]");
    if (add) add.addEventListener("click", () => {
      const nom = box.querySelector("[data-new=nom]").value.trim();
      const adresse = box.querySelector("[data-new=adresse]").value.trim();
      if (!nom || !adresse) { toast("Un nom et une adresse.", { error: true }); return; }
      save([...sites, { nom, adresse, actif: true }], `« ${nom} » s'ajoute dans la colonne de gauche.`);
    });
    box.querySelectorAll(".site-row").forEach((li) => {
      const id = li.dataset.id;
      const index = sites.findIndex((x) => x.id === id);
      const current = sites[index];
      const field = (k) => li.querySelector(`[data-k=${k}]`);
      const edited = () => sites.map((x) => x.id === id ? { ...x, nom: field("nom").value.trim(), adresse: field("adresse").value.trim(), actif: field("actif").checked } : x);
      field("nom").addEventListener("change", () => save(edited(), "Enregistré."));
      field("adresse").addEventListener("change", () => save(edited(), "Enregistré."));
      field("actif").addEventListener("change", (e) => save(edited(), e.target.checked ? `« ${current.nom} » revient dans la colonne de gauche.` : `« ${current.nom} » retiré de la colonne de gauche.`));
      li.querySelector("[data-up]").addEventListener("click", () => {
        const list = [...sites];
        [list[index - 1], list[index]] = [list[index], list[index - 1]];
        save(list);
      });
      li.querySelector("[data-remove]").addEventListener("click", async () => {
        if (!window.confirm(`Supprimer « ${current.nom} » ?`)) return;
        if (current.logo) await api.del(`/api/sites/${encodeURIComponent(id)}/logo`).catch(() => {});
        save(sites.filter((x) => x.id !== id), `« ${current.nom} » supprimé.`);
      });
      li.querySelector("[data-logo]").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
          const version = await sendLogo(id, file, toast);
          sites = sites.map((x) => x.id === id ? { ...x, logo: version } : x);
          await onChange?.();
          draw();
        } catch (err) { toast(err.message, { error: true }); }
      });
      const nologo = li.querySelector("[data-nologo]");
      if (nologo) nologo.addEventListener("click", async () => {
        try {
          await api.del(`/api/sites/${encodeURIComponent(id)}/logo`);
          sites = sites.map((x) => x.id === id ? { ...x, logo: null } : x);
          toast("Le globe est remis.");
          await onChange?.();
          draw();
        } catch (err) { toast(err.message, { error: true }); }
      });
    });
  };
  draw();
}
