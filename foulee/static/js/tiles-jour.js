// « Ma séance du jour » (vue Aujourd'hui) : avant, la séance prévue, le verdict de la nuit en une phrase, la
// météo heure par heure et le meilleur créneau selon le poste ; après, le débrief et le ressenti (pour le coach).
import * as api from "./api.js";
import { blocksHtml, sportIcon } from "./coach-ui.js";
import * as F from "./format.js";
import { analysisHTML, wireAnalysis } from "./fractions.js";
import { icon } from "./icons.js";
import { sketchSVG } from "./sketch.js";
import { zoneTableHTML } from "./zone-table.js";

const LEVEL_ICON = { feu: "check", doucement: "flat", repos: "warning" };
const RPE = ["", "Très facile", "Facile", "Facile", "Modéré", "Modéré", "Soutenu", "Difficile", "Difficile", "Très difficile", "Maximal"];

/** Le temps d'une heure (codes météo de l'OMS) : une icône et un mot. */
function sky(h) {
  const c = h.code ?? 0;
  if (c >= 95) return ["storm", "Orage"];
  if (c >= 71 && c <= 77) return ["snow", "Neige"];
  if ((c >= 51 && c <= 67) || (c >= 80 && c <= 82)) return ["rain", "Pluie"];
  if (c === 45 || c === 48) return ["cloud", "Brouillard"];
  if (c >= 2) return ["cloud", "Nuageux"];
  return [h.jour ? "sun" : "moon", h.jour ? "Soleil" : "Nuit claire"];
}

function weatherHTML(w, slot, poste) {
  if (!w) return `<p class="hint">Météo indisponible (pas de sortie récente avec position, ou pas de réseau).</p>`;
  const from = slot ? Number(slot.debut.slice(0, 2)) : -1;
  const to = slot ? Number(slot.fin.slice(0, 2)) || 24 : -1;
  const work = (h) => {
    if (!poste?.debut || !poste?.fin) return false;
    const a = Number(poste.debut.slice(0, 2));
    const b = Number(poste.fin.slice(0, 2));
    return a < b ? h >= a && h < b : h >= a || h < b;
  };
  const hours = w.heures.filter((h) => h.heure >= 6 && h.heure <= 21);
  return `<div class="sj-hours" role="list">${hours.map((h) => {
    const [ico, label] = sky(h);
    const inSlot = h.heure >= from && h.heure < to;
    return `<div class="sj-hour${inSlot ? " slot" : ""}${work(h.heure) ? " work" : ""}${h.jour ? "" : " night"}" role="listitem" title="${F.escape(`${h.heure} h : ${label}, ${F.dec1(h.temp)} °C (ressenti ${F.dec1(h.ressentie)} °C), pluie ${h.pluie_pct ?? 0} %, vent ${F.int(h.vent)} km/h`)}">
      <span class="sj-h">${h.heure} h</span>${icon(ico)}<b>${F.int(h.temp)}°</b><small class="${(h.pluie_pct || 0) >= 50 ? "wet" : ""}">${h.pluie_pct ?? 0} %</small>
      ${work(h.heure) ? `<em>Travail</em>` : ""}</div>`;
  }).join("")}</div>
  <p class="sj-src">Prévisions <a href="${F.escape(w.lien)}" target="_blank" rel="noopener">${F.escape(w.source)}</a>, près de ta dernière sortie · pluie : probabilité</p>`;
}

function plannedCard(p, vma) {
  const sent = p.coach;
  return `<article class="sj-plan${p.statut === "fait" ? " done" : ""}">
    <header><span class="co-ico">${sportIcon(p.sport)}</span><div><b>${F.escape(p.titre)}</b>
      <span>${[p.coach ? "de ton coach" : "ton plan", p.heure ? `à ${p.heure}` : "", p.minutes ? `≈ ${F.duration(p.minutes * 60, { short: true })}` : ""].filter(Boolean).map(F.escape).join(" · ")}</span></div>
      ${p.statut === "fait" ? `<span class="sj-chip ok">${icon("check")}Faite</span>` : ""}</header>
    ${p.blocs?.length ? `<div class="sj-sk">${sketchSVG(p.blocs, { vma, height: 30, approx: p.esquisse_approchee })}</div>${blocksHtml(p.blocs, vma)}`
      : p.description ? `<p class="sj-desc">${F.escape(p.description.slice(0, 400))}</p>` : ""}
    ${p.statut !== "fait" ? `<div class="inline-actions">${sent && p.coach_id
      ? `<button class="btn btn-small btn-primary" type="button" data-watch="${p.coach_id}">${icon("watch")}Envoyer sur ma montre</button>
         <a class="btn btn-small btn-ghost" href="/api/coach/seances/${p.coach_id}.fit" download>${icon("download")}Fichier .fit</a>`
      : `<span class="sj-note">${icon("watch")}Déjà dans ton calendrier Garmin : ta montre l'a à la synchro.</span>`}</div>` : ""}
  </article>`;
}

