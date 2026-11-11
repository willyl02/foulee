// Page « Un bug, une idée ? Parles-en ! ». D'abord un coup d'œil dans l'aide et sur GitHub, puis un
// titre, un message et des captures. Foulée met le tout en forme et ouvre la page « nouveau sujet »
// de GitHub, déjà remplie : rien ne part sans un clic, et le texte joint se lit avant l'envoi.
import * as api from "./api.js";
import { confirm } from "./editor.js";
import { suggest } from "./faq.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const DRAFT_KEY = "foulee-retour";
const MAX_SHOTS = 5;
const MAX_SHOT_BYTES = 10 * 1024 * 1024;
const MAX_URL = 7000;     // au-delà, GitHub répond « 414 URI Too Long » : le message passe par le presse-papiers
const MAX_MAILTO = 1800;  // les logiciels de messagerie coupent les liens mailto trop longs

export const KINDS = {
  bug: {
    label: "Un bug", icone: "bug", prefixe: "Bug", aide: "Quelque chose ne marche pas comme prévu.", section: "Ce qui se passe",
    titre: "Ex. : la synchro s'arrête à 40 %",
    message: "Ce que tu faisais, ce qui s'est passé, ce que tu attendais.\nUn message d'erreur ? Copie-le tel quel.\nÇa arrive à chaque fois, ou de temps en temps ?",
  },
  idee: {
    label: "Une idée", icone: "bulb", prefixe: "Idée", aide: "Une amélioration, une tuile, une donnée qui te manque.", section: "L'idée",
    titre: "Ex. : une tuile pour suivre l'usure de mes chaussures",
    message: "Ce qui te manque, à quoi ça te servirait, comment tu l'imagines.",
  },
  question: {
    label: "Une question", icone: "help", prefixe: "Question", aide: "Tu ne trouves pas comment faire quelque chose.", section: "La question",
    titre: "Ex. : comment comparer deux saisons ?",
    message: "Ce que tu cherches à faire, ce que tu as déjà essayé.",
  },
};

// Captures gardées le temps de la session : on peut aller voir l'aide et revenir sans les perdre
let shots = [];
let shotSeq = 0;

// ================================================================ outils
function store(value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    if (value === null) localStorage.removeItem(DRAFT_KEY); else localStorage.setItem(DRAFT_KEY, JSON.stringify(value));
  } catch (e) { /* stockage indisponible : le brouillon vit le temps de la page */ }
  return null;
}

/** Copie du texte : presse-papiers moderne, sinon l'ancienne méthode (pages en http sur le réseau local). */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (e) { /* on tente l'ancienne méthode */ }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;top:-1000px;opacity:0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  area.remove();
  return ok;
}

const canCopyImages = () => Boolean(window.isSecureContext && navigator.clipboard?.write && window.ClipboardItem);

async function asPng(blob) {
  if (blob.type === "image/png") return blob;
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  canvas.getContext("2d").drawImage(bitmap, 0, 0);
  bitmap.close?.();
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("conversion impossible"))), "image/png"));
}

