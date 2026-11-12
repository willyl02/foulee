// Réglages → Calendrier : le lien de publication du calendrier d'entraînement (Garmin Connect, Google Agenda,
// tout agenda iCal). Le lien donne le calendrier à quiconque le connaît : il se colle depuis la machine elle-même
// ou par Tailscale, part dans le coffre, et ne revient jamais ici que masqué (« connect.garmin.com/…a1b2 »).
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { hour } from "./tiles-agenda.js";

const GARMIN_CALENDAR = "https://connect.garmin.com/modern/calendar";

const fail = (text) => `<p class="computed warn">${icon("warning")}<span>${F.escape(text)}</span></p>`;

function howto(open) {
  return `<details class="howto" ${open ? "open" : ""}>
      <summary>Où trouver ce lien ?</summary>
      <ol class="steps">
        <li><b>Garmin Connect</b>, sur un ordinateur : ouvre <a href="${GARMIN_CALENDAR}" target="_blank" rel="noopener">ton calendrier${icon("external")}</a>, clique sur les <b>trois points</b> en haut à droite puis sur <b>«&nbsp;Publier le calendrier&nbsp;»</b>. Copie le lien proposé : il donne tes séances prévues (plans d'entraînement, séances programmées) et tes événements (courses).</li>
        <li><b>Google Agenda</b> : paramètres de l'agenda → «&nbsp;Intégrer l'agenda&nbsp;» → <b>«&nbsp;Adresse secrète au format iCal&nbsp;»</b>.</li>
        <li><b>Autre agenda</b> (club, coach, Outlook, Apple…) : son lien d'abonnement iCal, qui finit souvent par <code>.ics</code> ou commence par <code>webcal://</code>.</li>
      </ol>
    </details>`;
}

function privacy() {
  return `<p class="computed info">${icon("lock")}<span>Ce lien donne ton calendrier à quiconque le connaît. Foulée le range dans le coffre, comme ta clé Garmin : il ne s'affiche plus en entier, ne part pas dans la sauvegarde des réglages et n'est jamais transmis à Claude. Pour le rendre inutilisable, annule la publication dans Garmin Connect (une nouvelle publication donne un nouveau lien).</span></p>`;
}

function summary(info) {
  if (!info.lu_le) return "Pas encore lu.";
  const next = info.a_venir
    ? `${info.a_venir} séance${info.a_venir > 1 ? "s" : ""} ou course${info.a_venir > 1 ? "s" : ""} à venir${info.courses_a_venir ? `, dont ${info.courses_a_venir} course${info.courses_a_venir > 1 ? "s" : ""}` : ""}`
    : "rien de prévu pour l'instant";
  return `Lu ${F.relative(info.lu_le)} : ${next}.`;
}