function doneCard(a, planned, linked) {
  const plan = planned.find((p) => p.id === a.prevue);
  const feel = a.ressenti || {};
  const figures = [a.distance_km ? `${F.dec1(a.distance_km)} km` : "", a.duree, a.allure, a.fc_moy ? `FC ${a.fc_moy}` : ""].filter(Boolean);
  const versus = plan?.minutes && a.duree_s ? `prévu ≈ ${F.duration(plan.minutes * 60, { short: true })}, fait ${F.duration(a.duree_s, { short: true })}` : "";
  return `<article class="sj-done" data-done="${F.escape(a.id)}">
    <header><span class="co-ico">${sportIcon(a.sport)}</span><div><b>${F.escape(a.nom || a.sport_label || "Séance")}</b>
      <span>${F.escape([a.heure ? `à ${a.heure}` : "", ...figures].filter(Boolean).join(" · "))}</span></div>
      <button class="btn btn-small btn-ghost" type="button" data-open="${F.escape(a.id)}">${icon("activity")}Détail</button></header>
    ${plan ? `<p class="sj-vs">${icon("check")}<span>Pour <b>${F.escape(plan.titre)}</b>${versus ? ` : ${F.escape(versus)}` : ""}</span></p>` : ""}
    <div class="sj-feel">
      <span class="sj-label">Ton ressenti</span>
      <div class="sj-rpe" role="radiogroup" aria-label="Ressenti de 1 (très facile) à 10 (maximal)">${[...Array(10)].map((_, i) => `<button type="button" role="radio" aria-checked="${feel.rpe === i + 1}" data-rpe="${i + 1}" title="${RPE[i + 1]}">${i + 1}</button>`).join("")}</div>
      <span class="sj-rpe-word" data-word>${feel.rpe ? RPE[feel.rpe] : "de 1 (très facile) à 10 (maximal)"}</span>
      <textarea rows="2" maxlength="500" data-note placeholder="Un mot : jambes lourdes, bonnes sensations, douleur au mollet…">${F.escape(feel.note || "")}</textarea>
      <div class="inline-actions"><span class="hint" data-saved>${feel.rpe || feel.note ? "Enregistré" : ""}</span>
        ${linked ? `<button class="btn btn-small" type="button" data-coach>${icon("chat")}${feel.envoye_le ? "Renvoyer à mon coach" : "Envoyer à mon coach"}</button>` : ""}</div>
    </div>
    <details class="sj-more" data-more><summary>${icon("wave")}Analyse fraction par fraction</summary><div class="sj-analysis" data-analysis><p class="hint">Lecture des tours…</p></div></details>
  </article>`;
}

