// « Mes élèves » (coach) : le tableau de bord du groupe, les invitations, la gestion des comptes.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { avatar, dayLabel, fail, rget, sessionFigures, sportIcon } from "./coach-ui.js";

const DOW = ["L", "M", "M", "J", "V", "S", "D"];
const STRIP = { fait: "fait", manque: "manqué", prevu: "prévu", repos: "rien de prévu" };

function countdown(days) {
  if (days == null) return "";
  if (days < 0) return "passée";
  if (days === 0) return "aujourd'hui";
  return `J-${days}`;
}

function strip(days) {
  return `<div class="co-strip" role="img" aria-label="Sa semaine, jour par jour">${days.map((d, i) => `<span class="co-sq is-${d.etat}${d.coach ? " is-coach" : ""}${d.date === F.isoDate(new Date()) ? " today" : ""}"
      title="${F.escape(`${F.dateLong(d.date)} : ${STRIP[d.etat]}${d.titre ? ` · ${d.titre}` : ""}`)}">${DOW[i]}</span>`).join("")}</div>`;
}

function card(s) {
  const last = s.derniere_seance;
  const goal = s.objectif;
  const week = s.semaine || {};
  const waiting = !s.accord;
  const flags = [
    s.alerte ? `<span class="co-chip warn">${icon("warning")}${F.escape(s.alerte)}</span>` : "",
    waiting ? `<span class="co-chip">${icon("lock")}En attente de son accord de partage</span>` : "",
    !s.actif ? `<span class="co-chip red">désactivé</span>` : "",
  ].join("");
  return `<article class="co-student" data-student="${s.id}">
    <header>${avatar(s.nom)}<div class="co-student-name"><a href="#/coach/eleve/${s.id}"><b>${F.escape(s.nom)}</b></a>
      <small>${s.partage_recu_le ? `données reçues ${F.escape(F.relative(s.partage_recu_le))}` : waiting ? "pas encore de partage" : "rien reçu pour l'instant"}</small></div>
      ${s.non_lus ? `<a class="co-badge" href="#/coach/messages?fil=eleve-${s.id}" title="${s.non_lus} message${s.non_lus > 1 ? "s" : ""} non lu${s.non_lus > 1 ? "s" : ""}">${s.non_lus}</a>` : ""}</header>
    ${flags ? `<div class="co-flags">${flags}</div>` : ""}
    <div class="co-last">${last ? `<span class="co-ico">${sportIcon(last.sport)}</span><div><b>${F.escape(last.nom || last.sport_label || "Séance")}</b>
        <span>${F.escape([dayLabel(last.date), sessionFigures(last, { te: false })].filter(Boolean).join(" · "))}</span></div>`
      : `<span class="co-ico">${icon("activity")}</span><div><b class="muted">Aucune séance partagée</b><span>sur les 4 dernières semaines</span></div>`}</div>
    ${s.bande ? strip(s.bande) : ""}
    <dl class="co-facts">
      <div title="Séances faites cette semaine"><dt>Semaine</dt><dd><b>${week.seances || 0}</b></dd></div>
      <div title="Séances prévues (son plan et les tiennes) faites cette semaine"><dt>Prévues</dt><dd><b>${week.prevues ? `${week.faites}/${week.prevues}` : "–"}</b></dd></div>
      <div title="Charge d'entraînement des 7 derniers jours"><dt>Charge 7 j</dt><dd><b>${s.charge_7j != null ? F.int(s.charge_7j) : "–"}</b></dd></div>
      <div><dt>VMA</dt><dd><b>${s.vma_kmh ? F.dec1(s.vma_kmh) : "–"}</b></dd></div>
    </dl>
    <p class="co-goal">${icon("flag")}${goal ? `<span><b>${F.escape(goal.nom)}</b>${goal.temps_cible ? ` · ${F.escape(goal.temps_cible)}` : ""}</span>${goal.dans_jours != null ? `<span class="co-chip blue">${countdown(goal.dans_jours)}</span>` : ""}`
      : `<span class="muted">pas d'objectif partagé</span>`}</p>
    <div class="co-actions">
      <a class="btn btn-small" href="#/coach/eleve/${s.id}">${icon("user")}Fiche</a>
      <a class="btn btn-small btn-ghost" href="#/coach/messages?fil=eleve-${s.id}">${icon("chat")}Message</a>
      <a class="btn btn-small btn-ghost" href="#/coach/proposer?eleves=${s.id}">${icon("plus")}Proposer</a>
    </div>
  </article>`;
}

function kpis(students) {
  const done = students.reduce((a, s) => a + (s.semaine?.seances || 0), 0);
  const planned = students.reduce((a, s) => a + (s.semaine?.prevues || 0), 0);
  const plannedDone = students.reduce((a, s) => a + (s.semaine?.faites || 0), 0);
  const unread = students.filter((s) => s.non_lus);
  const races = students.filter((s) => s.objectif?.dans_jours >= 0).sort((a, b) => a.objectif.dans_jours - b.objectif.dans_jours);
  const watch = students.filter((s) => s.alerte);
  return `<div class="co-kpis">
    <div class="co-kpi"><small>Séances cette semaine</small><b>${done}</b><span>${planned ? `${plannedDone} sur ${planned} prévues faites` : "rien de prévu"}</span></div>
    <div class="co-kpi"><small>Messages non lus</small><b>${unread.reduce((a, s) => a + s.non_lus, 0)}</b><span>${unread.length ? F.escape(unread.map((s) => s.nom.split(" ")[0]).join(", ")) : "tout est lu"}</span></div>
    <div class="co-kpi"><small>Prochaine course</small><b>${races.length ? countdown(races[0].objectif.dans_jours) : "–"}</b><span>${races.length ? F.escape(`${races[0].nom.split(" ")[0]} · ${races[0].objectif.nom}`) : "aucun objectif daté"}</span></div>
    <div class="co-kpi${watch.length ? " warn" : ""}"><small>À surveiller</small><b>${watch.length}</b><span>${watch.length ? F.escape(watch.map((s) => `${s.nom.split(" ")[0]} : ${s.alerte}`).join(", ")) : "personne"}</span></div>
  </div>`;
}

export async function renderGroup(ctx) {
  const { page, me, host, toast } = ctx;
  page.innerHTML = `${ctx.head(`<h1>Mes élèves</h1>`, `<span>Relais <b>${F.escape(host)}</b> · ${F.escape(me.nom)}${me.admin ? " · administrateur du relais" : ""}</span>`,
    `<a class="btn" href="#/coach/messages?fil=groupe">${icon("club")}Fil du groupe</a><button class="btn btn-primary" type="button" data-invite-top>${icon("plus")}Inviter un élève</button>`)}
    ${ctx.tabs("eleves")}
    <div class="co-page wide">
      <div data-kpis></div>
      <div class="co-students" data-students><p class="computed co-wait">Chargement du groupe…</p></div>
      <section class="coach-card" data-invite-card><h2>${icon("key")}Inviter un élève</h2>
        <p>Crée un code et donne-le à ton élève, avec l'adresse du relais (<b>${F.escape(host)}</b>). Dans Foulée, il va dans Réglages → Coach et élèves → «&nbsp;J'ai un code d'invitation&nbsp;», puis choisit ce qu'il partage avec toi. Un code sert une seule fois et vaut 7 jours.</p>
        <div class="inline-actions"><button class="btn btn-primary" type="button" data-invite>${icon("plus")}Créer un code d'invitation</button></div>
        <div data-codes></div></section>
      <details class="coach-card co-manage"><summary><h2>${icon("settings")}Gérer les comptes du groupe</h2></summary><div data-accounts></div></details>
    </div>`;

  const studentsBox = page.querySelector("[data-students]");
  const codesBox = page.querySelector("[data-codes]");
  const accountsBox = page.querySelector("[data-accounts]");

  const drawStudents = (list) => {
    page.querySelector("[data-kpis]").innerHTML = list.length ? kpis(list) : "";
    studentsBox.innerHTML = list.length ? list.map(card).join("")
      : `<div class="co-empty-big">${icon("club")}<b>Personne pour l'instant</b><span>Invite ton premier élève : il te suffit de lui donner un code.</span></div>`;
    studentsBox.querySelectorAll("[data-student]").forEach((el) => el.addEventListener("click", (e) => {
      if (e.target.closest("a, button")) return;
      location.hash = `#/coach/eleve/${el.dataset.student}`;
    }));
    accountsBox.innerHTML = list.length ? `<table class="coach-table"><thead><tr><th>Élève</th><th>Identifiant</th><th>Inscrit</th><th>Dernière connexion</th><th></th></tr></thead><tbody>
      ${list.map((s) => `<tr><td><b>${F.escape(s.nom)}</b>${s.actif ? "" : ' <span class="muted">(désactivé)</span>'}</td><td><code>${F.escape(s.identifiant)}</code></td>
        <td>${F.escape(F.dateTime(s.inscrit_le))}</td><td>${F.escape(F.relative(s.derniere_connexion))}</td>
        <td><button class="btn btn-ghost btn-danger btn-small" type="button" data-remove="${s.id}" data-name="${F.escape(s.nom)}">${icon("trash")}Retirer</button></td></tr>`).join("")}
      </tbody></table><p class="hint">Retirer un élève efface son compte du relais, ce qu'il a partagé et vos messages. Il lui faudra un nouveau code pour revenir.</p>`
      : `<p class="computed">Aucun compte élève.</p>`;
    accountsBox.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", async () => {
      if (!window.confirm(`Retirer ${b.dataset.name} du groupe ? Son compte, ce qu'il a partagé et vos messages sont effacés du relais.`)) return;
      try { await api.del(`/api/coach/eleves/${b.dataset.remove}`); toast("Élève retiré du groupe."); await load(); }
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
  const createCode = async () => {
    invite.disabled = true;
    try {
      const res = await api.post("/api/coach/invitations");
      drawCodes(res.invitations, res.invitation.code);
    } catch (err) { toast(err.message); }
    invite.disabled = false;
  };
  invite.addEventListener("click", createCode);
  page.querySelector("[data-invite-top]").addEventListener("click", async () => {
    const box = page.querySelector("[data-invite-card]");
    box.scrollIntoView({ behavior: "smooth", block: "center" });
    await createCode();
  });

  async function load() {
    try {
      const group = await rget("groupe");
      drawStudents(group.eleves);
      drawCodes(group.invitations);
    } catch (err) {
      studentsBox.innerHTML = fail(err.message);
    }
  }
  await load();
  const onNews = () => { if (document.body.contains(studentsBox)) load(); else window.removeEventListener("coach:news", onNews); };
  window.addEventListener("coach:news", onNews);
}
