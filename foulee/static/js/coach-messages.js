// La messagerie : le fil du groupe, une conversation par élève (ou avec son coach), et les fils sous les séances.
import * as F from "./format.js";
import { icon } from "./icons.js";
import { avatar, fail, loading, mountThread, msgTime, rget } from "./coach-ui.js";

function convAvatar(t) {
  if (t.genre === "groupe") return avatar("", { group: true });
  if (t.genre === "seance") return `<span class="co-av seance">${icon("activity")}</span>`;
  return avatar(t.titre);
}

function preview(t) {
  if (!t.dernier) return t.genre === "groupe" ? "Les annonces et les rendez-vous du groupe" : t.genre === "seance" ? "" : "Pas encore de message";
  return `${t.dernier.moi ? "Toi : " : t.genre === "groupe" ? `${t.dernier.auteur.nom.split(" ")[0]} : ` : ""}${t.dernier.texte}`;
}

export async function renderMessages(ctx) {
  const { page, role, me, toast, params } = ctx;
  const coachSide = role === "coach";
  page.innerHTML = `${ctx.head(`<h1>Messages</h1>`, `<span>${coachSide ? "Le fil du groupe, une conversation par élève, et un fil sous chaque séance" : "Ton coach, le fil du groupe, et les fils sous tes séances"}</span>`)}
    ${ctx.tabs("messages")}
    <div class="co-chat" data-chat><div class="co-convs" data-convs>${loading()}</div><div class="co-pane" data-pane></div></div>`;
  const chat = page.querySelector("[data-chat]");
  const convs = page.querySelector("[data-convs]");
  const pane = page.querySelector("[data-pane]");
  let threads = [];
  let current = params.get("fil");
  let mounted = null;

  const drawList = () => {
    const groups = [["groupe", "Groupe"], ["eleve", coachSide ? "Élèves" : "Ton coach"], ["seance", "Sous les séances"]];
    convs.innerHTML = groups.map(([genre, label]) => {
      const items = threads.filter((t) => t.genre === genre);
      if (!items.length) return "";
      return `<h3 class="co-convs-title">${label}</h3>${items.map((t) => `<button type="button" class="co-conv${t.fil === current ? " on" : ""}" data-fil="${F.escape(t.fil)}">
        ${convAvatar(t)}<span class="co-conv-text"><b>${F.escape(t.titre)}</b><span>${F.escape(preview(t))}</span></span>
        <span class="co-conv-side">${t.dernier ? `<time>${F.escape(msgTime(t.dernier.cree_le).split(" · ")[0])}</time>` : ""}${t.non_lus ? `<span class="co-badge">${t.non_lus}</span>` : ""}</span></button>`).join("")}`;
    }).join("");
    convs.querySelectorAll("[data-fil]").forEach((b) => b.addEventListener("click", () => open(b.dataset.fil)));
  };

  const loadList = async () => {
    try {
      threads = (await rget("fils")).fils;
      drawList();
    } catch (err) { convs.innerHTML = fail(err.message); }
  };

  const open = (fil) => {
    const t = threads.find((x) => x.fil === fil);
    if (!t) return;
    current = fil;
    history.replaceState(null, "", `#/coach/messages?fil=${encodeURIComponent(fil)}`);
    chat.classList.add("has-open");
    mounted?.stop();
    const seanceKey = t.genre === "seance" ? fil.split("-").slice(2).join("-") : null;
    const link = t.genre === "seance"
      ? `<a class="btn btn-small btn-ghost" href="${coachSide ? `#/coach/eleve/${t.eleve_id}/seance/${encodeURIComponent(seanceKey)}` : `#/coach/seance/${encodeURIComponent(seanceKey)}`}">${icon("activity")}Voir la séance</a>`
      : t.genre === "eleve" && coachSide ? `<a class="btn btn-small btn-ghost" href="#/coach/eleve/${t.eleve_id}">${icon("user")}Sa fiche</a>`
        : t.genre === "groupe" && coachSide ? `<span class="co-chip">${icon("star")}épingle un message pour le garder en haut</span>` : "";
    pane.innerHTML = `<div class="co-pane-head"><button type="button" class="btn btn-ghost btn-small co-back" data-back title="Toutes les conversations">${icon("left")}</button>
        ${convAvatar(t)}<b>${F.escape(t.titre)}</b>${link}</div><div class="co-pane-body" data-thread></div>`;
    pane.querySelector("[data-back]").addEventListener("click", () => { chat.classList.remove("has-open"); });
    const style = t.genre === "eleve" ? "bubbles" : "comments";
    const first = coachSide ? t.titre.split(" ")[0] : (me.coach?.nom || "ton coach").split(" ")[0];
    mounted = mountThread(pane.querySelector("[data-thread]"), {
      fil, role, style, toast,
      placeholder: t.genre === "groupe" ? "Écrire au groupe…" : t.genre === "eleve" ? `Écrire à ${first}…` : "Répondre sous cette séance…",
      empty: t.genre === "groupe" ? "Le fil du groupe est vide. Une annonce, un rendez-vous, un bravo ?" : "Pas encore de message.",
      onRead: () => {
        if (t.non_lus) { t.non_lus = 0; drawList(); ctx.poke(); }
      },
    });
    drawList();
    if (window.matchMedia("(pointer: fine)").matches) mounted.ready.then(() => mounted.focus());
  };

  await loadList();
  if (!threads.some((t) => t.fil === current)) {
    const unread = threads.find((t) => t.non_lus);
    current = unread?.fil || (coachSide ? "groupe" : `eleve-${me.id}`);
  }
  if (threads.length) open(current);
  if (!params.get("fil") && window.matchMedia("(max-width: 760px)").matches) chat.classList.remove("has-open");

  const onNews = () => { if (document.body.contains(convs)) loadList(); else { window.removeEventListener("coach:news", onNews); window.removeEventListener("coach:sent", onNews); } };
  window.addEventListener("coach:news", onNews);
  window.addEventListener("coach:sent", onNews);
}