export const jour = {
  title: () => "Ma séance du jour",
  async render(body, p, ctx) {
    const d = await ctx.get("/api/jour");
    const linked = ctx.boot.coach?.role === "eleve";
    const todo = d.prevues.filter((x) => x.statut !== "fait");
    const poste = d.poste;
    ctx.sub([poste?.nom && poste.actif ? `${poste.nom}${poste.debut ? ` ${poste.debut}–${poste.fin}` : ""}` : "", F.dateLong(d.date)].filter(Boolean).join(" · "));
    const c = d.conseil;
    const zoned = d.faites.filter((a) => a.zones_fc);  // séances faites aujourd'hui avec leur temps par zone FC
    body.innerHTML = `<div class="sj">
      <p class="sj-verdict ${c.niveau || ""}">${icon(LEVEL_ICON[c.niveau] || "info")}<span><b>${F.escape(c.titre)}</b> ${F.escape(c.texte)}${d.forme?.resume && c.niveau ? `<small>${F.escape(d.forme.resume)}</small>` : ""}</span></p>
      <div class="sj-cols">
        <section class="sj-col"><h3>${todo.length ? "Prévu aujourd'hui" : d.faites.length ? "Prévu aujourd'hui" : "Rien de prévu aujourd'hui"}</h3>
          ${d.prevues.length ? d.prevues.map((x) => plannedCard(x, d.vma)).join("")
            : `<p class="hint">${c.niveau === "repos" ? "Profite d'une journée de repos." : "Envie de bouger ? Un footing facile de 40 min en endurance, ou une séance de renfo : compose-la dans l'Atelier (colonne de gauche)."}</p>`}
        </section>
        ${p.meteo !== false || zoned.length ? `<div class="sj-col sj-side">
          ${p.meteo !== false ? `<section><h3>Quand courir</h3><div data-weather><p class="hint">Lecture de la météo…</p></div></section>` : ""}
          ${zoned.length ? `<section class="sj-zones"><h3>Temps par zone FC</h3>${zoned.map((a) => zoneTableHTML(a.zones_fc, "fc", {
            title: zoned.length > 1 ? (a.nom || a.sport_label || "Séance") : "Séance du jour",
            sub: `${[a.heure ? `à ${a.heure}` : "", F.duration(a.zones_fc.total)].filter(Boolean).join(" · ")}`,
          })).join("")}</section>` : ""}
        </div>` : ""}
      </div>
      ${d.faites.length ? `<section class="sj-after"><h3>Après la séance</h3>${d.faites.map((a) => doneCard(a, d.prevues, linked)).join("")}</section>` : ""}
    </div>`;

    // La tuile grandit avec son contenu (avant la séance, après, analyse ouverte) : pas de barre de défilement
    const tile = body.closest(".tile");
    const fit = () => {
      if (!tile || tile.closest(".editing")) return;
      const css = getComputedStyle(document.documentElement);
      const row = parseFloat(css.getPropertyValue("--row")) || 140;
      const gap = parseFloat(getComputedStyle(tile.parentElement).rowGap) || 16;
      const need = body.offsetTop + body.querySelector(".sj").scrollHeight + 16;
      const rows = Math.max(2, Math.ceil((need + gap) / (row + gap)));
      tile.style.gridRow = `span ${rows}`;
      tile.style.setProperty("--h", rows);
    };
    body.classList.remove("scroll");
    new ResizeObserver(() => requestAnimationFrame(fit)).observe(body.querySelector(".sj"));

    // météo et créneau, sans retarder le reste
    if (p.meteo !== false) {
      ctx.get("/api/jour/meteo").then((m) => {
        const box = body.querySelector("[data-weather]");
        if (!box) return;
        const slot = m.creneau;
        if (!slot) box.closest("section").querySelector("h3").textContent = "La météo du jour";
        box.innerHTML = `${slot ? `<p class="sj-slot">${icon("clock")}<span><b>Ton créneau : ${F.escape(slot.debut.replace(":00", " h"))} – ${F.escape(slot.fin.replace(":00", " h"))}</b>${slot.raison ? ` · ${F.escape(slot.raison)}` : ""}</span></p>` : ""}${weatherHTML(m.meteo, slot, poste)}`;
      }).catch(() => {
        const box = body.querySelector("[data-weather]");
        if (box) box.innerHTML = `<p class="hint">Météo indisponible pour l'instant.</p>`;
      });
    }

    body.querySelectorAll("[data-watch]").forEach((btn) => btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        const res = await api.post(`/api/coach/seances/${btn.dataset.watch}/montre`, {});
        if (res.a_relier && res.adresse) {
          window.open(res.adresse, "_blank", "noopener");
          ctx.toast("Relie ton compte Garmin dans la fenêtre ouverte, puis renvoie la séance.");
        } else ctx.toast("Séance envoyée : synchronise ta montre.");
      } catch (err) { ctx.toast(err.message, { error: true }); }
      btn.disabled = false;
    }));

    body.querySelectorAll("[data-done]").forEach((card) => {
      const id = card.dataset.done;
      card.querySelector("[data-open]").addEventListener("click", () => ctx.openActivity(id));
      // l'analyse fraction par fraction de la séance faite, à la demande (elle prend de la place)
      const more = card.querySelector("[data-more]");
      more.addEventListener("toggle", () => {
        if (!more.open || more.dataset.loaded) return;
        more.dataset.loaded = "1";
        const box = card.querySelector("[data-analysis]");
        api.get(`/api/activities/${encodeURIComponent(id)}`).then((a) => {
          const html = a?.analyse?.length > 1 ? analysisHTML(a.analyse, null, { running: ["course", "trail"].includes(a.sport) }) : "";
          box.innerHTML = html || `<p class="hint">Pas de tours à découper pour cette séance.</p>`;
          if (html) wireAnalysis(box);
        }).catch(() => { box.innerHTML = `<p class="hint">Analyse indisponible.</p>`; });
      });
      const saved = card.querySelector("[data-saved]");
      const note = card.querySelector("[data-note]");
      let rpe = (d.faites.find((x) => x.id === id)?.ressenti || {}).rpe || null;
      const save = async () => {
        try {
          await api.put(`/api/jour/ressenti/${encodeURIComponent(id)}`, { rpe, note: note.value });
          saved.textContent = "Enregistré";
        } catch (err) { ctx.toast(err.message, { error: true }); }
      };
      card.querySelectorAll("[data-rpe]").forEach((b) => b.addEventListener("click", () => {
        rpe = Number(b.dataset.rpe);
        card.querySelectorAll("[data-rpe]").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
        card.querySelector("[data-word]").textContent = RPE[rpe];
        save();
      }));
      let timer = null;
      note.addEventListener("input", () => { saved.textContent = ""; clearTimeout(timer); timer = setTimeout(save, 800); });
      card.querySelector("[data-coach]")?.addEventListener("click", async (e) => {
        const btn = e.currentTarget; // après un await, e.currentTarget ne vaut plus rien
        btn.disabled = true;
        try {
          clearTimeout(timer);
          await save();
          await api.post(`/api/jour/ressenti/${encodeURIComponent(id)}/coach`, {});
          ctx.toast("Envoyé à ton coach, dans votre conversation.");
          btn.innerHTML = `${icon("chat")}Renvoyer à mon coach`;
        } catch (err) { ctx.toast(err.message, { error: true }); }
        btn.disabled = false;
      });
    });
  },
};