function download(shot, index) {
  const link = document.createElement("a");
  const ext = (shot.type.split("/")[1] || "png").replace("jpeg", "jpg").replace(/[^a-z0-9]/g, "");
  link.href = shot.url;
  link.download = `foulee-capture-${index + 1}.${ext}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function platform() {
  const ua = navigator.userAgent;
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
  if (/Android/.test(ua)) return "android";
  if (/Windows/.test(ua)) return "windows";
  if (/Macintosh|Mac OS X/.test(ua)) return "mac";
  return "autre";
}

const SCREENSHOT_TIPS = {
  windows: "Astuce : <kbd>Windows</kbd> + <kbd>Maj</kbd> + <kbd>S</kbd> capture une partie de l'écran ; colle-la ensuite ici avec <kbd>Ctrl</kbd> + <kbd>V</kbd>.",
  mac: "Astuce : <kbd>⌘</kbd> + <kbd>Ctrl</kbd> + <kbd>Maj</kbd> + <kbd>4</kbd> capture une partie de l'écran ; colle-la ensuite ici avec <kbd>⌘</kbd> + <kbd>V</kbd>.",
  android: "Astuce : appuie en même temps sur Marche/Arrêt et Volume bas pour faire une capture, puis choisis-la dans ta galerie.",
  ios: "Astuce : appuie en même temps sur le bouton latéral et Volume haut pour faire une capture, puis choisis-la dans tes photos.",
  autre: "",
};

function systemName() {
  const ua = navigator.userAgent;
  const android = ua.match(/Android ([\d.]+)/);
  const ios = ua.match(/OS (\d+)_(\d+)/);
  if (/Windows NT 10/.test(ua)) return "Windows 10 ou 11";
  if (/Windows/.test(ua)) return "Windows";
  if (android) return `Android ${android[1]}`;
  if (/iPhone|iPad|iPod/.test(ua)) return `${/iPad/.test(ua) ? "iPad" : "iPhone"}${ios ? ` (iOS ${ios[1]}.${ios[2]})` : ""}`;
  if (/Macintosh|Mac OS X/.test(ua)) return navigator.maxTouchPoints > 1 ? "iPad" : "macOS";
  if (/CrOS/.test(ua)) return "ChromeOS";
  if (/Linux/.test(ua)) return "Linux";
  return "inconnu";
}

async function preciseWindows() {
  // Seule l'API « Client Hints » distingue Windows 11 de Windows 10
  try {
    const data = await navigator.userAgentData?.getHighEntropyValues?.(["platformVersion"]);
    if (data?.platform === "Windows" && data.platformVersion) return Number(data.platformVersion.split(".")[0]) >= 13 ? "Windows 11" : "Windows 10";
  } catch (e) { /* navigateur sans Client Hints */ }
  return null;
}

function browserName() {
  const ua = navigator.userAgent;
  const known = [[/Edg(?:A|iOS)?\/(\d+)/, "Edge"], [/OPR\/(\d+)/, "Opera"], [/SamsungBrowser\/(\d+)/, "Samsung Internet"],
    [/(?:Firefox|FxiOS)\/(\d+)/, "Firefox"], [/(?:Chrome|CriOS)\/(\d+)/, "Chrome"], [/Version\/(\d+)[\d.]* .*Safari/, "Safari"]];
  for (const [pattern, name] of known) {
    const match = ua.match(pattern);
    if (match) return `${name} ${match[1]}`;
  }
  return "inconnu";
}

function themeName() {
  const chosen = document.documentElement.dataset.theme;
  if (chosen) return chosen === "dark" ? "sombre" : "clair";
  return matchMedia("(prefers-color-scheme: dark)").matches ? "sombre (automatique)" : "clair (automatique)";
}

/** « #/vue/accueil » → « vue « Accueil » » : la page où l'on était avant d'ouvrir le formulaire. */
function pageName(hash, boot) {
  if (!hash || hash.startsWith("#/retours")) return null;
  const [path, query] = hash.slice(1).split("?");
  const view = path.match(/^\/vue\/([^/]+)/);
  if (view) {
    const id = decodeURIComponent(view[1]);
    const found = (boot.vues || []).find((v) => v.id === id);
    return `vue « ${found?.name || id} »${new URLSearchParams(query || "").get("seance") ? ", détail d'une séance" : ""}`;
  }
  return { "/reglages": "Réglages", "/bienvenue": "page de bienvenue", "/aide": "Aide" }[path] || "première vue";
}

function syncText(boot) {
  if (boot.demo) return "désactivée (mode démo)";
  const s = boot.synchro || {};
  if (s.en_cours) return "en cours";
  const last = s.derniere;
  const success = s.derniere_reussie ? `dernière réussie le ${F.dateTime(s.derniere_reussie)}` : "jamais réussie";
  if (!last) return success;
  if (last.statut === "echec") {
    const error = String(last.resume?.garmin?.erreur || "").replace(/\s+/g, " ").slice(0, 300);
    return `échec le ${F.dateTime(last.fin)}${error ? ` : « ${error} »` : ""} ; ${success}`;
  }
  if (last.statut === "partiel") return `${success}, avec ${(last.resume?.garmin?.erreurs || []).length} alerte(s)`;
  return success;
}

function keyText(boot) {
  if (boot.demo) return "inutile (mode démo)";
  if (boot.cle_refusee) return `refusée par Garmin depuis le ${F.dateTime(boot.cle_refusee.depuis)}`;
  return boot.cle ? "enregistrée" : "absente";
}

/** Informations techniques jointes au message : rien de personnel (ni clé, ni chemin, ni données). */
function techLines(boot, from, system) {
  const install = { exe: "application Windows", serveur: "serveur", dev: "installation manuelle" }[boot.installation] || boot.installation;
  const v = boot.volumes || {};
  return [
    `Foulée ${boot.version}, ${install}${boot.demo ? ", mode démo" : ""}`,
    `Système : ${system} ; navigateur : ${browserName()}`,
    `Écran : ${screen.width} × ${screen.height}, fenêtre ${innerWidth} × ${innerHeight}, thème ${themeName()}`,
    `Ouvert ${boot.acces === "local" ? "sur la machine où tourne Foulée" : "depuis un autre appareil (réseau)"}`,
    ...((boot.utilisateurs || []).length > 1 ? [`Profils : ${boot.utilisateurs.length}, envoyé depuis ${boot.utilisateur?.principal ? "le profil principal" : "un autre profil"}`] : []),
    ...(from ? [`Page d'origine : ${from}`] : []),
    `Clé API Garmin : ${keyText(boot)}`,
    `Synchro : ${syncText(boot)}`,
    `Contenu : ${F.int(v.activities)} séances, ${F.int(v.daily)} valeurs quotidiennes${boot.premiere_date ? ` depuis le ${boot.premiere_date}` : ""}`,
  ];
}

