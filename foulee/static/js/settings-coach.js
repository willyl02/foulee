// Réglages → Coach et élèves : relier ce profil au relais du club, comme coach (il invite ses élèves) ou comme
// élève (il rejoint son coach avec un code d'invitation). Le mot de passe et le jeton de session ne passent que
// par la machine elle-même (ou Tailscale) ; le jeton va dans le coffre, comme la clé Garmin.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const fail = (text) => `<p class="computed warn">${icon("warning")}<span>${F.escape(text)}</span></p>`;

export function coachPageLabel(info) {
  return info?.role === "coach" ? "Mes élèves" : "Mon coach";
}

/** Le panneau, redessiné après chaque action. onChange : la colonne (« Mes élèves » / « Mon coach ») suit. */
export async function coachPanel(box, boot, { toast, onChange }) {
  let info;
  try {
    info = await api.get("/api/coach", null, { fresh: true });
  } catch (err) {
    box.innerHTML = fail(`État du lien avec le relais indisponible : ${err.message}`);
    return;
  }
  const where = boot.machine === "pc" ? "le PC" : "le serveur";

  const linked = () => {
    const a = info.compte;
    const role = a.role === "coach" ? `coach${a.admin ? " et administrateur du relais" : ""}` : `élève de <b>${F.escape(a.coach?.nom || "?")}</b>`;
    return `<p class="computed ok">${icon("check")}<span>Relié au relais <b>${F.escape(info.adresse.replace(/^https?:\/\//, ""))}</b> en tant que ${role} : <b>${F.escape(a.nom)}</b> (identifiant <code>${F.escape(a.identifiant)}</code>).</span></p>
      <div class="inline-actions">
        <a class="btn" href="#/coach">${icon(a.role === "coach" ? "club" : "user")}${coachPageLabel(a)}</a>
        ${a.role === "eleve" ? `<a class="btn btn-ghost" href="#/coach/partage">${icon("edit")}Ce que je partage</a><button class="btn btn-ghost" type="button" data-push>${icon("sync")}Envoyer maintenant</button>` : ""}
        ${info.local ? `<button class="btn btn-ghost" type="button" data-pw>${icon("lock")}Changer le mot de passe</button>` : ""}
        <button class="btn btn-ghost" type="button" data-logout>${icon("power")}Se déconnecter</button>
        ${a.role === "eleve" && info.local ? `<button class="btn btn-ghost btn-danger" type="button" data-leave>${icon("trash")}Quitter le groupe</button>` : ""}
      </div>
      <div data-extra></div>
      <p class="hint" data-status aria-live="polite"></p>`;
  };

  const choose = (mode) => `
    <div class="segmented" role="group" aria-label="Comment te relier">
      <button type="button" data-mode="eleve" aria-pressed="${mode === "eleve"}">J'ai un code d'invitation</button>
      <button type="button" data-mode="compte" aria-pressed="${mode === "compte"}">J'ai déjà un compte</button>
    </div>
    <form class="coach-form" data-form novalidate>
      <div class="form-grid">
        <label class="field"><span>Adresse du relais</span><input type="text" name="adresse" autocomplete="off" spellcheck="false" autocapitalize="off" placeholder="relais.mon-club.com" value="${F.escape((info.adresse || "").replace(/^https:\/\//, ""))}"></label>
        ${mode === "eleve" ? `<label class="field"><span>Code d'invitation</span><input type="text" name="code" autocomplete="off" spellcheck="false" autocapitalize="characters" placeholder="ABCD-EFGH"></label>` : ""}
        <label class="field"><span>Identifiant</span><input type="text" name="identifiant" autocomplete="username" spellcheck="false" autocapitalize="off" placeholder="${mode === "eleve" ? "à choisir, ex. marie.dupont" : ""}"></label>
        ${mode === "eleve" ? `<label class="field"><span>Nom affiché au coach</span><input type="text" name="nom" autocomplete="off" placeholder="ex. Marie D." value="${F.escape(boot.profil?.prenom_affiche || "")}"></label>` : ""}
        <label class="field"><span>Mot de passe${mode === "eleve" ? " (10 caractères au moins)" : ""}</span><input type="password" name="mot_de_passe" autocomplete="${mode === "eleve" ? "new-password" : "current-password"}"></label>
        ${mode === "eleve" ? `<label class="field"><span>Encore une fois</span><input type="password" name="encore" autocomplete="new-password"></label>` : ""}
      </div>
      <div class="inline-actions"><button class="btn btn-primary" type="submit">${icon("check")}${mode === "eleve" ? "Rejoindre mon coach" : "Me connecter"}</button></div>
      <p class="hint" data-status aria-live="polite"></p>
    </form>
    <p class="computed info">${icon("lock")}<span>${mode === "eleve"
      ? "Ton coach te donne l'adresse du relais et un code d'invitation (valable 7 jours, une seule fois). Tu choisis ton identifiant et ton mot de passe : ils serviront si tu réinstalles Foulée. Ensuite, tu choisis ce que tu partages, case par case : rien ne part avant ton accord."
      : "Les comptes coach sont créés par l'administrateur du relais. Ton mot de passe ne reste pas sur ce PC : Foulée garde seulement un jeton de connexion, dans le coffre, comme ta clé Garmin."}</span></p>`;

  const render = (mode = "eleve") => {
    if (info.relie) {
      box.innerHTML = linked();
      wireLinked();
    } else if (!info.local) {
      box.innerHTML = `<p class="computed">Pas encore relié. La connexion au relais se fait depuis ${where} où tourne Foulée, ou par Tailscale : un mot de passe ne doit pas circuler en clair sur le réseau de la maison.</p>`;
    } else {
      box.innerHTML = choose(mode);
      wireForm(mode);
    }
  };

  const wireForm = (mode) => {
    box.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => render(b.dataset.mode)));
    const form = box.querySelector("[data-form]");
    const status = form.querySelector("[data-status]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = (name) => form.elements[name]?.value?.trim() || "";
      if (!v("adresse")) { status.textContent = "Indique l'adresse du relais."; return; }
      if (mode === "eleve" && form.elements.mot_de_passe.value !== form.elements.encore.value) {
        status.textContent = "Les deux mots de passe ne sont pas identiques."; return;
      }
      const button = form.querySelector('[type="submit"]');
      button.disabled = true;
      status.textContent = "Connexion au relais…";
      try {
        const body = { adresse: v("adresse"), identifiant: v("identifiant"), mot_de_passe: form.elements.mot_de_passe.value };
        info = mode === "eleve"
          ? await api.post("/api/coach/inscription", { ...body, code: v("code"), nom: v("nom") })
          : await api.post("/api/coach/connexion", body);
        toast(info.compte.role === "coach" ? "Relié au relais en tant que coach." : `Bienvenue dans le groupe de ${info.compte.coach?.nom || "ton coach"} !`);
        render();
        await onChange?.();
        if (info.compte.role === "eleve" && mode === "eleve") location.hash = "#/coach/partage";
      } catch (err) {
        status.textContent = err.message;
        button.disabled = false;
      }
    });
  };

  const wireLinked = () => {
    const status = box.querySelector("[data-status]");
    const extra = box.querySelector("[data-extra]");
    box.querySelector("[data-push]")?.addEventListener("click", async (e) => {
      const button = e.currentTarget;
      button.disabled = true;
      status.textContent = "Envoi au relais…";
      try {
        const res = await api.post("/api/coach/echange");
        status.textContent = res.envoi ? `Envoyé : ${res.envoi.seances} séance${res.envoi.seances > 1 ? "s" : ""} partagée${res.envoi.seances > 1 ? "s" : ""}, ${res.propositions} séance${res.propositions > 1 ? "s" : ""} proposée${res.propositions > 1 ? "s" : ""} par ton coach.` : "Choisis d'abord ce que tu partages (« Ce que je partage »).";
      } catch (err) { status.textContent = err.message; }
      button.disabled = false;
    });
    box.querySelector("[data-logout]").addEventListener("click", async () => {
      if (!window.confirm("Se déconnecter du relais ? Tu pourras te reconnecter avec ton identifiant et ton mot de passe.")) return;
      try {
        info = await api.del("/api/coach");
        render("compte");
        onChange?.();
      } catch (err) { status.textContent = err.message; }
    });
    box.querySelector("[data-leave]")?.addEventListener("click", () => {
      extra.innerHTML = `<form class="coach-form" data-leave-form novalidate>
          <p class="computed warn">${icon("warning")}<span>Quitter le groupe efface ton compte du relais, et tout ce que tu as partagé. Ton coach ne voit plus rien. Tes données restent dans ton Foulée.</span></p>
          <label class="field narrow"><span>Ton mot de passe, pour confirmer</span><input type="password" name="mot_de_passe" autocomplete="current-password"></label>
          <div class="inline-actions"><button class="btn btn-danger" type="submit">${icon("trash")}Quitter le groupe</button><button class="btn btn-ghost" type="button" data-cancel>Annuler</button></div>
        </form>`;
      const form = extra.querySelector("form");
      form.querySelector("[data-cancel]").addEventListener("click", () => { extra.innerHTML = ""; });
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          info = await api.post("/api/coach/quitter", { mot_de_passe: form.elements.mot_de_passe.value });
          toast("Tu as quitté le groupe : ton compte est effacé du relais.");
          render();
          onChange?.();
        } catch (err) { status.textContent = err.message; }
      });
    });
    box.querySelector("[data-pw]")?.addEventListener("click", () => {
      extra.innerHTML = `<form class="coach-form" data-pw-form novalidate><div class="form-grid">
          <label class="field"><span>Mot de passe actuel</span><input type="password" name="actuel" autocomplete="current-password"></label>
          <label class="field"><span>Nouveau (10 caractères au moins)</span><input type="password" name="nouveau" autocomplete="new-password"></label>
          <label class="field"><span>Encore une fois</span><input type="password" name="encore" autocomplete="new-password"></label></div>
          <div class="inline-actions"><button class="btn btn-primary" type="submit">${icon("check")}Changer</button><button class="btn btn-ghost" type="button" data-cancel>Annuler</button></div>
        </form>`;
      const form = extra.querySelector("form");
      form.querySelector("[data-cancel]").addEventListener("click", () => { extra.innerHTML = ""; });
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (form.elements.nouveau.value !== form.elements.encore.value) { status.textContent = "Les deux nouveaux mots de passe ne sont pas identiques."; return; }
        try {
          await api.post("/api/coach/mot-de-passe", { actuel: form.elements.actuel.value, nouveau: form.elements.nouveau.value });
          extra.innerHTML = "";
          toast("Mot de passe changé : tes autres appareils devront se reconnecter.");
        } catch (err) { status.textContent = err.message; }
      });
    });
  };

  render(info.adresse ? "compte" : "eleve");
}

