// Page « Mes élèves » (coach) ou « Mon coach » (élève), quand le profil est relié au relais du club.
// Étape 1 du projet : les comptes et les invitations. Les séances partagées et la messagerie viendront ensuite.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const fail = (text) => `<p class="computed warn">${icon("warning")}<span>${F.escape(text)}</span></p>`;
const seen = (value) => (value ? F.relative(value) : "jamais");

export async function renderCoachPage(page, boot, { toast, onUnlinked }) {
  page.innerHTML = `<header class="head"><div><h1>…</h1></div></header><div class="coach-page"><p class="computed">Chargement…</p></div>`;
  let info;
  try {
    info = await api.post("/api/coach/actualiser");
  } catch (err) {
    try { info = await api.get("/api/coach", null, { fresh: true }); } catch (e) { info = null; }
    if (!info?.relie) { page.querySelector(".coach-page").innerHTML = fail(err.message); return; }
  }
  if (!info.relie) {
    page.innerHTML = `<header class="head"><div><h1>Coach et élèves</h1></div></header>
      <div class="coach-page">${fail("Ce profil n'est plus relié au relais (session fermée : mot de passe changé, compte retiré…).")}
      <div class="inline-actions"><a class="btn btn-primary" href="#/reglages?section=coach">${icon("settings")}Me reconnecter</a></div></div>`;
    onUnlinked?.();
    return;
  }
  const a = info.compte;
  const host = info.adresse.replace(/^https?:\/\//, "");
  if (a.role === "eleve") {
    page.innerHTML = `<header class="head"><div><h1>Mon coach</h1>
        <div class="head-sub"><span>Relais <b>${F.escape(host)}</b> · ton identifiant : <code>${F.escape(a.identifiant)}</code></span></div></div></header>
      <div class="coach-page">
        <section class="coach-card"><h2>${icon("user")}${F.escape(a.coach?.nom || "Ton coach")}</h2>
          <p>Tu fais partie de son groupe depuis ${F.escape(F.dateTime(info.relie_le))}.</p></section>
        <section class="coach-card"><h2>${icon("lock")}Ce que tu partages</h2>
          <p><b>Rien pour l'instant.</b> Le partage de tes séances (les 4 dernières semaines, en résumé), de ton objectif et de ta VMA arrive dans une prochaine bêta. Il faudra ton accord, case par case : tracés GPS, sommeil, VFC et poids resteront en option.</p></section>
        <section class="coach-card"><h2>${icon("chat")}À venir</h2>
          <p>Les messages avec ton coach (une conversation et un fil sous chaque séance), le fil du groupe, et les séances qu'il te propose, dans ton calendrier.</p></section>
        <p class="hint">Changer de mot de passe, te déconnecter ou quitter le groupe : <a href="#/reglages?section=coach">Réglages → Coach et élèves</a>.</p>
      </div>`;
    return;
  }

  page.innerHTML = `<header class="head"><div><h1>Mes élèves</h1>
      <div class="head-sub"><span>Relais <b>${F.escape(host)}</b> · ${F.escape(a.nom)}${a.admin ? " · administrateur du relais" : ""}</span></div></div></header>
    <div class="coach-page">
      <section class="coach-card"><h2>${icon("club")}Le groupe</h2><div data-students><p class="computed">Chargement…</p></div></section>
      <section class="coach-card"><h2>${icon("key")}Inviter un élève</h2>
        <p>Crée un code et donne-le à ton élève, avec l'adresse du relais (<b>${F.escape(host)}</b>). Dans Foulée, il va dans Réglages → Coach et élèves → «&nbsp;J'ai un code d'invitation&nbsp;». Un code sert une seule fois et vaut 7 jours.</p>
        <div class="inline-actions"><button class="btn btn-primary" type="button" data-invite>${icon("plus")}Créer un code d'invitation</button></div>
        <div data-codes></div></section>
      <section class="coach-card"><h2>${icon("chat")}À venir</h2>
        <p>Les séances de tes élèves (4 dernières semaines, en résumé, avec leur accord), leurs objectifs, la messagerie et le fil du groupe, puis les séances que tu leur proposes.</p></section>
    </div>`;

  const studentsBox = page.querySelector("[data-students]");
  const codesBox = page.querySelector("[data-codes]");

  const drawStudents = (list) => {
    if (!list.length) { studentsBox.innerHTML = `<p class="computed">Personne pour l'instant : invite ton premier élève ci-dessous.</p>`; return; }
    studentsBox.innerHTML = `<table class="coach-table"><thead><tr><th>Élève</th><th>Identifiant</th><th>Inscrit</th><th>Dernière connexion</th><th></th></tr></thead><tbody>
      ${list.map((s) => `<tr><td><b>${F.escape(s.nom)}</b>${s.actif ? "" : " <span class=\"muted\">(désactivé)</span>"}</td><td><code>${F.escape(s.identifiant)}</code></td>
        <td>${F.escape(F.dateTime(s.cree_le))}</td><td>${F.escape(seen(s.derniere_connexion))}</td>
        <td><button class="btn btn-ghost btn-danger btn-small" type="button" data-remove="${s.id}" data-name="${F.escape(s.nom)}">${icon("trash")}Retirer</button></td></tr>`).join("")}
      </tbody></table>`;
    studentsBox.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", async () => {
      if (!window.confirm(`Retirer ${b.dataset.name} du groupe ? Son compte est effacé du relais ; il lui faudra un nouveau code pour revenir.`)) return;
      try { drawStudents((await api.del(`/api/coach/eleves/${b.dataset.remove}`)).eleves); toast("Élève retiré du groupe."); }
      catch (err) { toast(err.message); }
    }));
  };

  const drawCodes = (list, fresh = null) => {
    codesBox.innerHTML = list.length ? `<ul class="coach-codes">${list.map((c) => `<li class="${c.code === fresh ? "fresh" : ""}">
        <code class="coach-code">${F.escape(c.code)}</code><span class="muted">valable jusqu'au ${F.escape(F.dateTime(c.expire_le))}</span>
        <button class="btn btn-ghost btn-small" type="button" data-copy="${F.escape(c.code)}">${icon("copy")}Copier</button>
        <button class="btn btn-ghost btn-danger btn-small" type="button" data-cancel="${F.escape(c.code)}">Annuler</button></li>`).join("")}</ul>` : "";
    codesBox.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
      const text = `Relais : ${host}\nCode d'invitation : ${b.dataset.copy}`;
      try { await navigator.clipboard.writeText(text); toast("Adresse du relais et code copiés."); } catch (e) { toast(b.dataset.copy); }
    }));
    codesBox.querySelectorAll("[data-cancel]").forEach((b) => b.addEventListener("click", async () => {
      try { drawCodes((await api.del(`/api/coach/invitations/${encodeURIComponent(b.dataset.cancel)}`)).invitations); }
      catch (err) { toast(err.message); }
    }));
  };

  const invite = page.querySelector("[data-invite]");
  invite.addEventListener("click", async () => {
    invite.disabled = true;
    try {
      const res = await api.post("/api/coach/invitations");
      drawCodes(res.invitations, res.invitation.code);
    } catch (err) { toast(err.message); }
    invite.disabled = false;
  });

  try {
    const group = await api.get("/api/coach/groupe", null, { fresh: true });
    drawStudents(group.eleves);
    drawCodes(group.invitations);
  } catch (err) {
    studentsBox.innerHTML = fail(err.message);
  }
}