function fullTitle(kind, title) {
  const prefix = KINDS[kind].prefixe;
  const clean = title.trim().replace(/\s+/g, " ");
  return new RegExp(`^${prefix}\\s*:`, "i").test(clean) ? clean : `${prefix} : ${clean}`;
}

function markdownBody(kind, message, lines, count) {
  const parts = [`### ${KINDS[kind].section}`, "", message.trim(), ""];
  if (count) parts.push("### Captures", `<!-- Colle (Ctrl+V) ou glisse ici tes ${count > 1 ? `${count} captures` : "captures"} -->`, "", "");
  if (lines) parts.push("<details><summary>Informations techniques</summary>", "", ...lines.map((l) => `- ${l}`), "", "</details>", "");
  parts.push("_Préparé avec le formulaire « Un bug, une idée ? » de Foulée._");
  return parts.join("\n");
}

function plainBody(kind, message, lines, count) {
  const parts = [message.trim(), ""];
  if (count) parts.push(`(${count > 1 ? `${count} captures jointes` : "1 capture jointe"})`, "");
  if (lines) parts.push("-- Informations techniques --", ...lines.map((l) => `• ${l}`), "");
  return parts.join("\n");
}

// ================================================================ page
/**
 * @param {HTMLElement} page
 * @param {object} boot état de /api/bootstrap
 * @param {{ toast: Function, from?: string, kind?: string, keep: Function }} ctx
 */
