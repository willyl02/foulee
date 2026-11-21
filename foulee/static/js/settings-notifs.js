// Réglages → Notifications (profil relié au relais du club) : sur le téléphone par ntfy (appli gratuite, sans
// compte), et par e-mail (adresse confirmée par un code, quand le relais a un service d'envoi). Les réglages vivent
// sur le relais : c'est lui qui voit passer séances et messages.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const R = (path) => `/api/coach/r/${path}`;
const STORES = [
  ["Android (Google Play)", "https://play.google.com/store/apps/details?id=io.heckel.ntfy"],
  ["Android (F-Droid)", "https://f-droid.org/packages/io.heckel.ntfy/"],
  ["iPhone (App Store)", "https://apps.apple.com/app/ntfy/id1625396347"],
];

export async function notificationsPanel(box, { toast }) {
  box.innerHTML = `<p class="hint">Lecture des réglages sur le relais…</p>`;
  let data;
  try { data = await api.get(R("notifications"), null, { fresh: true }); } catch (err) {
    box.innerHTML = `<p class="hint">${F.escape(err.message)}</p>`;
    return;
  }
  let changing = false; // « Changer d'adresse » : le formulaire, même avec une adresse confirmée
  const lastLine = (last) => last ? `<span class="nf-last ${last.statut === "ok" ? "ok" : "bad"}">${last.statut === "ok" ? icon("check") : icon("warning")}Dernier envoi ${F.escape(F.relative(last.cree_le))} : ${last.statut === "ok" ? "parti" : F.escape(last.detail || "échec")}</span>` : "";
  const emailCard = () => {
    const mail = data.reglages.email || {};
    const head = (extra) => `<div class="nf-head">${icon("chat")}<div><b>Par e-mail</b><span>Les mêmes événements et les mêmes heures calmes, dans ta boîte mail.</span></div>${extra}</div>`;
    if (!data.email_pret) {
      return `<div class="nf-card nf-soon">${head(`<span class="nf-tag">Bientôt</span>`)}
        <p class="hint nf-note">Le relais du club n'envoie pas encore d'e-mails : son administrateur doit d'abord lui brancher un service d'envoi.</p></div>`;
    }
    const verified = mail.adresse && mail.verifiee_le;
    const last = data.dernier && data.dernier.canal === "email" ? data.dernier : null;
    if (verified && !changing) {
      return `<div class="nf-card">${head(`<label class="switch"><input type="checkbox" data-mail-on ${mail.actif ? "checked" : ""}><span>${mail.actif ? "Activés" : "Désactivés"}</span></label>`)}
        <div class="nf-mail">${icon("check")}<span><b>${F.escape(mail.adresse)}</b>, confirmée ${F.escape(F.relative(mail.verifiee_le))}</span></div>
        <div class="inline-actions nf-mail-actions"><button class="btn btn-small" type="button" data-mail-test>${icon("chat")}Envoyer un e-mail d'essai</button>
          <button class="btn btn-ghost btn-small" type="button" data-mail-change>${icon("edit")}Changer d'adresse</button>
          <button class="btn btn-ghost btn-small" type="button" data-mail-remove>${icon("trash")}Retirer</button>${lastLine(last)}</div></div>`;
    }
    const waiting = data.email_attente;
    return `<div class="nf-card">${head(verified ? `<button class="btn btn-ghost btn-small" type="button" data-mail-cancel>Annuler</button>` : "")}
      <ol class="nf-steps">
        <li><b>Ton adresse</b>
          <div class="nf-row"><input type="text" inputmode="email" autocomplete="email" spellcheck="false" data-mail-address placeholder="prenom.nom@exemple.fr" value="${F.escape(waiting || "")}">
            <button class="btn btn-small" type="button" data-mail-send>${icon("chat")}${waiting ? "Renvoyer un code" : "Recevoir un code"}</button></div></li>
        <li class="${waiting ? "" : "nf-off"}"><b>Le code reçu</b>${waiting ? ` à ${F.escape(waiting)} (valable 30 minutes ; regarde aussi dans les indésirables)` : " : six chiffres, par e-mail"}
          <div class="nf-row"><input type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" data-mail-code placeholder="123456" ${waiting ? "" : "disabled"}>
            <button class="btn btn-small" type="button" data-mail-verify ${waiting ? "" : "disabled"}>${icon("check")}Confirmer</button></div></li>
      </ol>${lastLine(last)}</div>`;
  };
  const draw = () => {
    const s = data.reglages;
    const last = data.dernier && data.dernier.canal !== "email" ? data.dernier : null;
    box.innerHTML = `
      <div class="nf-card">
        <div class="nf-head">${icon("bell")}<div><b>Sur ton téléphone, avec ntfy</b><span>Une appli gratuite, sans compte ni publicité.</span></div>
          <label class="switch"><input type="checkbox" data-on ${s.ntfy.actif ? "checked" : ""}><span>${s.ntfy.actif ? "Activées" : "Désactivées"}</span></label></div>
        <ol class="nf-steps">
          <li><b>Installe ntfy</b> : ${STORES.map(([label, url]) => `<a href="${url}" target="_blank" rel="noopener">${label}</a>`).join(" · ")}.</li>
          <li><b>Abonne-toi à ton sujet</b> : scanne ce code avec ton téléphone, ou, dans ntfy, touche « + » et colle le sujet ci-dessous${s.ntfy.serveur !== "https://ntfy.sh" ? ` (en choisissant le serveur ${F.escape(s.ntfy.serveur)})` : ""}.
            <div class="nf-sub"><img src="/api/notifications/qr.svg?adresse=${encodeURIComponent(data.abonnement)}" alt="QR code de l'abonnement ntfy" width="132" height="132">
              <div><span class="hint">Ton sujet (garde-le pour toi : qui le connaît lit tes notifications)</span>
                <code data-topic>${F.escape(s.ntfy.sujet)}</code>
                <div class="inline-actions"><button class="btn btn-small" type="button" data-copy>${icon("copy")}Copier</button>
                  <button class="btn btn-ghost btn-small" type="button" data-new-topic>${icon("reset")}Changer de sujet</button></div></div></div></li>
          <li><b>Essaie</b> : <button class="btn btn-small" type="button" data-test>${icon("bell")}Envoyer une notification d'essai</button>
            ${lastLine(last)}</li>
        </ol>
      </div>
      <div class="nf-grid">
        <fieldset class="nf-box"><legend>Me prévenir quand</legend>
          ${data.evenements.map((e) => `<label class="check"><input type="checkbox" data-event="${e.cle}" ${s.evenements[e.cle] ? "checked" : ""}> ${F.escape(e.libelle)}</label>`).join("")}
          <label class="check"><input type="checkbox" data-detail ${s.detail ? "checked" : ""}> Afficher le détail (titre de la séance, début du message)</label>
        </fieldset>
        <fieldset class="nf-box"><legend>Heures calmes</legend>
          <label class="check"><input type="checkbox" data-quiet ${s.calme.actif ? "checked" : ""}> Ne pas me déranger</label>
          <div class="nf-hours"><label class="field"><span>De</span><input type="time" data-from value="${F.escape(s.calme.debut)}"></label>
            <label class="field"><span>À</span><input type="time" data-to value="${F.escape(s.calme.fin)}"></label></div>
          <p class="hint">Pendant ces heures, la notification et l'e-mail attendent leur fin (pratique en horaires postés).</p>
        </fieldset>
      </div>
      <details class="nf-more"><summary>Serveur ntfy</summary>
        <label class="field"><span>Adresse du serveur</span><input type="text" inputmode="url" data-server value="${F.escape(s.ntfy.serveur)}" spellcheck="false"></label>
        <p class="hint">ntfy.sh par défaut. Un ntfy installé sur la machine du relais se règle ici (sur iPhone, il doit relayer par ntfy.sh pour que les notifications arrivent tout de suite).</p>
      </details>
      ${emailCard()}`;
    wire();
  };
  const save = async (body, message) => {
    try {
      data = await api.put(R("notifications"), body);
      draw();
      if (message) toast(message);
    } catch (err) { toast(err.message, { error: true }); draw(); }
  };
  const wire = () => {
    const $ = (sel) => box.querySelector(sel);
    $("[data-on]").addEventListener("change", (e) => save({ ntfy: { actif: e.target.checked } },
      e.target.checked ? "Notifications activées : abonne-toi au sujet dans ntfy, puis fais un essai." : "Notifications désactivées."));
    box.querySelectorAll("[data-event]").forEach((el) => el.addEventListener("change", () => save({ evenements: { [el.dataset.event]: el.checked } })));
    $("[data-detail]").addEventListener("change", (e) => save({ detail: e.target.checked }));
    const quiet = () => save({ calme: { actif: $("[data-quiet]").checked, debut: $("[data-from]").value, fin: $("[data-to]").value } });
    $("[data-quiet]").addEventListener("change", quiet);
    $("[data-from]").addEventListener("change", quiet);
    $("[data-to]").addEventListener("change", quiet);
    $("[data-server]").addEventListener("change", (e) => save({ ntfy: { serveur: e.target.value } }, "Serveur ntfy enregistré : abonne-toi de nouveau dans l'appli."));
    $("[data-copy]").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(data.reglages.ntfy.sujet); toast("Sujet copié."); } catch (err) { toast("Copie impossible : sélectionne le sujet à la main."); }
    });
    $("[data-new-topic]").addEventListener("click", () => {
      if (!window.confirm("Changer de sujet ? L'ancien ne recevra plus rien : il faudra t'abonner au nouveau dans ntfy.")) return;
      save({ nouveau_sujet: true }, "Nouveau sujet : abonne-toi à lui dans ntfy.");
    });
    wireEmail($);
    $("[data-test]").addEventListener("click", async (e) => {
      e.currentTarget.disabled = true;
      try {
        await api.post(R("notifications/essai"), {});
        toast("Essai envoyé : il arrive dans quelques secondes sur ton téléphone.");
        setTimeout(async () => { try { data = await api.get(R("notifications"), null, { fresh: true }); draw(); } catch (err) { /* plus tard */ } }, 3000);
      } catch (err) { toast(err.message, { error: true }); }
      e.currentTarget.disabled = false;
    });
  };
  const refresh = () => setTimeout(async () => { try { data = await api.get(R("notifications"), null, { fresh: true }); draw(); } catch (err) { /* plus tard */ } }, 4000);
  const busy = async (button, job) => {
    if (button) button.disabled = true;
    try { await job(); } catch (err) { toast(err.message, { error: true }); }
    if (button && button.isConnected) button.disabled = false;
  };
  const wireEmail = ($) => {
    const on = $("[data-mail-on]");
    if (on) on.addEventListener("change", (e) => save({ email: { actif: e.target.checked } }, e.target.checked ? "E-mails activés." : "E-mails désactivés."));
    const sendCode = (e) => busy(e.currentTarget, async () => {
      const adresse = ($("[data-mail-address]").value || "").trim();
      if (!adresse) { toast("Ton adresse e-mail d'abord.", { error: true }); return; }
      data = await api.post(R("notifications/email/code"), { adresse });
      draw();
      toast(`Code envoyé à ${adresse} : il arrive dans une minute ou deux.`);
      const field = box.querySelector("[data-mail-code]");
      if (field) field.focus();
    });
    const send = $("[data-mail-send]");
    if (send) send.addEventListener("click", sendCode);
    const verify = () => busy($("[data-mail-verify]"), async () => {
      const code = ($("[data-mail-code]").value || "").trim();
      if (!code) return;
      const answer = await api.post(R("notifications/email/verifier"), { code });
      if (answer.erreur) {
        data = answer;
        toast(answer.erreur, { error: true });
        draw();
        return;
      }
      data = answer;
      changing = false;
      draw();
      toast("Adresse confirmée : les e-mails sont activés.");
    });
    const button = $("[data-mail-verify]");
    if (button) button.addEventListener("click", verify);
    const code = $("[data-mail-code]");
    if (code) code.addEventListener("keydown", (e) => { if (e.key === "Enter") verify(); });
    const address = $("[data-mail-address]");
    if (address) address.addEventListener("keydown", (e) => { if (e.key === "Enter") $("[data-mail-send]").click(); });
    const test = $("[data-mail-test]");
    if (test) test.addEventListener("click", (e) => busy(e.currentTarget, async () => {
      await api.post(R("notifications/essai"), { canal: "email" });
      toast("E-mail d'essai envoyé : regarde ta boîte dans une minute.");
      refresh();
    }));
    const change = $("[data-mail-change]");
    if (change) change.addEventListener("click", () => { changing = true; draw(); });
    const cancel = $("[data-mail-cancel]");
    if (cancel) cancel.addEventListener("click", () => { changing = false; draw(); });
    const remove = $("[data-mail-remove]");
    if (remove) remove.addEventListener("click", () => {
      if (!window.confirm("Retirer ton adresse ? Le relais ne t'enverra plus d'e-mails.")) return;
      save({ email: { retirer: true } }, "Adresse retirée.");
    });
  };
  draw();
}
