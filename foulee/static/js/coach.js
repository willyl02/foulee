// Coach et élèves, quand le profil est relié au relais du club. Une page par adresse :
//   #/coach                       Mes élèves (coach) ou Mon coach (élève)
//   #/coach/eleve/<id>            la fiche d'un élève (coach)
//   #/coach/eleve/<id>/seance/<c> une séance d'un élève et son fil (coach)
//   #/coach/seance/<c>            une de mes séances partagées et son fil (élève)
//   #/coach/messages?fil=…        la messagerie (les deux)
//   #/coach/proposer              proposer une séance (coach)
//   #/coach/partage               ce que je partage avec mon coach (élève)
// Le relevé des nouveautés (toutes les minutes) met à jour le badge de la colonne et prévient d'un message.
import * as api from "./api.js";
import { icon } from "./icons.js";
import { fail, tabs } from "./coach-ui.js";
import { renderGroup } from "./coach-groupe.js";
import { renderStudent, renderSession } from "./coach-fiche.js";
import { renderMessages } from "./coach-messages.js";
import { renderEditor } from "./coach-proposer.js";
import { renderMyCoach, renderAccord } from "./coach-eleve.js";

// ------------------------------------------------------------ relevé
const watch = { timer: null, unread: 0, repere: null, role: null, toast: null, onBadge: null, busy: false };

export function coachUnread() { return watch.unread; }

function setUnread(n) {
  watch.unread = n;
  watch.onBadge?.(n);
  document.querySelectorAll("[data-coach-unread]").forEach((el) => { el.textContent = n; el.hidden = !n; });
}

async function tick() {
  if (document.hidden || watch.busy || !watch.role) return;
  watch.busy = true;
  try {
    const news = await api.get("/api/coach/r/nouveautes", null, { fresh: true });
    const before = watch.repere;
    if (before !== null && news.repere !== before) {
      const [msgBefore, otherBefore] = before.split("|");
      const [msgNow, otherNow] = news.repere.split("|");
      window.dispatchEvent(new CustomEvent("coach:news", { detail: news }));
      const onMessages = location.hash.startsWith("#/coach/messages");
      if (msgNow !== msgBefore && news.non_lus > watch.unread && !onMessages) {
        watch.toast?.(news.non_lus === 1 ? "Un nouveau message sur le relais du club." : `${news.non_lus} messages non lus sur le relais du club.`);
      }
      if (watch.role === "eleve" && otherNow !== otherBefore) {
        try { await api.post("/api/coach/echange"); } catch (e) { /* le calendrier suivra à la prochaine synchro */ }
        watch.toast?.("Ton coach a mis à jour tes séances : elles sont dans ton calendrier.");
      }
    }
    watch.repere = news.repere;
    setUnread(news.non_lus);
  } catch (err) {
    if (/session|relié|reconnect/i.test(err.message)) stopWatch();
  } finally {
    watch.busy = false;
  }
}

function stopWatch() { clearInterval(watch.timer); watch.timer = null; watch.role = null; }

/** À lancer au démarrage et après chaque changement de profil ou de lien. */
export function watchCoach(boot, { toast, onBadge } = {}) {
  stopWatch();
  watch.toast = toast || watch.toast;
  watch.onBadge = onBadge || watch.onBadge;
  watch.repere = null;
  if (!boot?.coach) { setUnread(0); return; }
  watch.role = boot.coach.role;
  tick();
  watch.timer = setInterval(tick, 60000);
}

/** Relevé immédiat (après la lecture d'un fil : le badge baisse tout de suite). */
export function pokeCoach() { setTimeout(tick, 300); }

document.addEventListener("visibilitychange", () => { if (!document.hidden && watch.role) tick(); });

// ------------------------------------------------------------ pages
function head(title, sub = "", actions = "") {
  return `<header class="head co-head"><div>${title}${sub ? `<div class="head-sub">${sub}</div>` : ""}</div>${actions ? `<div class="head-tools">${actions}</div>` : ""}</header>`;
}

export async function renderCoachPage(page, boot, { toast, onUnlinked, path = "/coach", params = new URLSearchParams() }) {
  const parts = path.split("/").filter(Boolean).slice(1).map(decodeURIComponent);  // sans « coach »
  page.innerHTML = `<header class="head"><div><h1>…</h1></div></header><div class="co-page"><p class="computed co-wait">Chargement…</p></div>`;
  let info;
  try {
    info = parts.length ? await api.get("/api/coach", null, { fresh: true }) : await api.post("/api/coach/actualiser");
  } catch (err) {
    try { info = await api.get("/api/coach", null, { fresh: true }); } catch (e) { info = null; }
    if (!info?.relie) { page.querySelector(".co-page").innerHTML = fail(err.message); return; }
  }
  if (!info.relie) {
    page.innerHTML = `<header class="head"><div><h1>Coach et élèves</h1></div></header>
      <div class="co-page">${fail("Ce profil n'est plus relié au relais (session fermée : mot de passe changé, compte retiré…).")}
      <div class="inline-actions"><a class="btn btn-primary" href="#/reglages?section=coach">${icon("settings")}Me reconnecter</a></div></div>`;
    onUnlinked?.();
    return;
  }
  const role = info.compte.role;
  const ctx = {
    page, boot, info, role, me: info.compte, host: info.adresse.replace(/^https?:\/\//, ""), params, toast,
    head, poke: pokeCoach,
    tabs: (active) => tabs(role, active, { unread: watch.unread }),
  };
  try {
    if (role === "coach") {
      if (parts[0] === "eleve" && /^\d+$/.test(parts[1] || "")) {
        if (parts[2] === "seance" && parts[3]) await renderSession(ctx, Number(parts[1]), parts.slice(3).join("/"));
        else await renderStudent(ctx, Number(parts[1]));
      } else if (parts[0] === "messages") await renderMessages(ctx);
      else if (parts[0] === "proposer") await renderEditor(ctx);
      else await renderGroup(ctx);
    } else if (parts[0] === "seance" && parts[1]) await renderSession(ctx, null, parts.slice(1).join("/"));
    else if (parts[0] === "messages") await renderMessages(ctx);
    else if (parts[0] === "partage") await renderAccord(ctx);
    else await renderMyCoach(ctx);
  } catch (err) {
    page.innerHTML = `${head(`<h1>${role === "coach" ? "Mes élèves" : "Mon coach"}</h1>`)}${ctx.tabs("")}<div class="co-page">${fail(err.message)}</div>`;
  }
}