/** Le panneau (relié ou non), redessiné après chaque action. onChange : la colonne (vue « Calendrier ») suit. */
export async function calendarPanel(box, boot, { toast, onChange }) {
  let info;
  try {
    info = await api.get("/api/calendrier/statut", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(`État du calendrier indisponible : ${err.message}`);
    return;
  }

  if (info.demo) {
    box.innerHTML = `<p class="computed ok">${icon("check")}<span>Mode démo : un calendrier Garmin Connect fictif est relié (séances prévues, un 10 km). ${F.escape(summary(info))}</span></p>
      ${info.vue ? `<div class="inline-actions"><a class="btn" href="#/vue/${encodeURIComponent(info.vue)}">${icon("calendar")}Voir le calendrier</a></div>` : ""}`;
    return;
  }

  const form = (replacing) => `
    ${replacing ? "" : howto(true)}
    <div class="key-row">
      <input type="password" data-cal-input autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="https://… ou webcal://…" aria-label="Lien de publication du calendrier (iCal)">
      <button class="btn btn-ghost icon-btn" type="button" data-cal-show title="Afficher le lien" aria-label="Afficher le lien" aria-pressed="false">${icon("eye")}</button>
      <button class="btn btn-primary" type="button" data-cal-save>${icon("check")}Lire et enregistrer</button>
      ${replacing ? `<button class="btn btn-ghost" type="button" data-cal-cancel>Annuler</button>` : ""}
    </div>
    <p class="hint" data-cal-status aria-live="polite"></p>
    ${privacy()}`;

  const render = (replacing = false) => {
    if (!info.lie) {
      box.innerHTML = info.local ? form(false)
        : `<p class="computed">Le lien du calendrier se colle depuis le ${boot.machine === "pc" ? "PC" : "serveur"} où tourne Foulée, ou par Tailscale : il donne accès à ton calendrier et ne doit pas circuler en clair sur le réseau de la maison.</p>${howto(false)}`;
      wire();
      return;
    }
    const refused = info.refus;
    const name = info.nom ? `« ${F.escape(info.nom)} »` : info.garmin ? "Garmin Connect" : "ton agenda";
    const state = refused
      ? `<p class="computed warn">${icon("warning")}<span><b>Le lien ne répond plus</b> depuis le ${F.escape(F.dateTime(refused.depuis))}${refused.statut ? ` (HTTP ${F.escape(refused.statut)})` : ""} : la publication a peut-être été annulée. Publie de nouveau le calendrier, puis colle le nouveau lien. En attendant, Foulée garde les séances déjà lues.</span></p>`
      : `<p class="computed ok">${icon("check")}<span>Calendrier relié : ${name} <code>${F.escape(info.masque)}</code>. ${F.escape(summary(info))}</span></p>`;
    const race = info.prochaine_course;
    box.innerHTML = `${state}
      ${race ? `<p class="computed info">${icon("flag")}<span>Prochaine course : <b>${F.escape(race.titre)}</b>, ${F.escape(F.dateLong(race.date, { year: true }).replace(/^./, (c) => c.toLowerCase()))}${race.heure ? ` à ${F.escape(hour(race.heure))}` : ""}${race.lieu ? `, ${F.escape(race.lieu)}` : ""} (${race.dans_jours === 0 ? "aujourd'hui" : `J−${race.dans_jours}`}).</span></p>` : ""}
      ${replacing ? form(true) : `<div class="inline-actions">
        ${info.vue ? `<a class="btn" href="#/vue/${encodeURIComponent(info.vue)}">${icon("calendar")}Voir le calendrier</a>` : ""}
        <button class="btn" type="button" data-cal-refresh>${icon("sync")}Relire maintenant</button>
        ${info.local ? `<button class="btn btn-ghost" type="button" data-cal-replace>${icon("edit")}Remplacer le lien</button>
          <button class="btn btn-ghost btn-danger" type="button" data-cal-forget>${icon("trash")}Retirer le calendrier</button>` : ""}
        <span class="hint" data-cal-status aria-live="polite"></span>
      </div>
      <p class="hint">Foulée relit le calendrier avec la synchro automatique (rythme réglable dans «&nbsp;Synchro et calculs&nbsp;»). Le calendrier publié par Garmin ne contient que l'avenir : Foulée garde lui-même les jours passés, pour te dire ce qui a été fait ou manqué.</p>`}`;
    wire();
  };

  const wire = () => {
    const status = box.querySelector("[data-cal-status]");
    box.querySelector("[data-cal-replace]")?.addEventListener("click", () => { render(true); box.querySelector("[data-cal-input]")?.focus(); });
    box.querySelector("[data-cal-cancel]")?.addEventListener("click", () => render(false));
    box.querySelector("[data-cal-refresh]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      status.classList.remove("error");
      status.textContent = "Lecture du calendrier…";
      try {
        const res = await api.post("/api/calendrier/actualiser");
        info = res;
        toast(`Calendrier relu : ${res.lu.a_venir} séance(s) ou course(s) à venir.`);
        render(false);
        onChange?.();
      } catch (err) {
        status.classList.add("error");
        status.textContent = err.message;
        button.disabled = false;
        onChange?.();  // la pastille passe au rouge
      }
    });
    box.querySelector("[data-cal-forget]")?.addEventListener("click", async () => {
      if (!window.confirm("Retirer le calendrier ? La vue « Calendrier » et les séances prévues disparaissent de Foulée (tes séances faites restent). Le lien est effacé du coffre.")) return;
      try {
        info = await api.del("/api/calendrier");
        toast("Calendrier retiré.");
        render(false);
        onChange?.();
      } catch (err) {
        toast(err.message, { error: true });
      }
    });
    const input = box.querySelector("[data-cal-input]");
    if (!input) return;
    const show = box.querySelector("[data-cal-show]");
    show.addEventListener("click", () => {
      const visible = input.type === "password";
      input.type = visible ? "text" : "password";
      show.setAttribute("aria-pressed", String(visible));
    });
    const save = async () => {
      if (!input.value.trim()) { status.textContent = "Colle d'abord le lien du calendrier."; input.focus(); return; }
      const button = box.querySelector("[data-cal-save]");
      button.disabled = true;
      status.classList.remove("error");
      status.textContent = "Lecture du calendrier…";
      try {
        const res = await api.put("/api/calendrier", { lien: input.value });
        input.value = "";  // vidé tout de suite : le lien ne reste pas dans la page
        info = res;
        const read = res.lu || {};
        toast(`Calendrier relié : ${read.a_venir || 0} séance(s) ou course(s) à venir. La vue « Calendrier » est dans la colonne.`);
        render(false);
        onChange?.();
      } catch (err) {
        status.classList.add("error");
        status.textContent = err.message;
        button.disabled = false;
      }
    };
    box.querySelector("[data-cal-save]").addEventListener("click", save);
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); save(); } });
  };

  render(false);
}