export function renderFeedback(page, boot, { toast, from = "", kind: wantedKind = "", keep }) {
  const info = boot.retours || { depot: "willyl02/foulee", issues: "https://github.com/willyl02/foulee/issues", nouveau: "https://github.com/willyl02/foulee/issues/new", email: null };
  const saved = store() || {};
  const kindOf = (k) => (KINDS[k] ? k : null);
  const draft = {
    kind: kindOf(wantedKind) || kindOf(saved.kind) || "bug",
    titre: saved.titre || "", message: saved.message || "", infos: saved.infos !== false,
  };
  const origin = pageName(from, boot);
  let system = systemName();
  const os = platform();
  const coarse = matchMedia("(pointer: coarse)").matches;

  page.innerHTML = `
    <header class="head"><div><h1>Un bug, une idée ? Parles-en !</h1>
      <div class="head-sub">Un défaut, une envie, une question : quelques lignes suffisent. Ton message arrive sur GitHub, où chaque sujet a sa page et sa discussion.</div></div></header>
    <div class="fb">
      <section class="fb-card" aria-labelledby="fb-first">
        <h2 id="fb-first"><span class="fb-num" aria-hidden="true">1</span>D'abord, un coup d'œil</h2>
        <p class="fb-lead">Ta réponse existe peut-être déjà : dans <a href="#/aide">l'aide de Foulée</a>, ou parmi les sujets déjà ouverts sur GitHub.</p>
        <form class="fb-search" data-search-form role="search">
          <label class="search-field">${icon("search")}<input type="search" data-q placeholder="Quelques mots : synchro, clé, zones…" aria-label="Chercher dans l'aide et sur GitHub"></label>
          <button class="btn" type="submit">${icon("external")}Chercher sur GitHub</button>
        </form>
        <div class="fb-suggest" data-suggest-top aria-live="polite"></div>
        <div class="fb-github">
          <h3>Que trouve-t-on sur GitHub ?</h3>
          <p>GitHub est le site où vit le code de Foulée. Son onglet <b>Issues</b> (« sujets ») rassemble tous les bugs signalés et toutes les idées proposées : chacun a sa page, avec la discussion et ce qui a été fait.</p>
          <dl class="fb-terms">
            <div><dt>Open / Closed</dt><dd>Ouverts : en cours. Fermés : corrigés, réalisés ou écartés, avec l'explication dans la discussion.</dd></div>
            <div><dt>Étiquettes</dt><dd><span class="fb-label">bug</span> un défaut, <span class="fb-label">enhancement</span> une idée, <span class="fb-label">question</span> une question.</dd></div>
            <div><dt>Recherche</dt><dd>Quelques mots dans la barre de recherche ; regarde aussi les sujets fermés : la réponse y est souvent.</dd></div>
            <div><dt>Déjà signalé ?</dt><dd>Ajoute un 👍 au premier message, ou un commentaire si tu as du nouveau : ça vaut mieux qu'un doublon, et tu seras prévenu des réponses.</dd></div>
          </dl>
          <p class="fb-visibility" data-visibility>Lire les sujets ne demande rien ; pour en écrire un, il faut un compte GitHub (gratuit).</p>
          <a class="btn btn-ghost" href="${F.escape(info.issues)}" target="_blank" rel="noopener">${icon("external")}Voir tous les sujets sur GitHub</a>
        </div>
      </section>

      <form class="fb-card fb-form" data-form novalidate aria-labelledby="fb-second">
        <h2 id="fb-second"><span class="fb-num" aria-hidden="true">2</span>Raconte</h2>
        <fieldset class="fb-kinds">
          <legend>De quoi s'agit-il ?</legend>
          ${Object.entries(KINDS).map(([id, k]) => `<label class="fb-kind"><input class="sr-only" type="radio" name="kind" value="${id}" ${id === draft.kind ? "checked" : ""}>
            ${icon(k.icone)}<b>${k.label}</b><span>${k.aide}</span></label>`).join("")}
        </fieldset>
        <label class="field"><span>Titre</span>
          <input type="text" name="titre" maxlength="120" autocomplete="off" value="${F.escape(draft.titre)}" aria-describedby="fb-title-hint">
          <span class="hint" id="fb-title-hint">Une phrase qui résume, pour retrouver le sujet d'un coup d'œil.</span></label>
        <div class="fb-suggest" data-suggest-title aria-live="polite"></div>
        <label class="field"><span>Message</span>
          <textarea name="message" rows="7" maxlength="6000">${F.escape(draft.message)}</textarea></label>
        <div class="fb-shots">
          <div class="fb-drop" data-drop>
            ${icon("image")}
            <div><b>Des captures d'écran ?</b> (facultatif, ${MAX_SHOTS} au plus)
              <span>${coarse ? "" : "Glisse-les ici, colle-les, ou "}<button class="fb-link" type="button" data-pick>${coarse ? "Choisis des images" : "choisis des fichiers"}</button>.</span>
              ${SCREENSHOT_TIPS[os] ? `<span class="fb-tip">${SCREENSHOT_TIPS[os]}</span>` : ""}</div>
            <input type="file" accept="image/*" multiple hidden data-file>
          </div>
          <ul class="fb-shot-list" data-shots></ul>
        </div>
        <label class="check"><input type="checkbox" name="infos" ${draft.infos ? "checked" : ""}>Joindre les informations techniques</label>
        <details class="fb-tech" data-tech>
          <summary>Voir ce qui sera joint</summary>
          <p class="hint">Version de Foulée, système, navigateur, page d'origine, état de la clé et de la synchro. Ni ta clé, ni tes mesures, ni le chemin de ton dossier.</p>
          <pre data-tech-text></pre>
        </details>
        <p class="fb-error" data-error role="alert" hidden></p>
        <div class="fb-actions">
          <button class="btn btn-primary" type="submit">${icon("external")}Envoyer via GitHub</button>
          ${info.email ? `<button class="btn" type="button" data-mail>${icon("chat")}Envoyer par e-mail</button>` : ""}
          <button class="btn btn-ghost" type="button" data-copy>${icon("copy")}Copier le texte</button>
          <span class="spacer"></span>
          <button class="btn btn-ghost" type="button" data-clear>${icon("trash")}Effacer</button>
        </div>
        <p class="hint fb-after">GitHub s'ouvre dans un nouvel onglet, avec ton titre et ton message déjà remplis : tu relis, tu ajoutes tes captures, tu valides.${info.email ? " Pas de compte GitHub\u00a0? «\u00a0Envoyer par e-mail\u00a0» prépare un e-mail à la place." : ""}</p>
      </form>

      <section class="fb-card fb-next" data-next hidden tabindex="-1" aria-labelledby="fb-third"></section>

      <p class="fb-privacy">${icon("eye")}<span>Rien ne part sans ton clic. Ce que tu publies sur GitHub est visible de tous si le dépôt est public : n'y mets ni mot de passe, ni clé, ni adresse.</span></p>
    </div>`;

  const form = page.querySelector("[data-form]");
  const titleInput = form.elements.titre;
  const messageInput = form.elements.message;
  const techText = page.querySelector("[data-tech-text]");
  const errorBox = page.querySelector("[data-error]");
  const next = page.querySelector("[data-next]");
  const fileInput = page.querySelector("[data-file]");

  // ---------------------------------------------------- brouillon et aperçu
  const kind = () => form.elements.kind.value || "bug";
  const lines = () => (form.elements.infos.checked ? techLines(boot, origin, system) : null);
  const save = () => store({ kind: kind(), titre: titleInput.value, message: messageInput.value, infos: form.elements.infos.checked });
  const paint = () => {
    const k = KINDS[kind()];
    titleInput.placeholder = k.titre;
    messageInput.placeholder = k.message;
    techText.textContent = techLines(boot, origin, system).join("\n");
    page.querySelector("[data-tech]").hidden = !form.elements.infos.checked;
  };
  paint();
  preciseWindows().then((precise) => { if (precise) { system = precise; paint(); } });

  // ------------------------------------------------- réponses déjà dans l'aide
  const showSuggestions = (box, text, intro) => {
    const found = suggest(text, boot, 3);
    box.innerHTML = found.length ? `<p class="fb-suggest-intro">${intro}</p>${found.map((e) => `<details class="faq-item">
        <summary><span>${F.escape(e.item.q)}</span>${icon("chevron")}</summary><div class="faq-answer">${e.html}
        <p class="fb-more"><a href="#/aide?question=${e.id}">Voir dans l'aide</a></p></div></details>`).join("")}` : "";
  };
  let timer = null;
  const later = (fn) => { clearTimeout(timer); timer = setTimeout(fn, 250); };
  const query = page.querySelector("[data-q]");
  const topBox = page.querySelector("[data-suggest-top]");
  query.addEventListener("input", () => later(() => {
    showSuggestions(topBox, query.value, query.value.trim() ? "Dans l'aide de Foulée :" : "");
    if (query.value.trim() && !topBox.innerHTML) topBox.innerHTML = `<p class="fb-suggest-intro">Rien dans l'aide pour « ${F.escape(query.value.trim())} » : cherche sur GitHub.</p>`;
  }));
  page.querySelector("[data-search-form]").addEventListener("submit", (e) => {
    e.preventDefault();
    const words = query.value.trim();
    const url = words ? `${info.issues}?q=${encodeURIComponent(`is:issue ${words}`)}` : info.issues;
    window.open(url, "_blank", "noopener");
  });
  const titleBox = page.querySelector("[data-suggest-title]");
  titleInput.addEventListener("input", () => later(() => showSuggestions(titleBox, titleInput.value, "Déjà dans l'aide, peut-être :")));

  form.addEventListener("input", (e) => {
    if (e.target.name === "kind" || e.target.name === "infos") paint();
    errorBox.hidden = true;
    save();
  });
  form.addEventListener("change", (e) => { if (e.target.name === "kind") { paint(); save(); } });

  // ------------------------------------------------------------- captures
  const shotList = page.querySelector("[data-shots]");
  const paintShots = () => {
    shotList.innerHTML = shots.map((s, i) => `<li class="fb-shot">
        <img src="${s.url}" alt="Capture ${i + 1}">
        <div class="fb-shot-text"><b title="${F.escape(s.name)}">${F.escape(s.name)}</b><span>${F.size(s.size)}</span></div>
        <button class="btn btn-ghost icon-btn" type="button" data-remove="${s.id}" aria-label="Retirer la capture ${i + 1}" title="Retirer">${icon("trash")}</button>
      </li>`).join("");
    page.querySelector("[data-drop]").classList.toggle("full", shots.length >= MAX_SHOTS);
  };
  const addFiles = (files) => {
    const images = [...files].filter((f) => f.type.startsWith("image/"));
    if (!images.length) { toast("Seules les images sont acceptées (PNG, JPEG, WebP…).", { error: true }); return; }
    let refused = 0;
    images.forEach((file) => {
      if (shots.length >= MAX_SHOTS || file.size > MAX_SHOT_BYTES) { refused += 1; return; }
      const name = file.name && file.name !== "image.png" ? file.name : `capture-${shots.length + 1}.png`;
      shots.push({ id: ++shotSeq, name, type: file.type, size: file.size, blob: file, url: URL.createObjectURL(file) });
    });
    if (refused) toast(`${refused} image(s) laissée(s) de côté : ${MAX_SHOTS} captures au plus, de 10 Mo chacune.`, { error: true });
    paintShots();
  };
  shotList.addEventListener("click", (e) => {
    const id = Number(e.target.closest("[data-remove]")?.dataset.remove);
    if (!id) return;
    const shot = shots.find((s) => s.id === id);
    if (shot) URL.revokeObjectURL(shot.url);
    shots = shots.filter((s) => s.id !== id);
    paintShots();
  });
  page.querySelector("[data-pick]").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => { addFiles(fileInput.files); fileInput.value = ""; });
  const drop = page.querySelector("[data-drop]");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
  });
  // Ctrl+V n'importe où sur la page : une image du presse-papiers devient une capture
  const onPaste = (e) => {
    const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
    if (!files.length) return;
    e.preventDefault();
    addFiles(files);
    toast(files.length > 1 ? `${files.length} captures ajoutées.` : "Capture ajoutée.");
  };
  document.addEventListener("paste", onPaste);
  keep({ dispose: () => document.removeEventListener("paste", onPaste) });
  paintShots();

  // ------------------------------------------------------------- envoi
  const check = () => {
    const problems = [];
    if (titleInput.value.trim().length < 5) problems.push("un titre (5 caractères au moins)");
    if (messageInput.value.trim().length < 10) problems.push("quelques mots dans le message");
    if (!problems.length) return true;
    errorBox.textContent = `Il manque ${problems.join(" et ")}.`;
    errorBox.hidden = false;
    (titleInput.value.trim().length < 5 ? titleInput : messageInput).focus();
    return false;
  };
  const title = () => fullTitle(kind(), titleInput.value);

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!check()) return;
    const body = markdownBody(kind(), messageInput.value, lines(), shots.length);
    const base = `${info.nouveau}?title=${encodeURIComponent(title())}`;
    const url = `${base}&body=${encodeURIComponent(body)}`;
    if (url.length <= MAX_URL) {
      window.open(url, "_blank", "noopener");
      showNext({ channel: "github", url });
    } else {
      // Message trop long pour une adresse : on le fait copier, puis coller sur GitHub
      showNext({ channel: "github", url: base, longText: body });
    }
  });
  page.querySelector("[data-mail]")?.addEventListener("click", () => {
    if (!check()) return;
    const body = plainBody(kind(), messageInput.value, lines(), shots.length);
    const base = `mailto:${info.email}?subject=${encodeURIComponent(`[Foulée] ${title()}`)}`;
    const url = `${base}&body=${encodeURIComponent(body)}`;
    if (url.length <= MAX_MAILTO) {
      location.href = url;
      showNext({ channel: "mail", url });
    } else {
      showNext({ channel: "mail", url: base, longText: body });
    }
  });
  page.querySelector("[data-copy]").addEventListener("click", async () => {
    if (!check()) return;
    const text = `${title()}\n\n${markdownBody(kind(), messageInput.value, lines(), shots.length)}`;
    toast((await copyText(text)) ? "Texte copié : colle-le où tu veux." : "Copie impossible : sélectionne le texte à la main.", { error: false });
  });
  page.querySelector("[data-clear]").addEventListener("click", async () => {
    if ((titleInput.value || messageInput.value || shots.length)
      && !(await confirm("Effacer ce message ?", "Le titre, le message et les captures seront effacés.", "Effacer"))) return;
    clearAll();
  });

  function clearAll() {
    store(null);
    shots.forEach((s) => URL.revokeObjectURL(s.url));
    shots = [];
    titleInput.value = "";
    messageInput.value = "";
    titleBox.innerHTML = "";
    next.hidden = true;
    errorBox.hidden = true;
    paintShots();
    titleInput.focus();
  }

  // ------------------------------------------------- dernière étape (GitHub ou e-mail)
  function showNext({ channel, url, longText = "" }) {
    const github = channel === "github";
    const where = github ? "la zone de texte de GitHub" : "ton e-mail";
    const shotsHtml = shots.length ? `<ul class="fb-shot-list fb-shot-send">${shots.map((s, i) => `<li class="fb-shot">
          <img src="${s.url}" alt="Capture ${i + 1}">
          <div class="fb-shot-text"><b title="${F.escape(s.name)}">${F.escape(s.name)}</b><span>${F.size(s.size)}</span></div>
          <div class="fb-shot-tools">
            ${canCopyImages() && github ? `<button class="btn" type="button" data-copy-shot="${i}">${icon("copy")}Copier</button>` : ""}
            <button class="btn btn-ghost" type="button" data-download-shot="${i}">${icon("download")}Télécharger</button>
          </div></li>`).join("")}</ul>` : "";
    const steps = [];
    if (longText) {
      steps.push(`Ton message est trop long pour passer directement : <button class="btn" type="button" data-copy-long>${icon("copy")}Copier le message</button>`);
      steps.push(github
        ? `<a class="btn btn-primary" href="${F.escape(url)}" target="_blank" rel="noopener">${icon("external")}Ouvrir GitHub</a> puis colle le message (<kbd>Ctrl</kbd> + <kbd>V</kbd>) dans la grande zone de texte.`
        : `<a class="btn btn-primary" href="${F.escape(url)}">${icon("chat")}Ouvrir l'e-mail</a> puis colle le message (<kbd>Ctrl</kbd> + <kbd>V</kbd>).`);
    } else {
      steps.push(github
        ? "Un nouvel onglet s'est ouvert sur GitHub, avec ton titre et ton message. Connecte-toi si GitHub le demande."
        : `Ton logiciel de messagerie s'est ouvert avec un e-mail prêt, adressé à <b>${F.escape(info.email)}</b>.`);
    }
    if (shots.length) {
      steps.push(github
        ? (canCopyImages()
          ? `Ajoute tes captures : « Copier » sur une capture, puis <kbd>Ctrl</kbd> + <kbd>V</kbd> dans ${where}. Ou « Télécharger » et glisse le fichier dans ${where}.`
          : `Ajoute tes captures : « Télécharger », puis glisse chaque fichier dans ${where}.`)
        : "Joins tes captures à l'e-mail : « Télécharger », puis ajoute-les en pièces jointes.");
    }
    steps.push(github
      ? "Clique sur le bouton vert <b>Create</b> (« Submit new issue » sur l'ancienne page) : c'est envoyé ! GitHub te préviendra par e-mail à chaque réponse."
      : "Envoie l'e-mail : c'est parti !");
    next.innerHTML = `
      <h2 id="fb-third"><span class="fb-num" aria-hidden="true">3</span>${github ? "Dernière étape, sur GitHub" : "Dernière étape, dans ta messagerie"}</h2>
      <ol class="fb-steps">${steps.map((s) => `<li>${s}</li>`).join("")}</ol>
      ${shotsHtml}
      ${!github ? `<p class="hint">Pas de logiciel de messagerie ? « Copier le texte », puis envoie-le à <b>${F.escape(info.email)}</b> depuis ta messagerie habituelle.</p>` : ""}
      <div class="fb-actions">
        ${!longText && github ? `<a class="btn" href="${F.escape(url)}" target="_blank" rel="noopener">${icon("external")}Rouvrir GitHub</a>` : ""}
        <button class="btn btn-ghost" type="button" data-done>${icon("check")}C'est envoyé : effacer le brouillon</button>
      </div>`;
    next.hidden = false;
    next.querySelector("[data-copy-long]")?.addEventListener("click", async () => {
      toast((await copyText(longText)) ? "Message copié : colle-le dans la zone de texte." : "Copie impossible : utilise « Copier le texte » plus haut.");
    });
    next.querySelectorAll("[data-copy-shot]").forEach((b) => b.addEventListener("click", async () => {
      const shot = shots[Number(b.dataset.copyShot)];
      try {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": await asPng(shot.blob) })]);
        toast("Capture copiée : colle-la sur GitHub avec Ctrl + V.");
      } catch (err) {
        toast("Copie impossible ici : télécharge la capture, puis glisse-la sur GitHub.", { error: true });
      }
    }));
    next.querySelectorAll("[data-download-shot]").forEach((b) => b.addEventListener("click", () => download(shots[Number(b.dataset.downloadShot)], Number(b.dataset.downloadShot))));
    next.querySelector("[data-done]").addEventListener("click", () => {
      clearAll();
      toast("Merci ! Brouillon effacé.");
      page.querySelector(".head")?.scrollIntoView({ behavior: "smooth" });
    });
    requestAnimationFrame(() => { next.scrollIntoView({ behavior: "smooth", block: "start" }); next.focus({ preventScroll: true }); });
  }

  // --------------------------------------------- le dépôt s'ouvre-t-il pour tout le monde ?
  api.get("/api/retours", null, { fresh: true }).then((res) => {
    const box = page.querySelector("[data-visibility]");
    if (!box?.isConnected) return;
    if (res.visibilite === "prive") {
      box.innerHTML = `${icon("info")}<span>Pour l'instant, le dépôt de Foulée est <b>privé</b> : ses pages ne s'ouvrent que pour les personnes invitées, connectées à leur compte GitHub.${res.email ? " Sinon, envoie ton message par e-mail." : ""}</span>`;
      box.classList.add("note");
    } else if (res.visibilite === "public") {
      box.innerHTML = `${icon("check")}<span>Le dépôt est public : lire les sujets ne demande rien. Pour en écrire un, il faut un compte GitHub (gratuit, « Sign up » en haut de la page).${res.email ? " Pas de compte\u00a0? Le bouton «\u00a0Envoyer par e-mail\u00a0», plus bas, fait aussi l'affaire." : ""}</span>`;
      box.classList.add("note");
    }
  }).catch(() => { /* GitHub injoignable : le texte par défaut suffit */ });
}
