// Tuile « Withings : dernières mesures » : dernière pesée et composition, dernière tension, dernière nuit,
// dernière journée, chacune face à tes habitudes. Seules les familles mesurées par tes appareils s'affichent.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";

const BODY_ROWS = ["wi_fat_pct", "wi_muscle_kg", "wi_water_pct", "wi_bone_kg", "wi_visceral", "wi_bmi", "wi_pwv", "wi_bmr"];
const PHASES = [["wi_deep_s", "Profond", "deep"], ["wi_light_s", "Léger", "light"], ["wi_rem_s", "Paradoxal", "rem"], ["wi_awake_s", "Éveil", "awake"]];

function when(day) {
  const today = F.isoDate(new Date());
  const yesterday = F.isoDate(F.addDays(new Date(), -1));
  if (day === today) return "aujourd'hui";
  if (day === yesterday) return "hier";
  return `le ${F.dateLong(day, { weekday: false })}`;
}

/** Écart coloré selon le sens « favorable » de la métrique (vert / rouge), neutre sinon. */
function trend(meta, value, ref) {
  if (!F.isNum(value) || !F.isNum(ref) || F.value(meta, value) === F.value(meta, ref)) return "";  // pas d'écart visible
  const text = F.delta(meta, value, ref);
  if (!text) return "";
  const up = value > ref;
  const tone = !meta?.better ? "" : (up === (meta.better === "up")) ? "good" : "bad";
  return `<span class="wi-delta ${tone}">${F.escape(text)}</span>`;
}

function bodyCard(d, ctx) {
  const v = d.valeurs || {};
  const ref = d.reference?.valeurs || {};
  const weight = ctx.meta("wi_weight_kg");
  const rows = BODY_ROWS.filter((k) => F.isNum(v[k])).map((k) => {
    const meta = ctx.meta(k);
    const label = meta.label.replace(/ \(Withings\)$/, "");
    return `<div><dt>${F.escape(label)}</dt><dd>${F.escape(F.value(meta, v[k]))}${trend(meta, v[k], ref[k])}</dd></div>`;
  });
  return `<article class="wi-card">
      <h3>${icon("scale")}Dernière pesée <small>${F.escape(when(d.date))}</small></h3>
      <p class="wi-big">${F.escape(F.value(weight, v.wi_weight_kg))}${trend(weight, v.wi_weight_kg, ref.wi_weight_kg)}</p>
      ${d.reference ? `<p class="wi-sub">Écarts face à la pesée du ${F.escape(F.dateLong(d.reference.date, { weekday: false }))} · ${F.int(d.pesees_30j)} pesée${d.pesees_30j > 1 ? "s" : ""} en 30 jours</p>` : `<p class="wi-sub">${F.int(d.pesees_30j)} pesée${d.pesees_30j > 1 ? "s" : ""} en 30 jours</p>`}
      ${rows.length ? `<dl class="wi-rows">${rows.join("")}</dl>` : ""}
    </article>`;
}

function pressureCard(d) {
  const v = d.valeurs || {};
  const avg = d.moyenne_7j || {};
  const level = d.niveau;
  return `<article class="wi-card">
      <h3>${icon("heart")}Dernière tension <small>${F.escape(when(d.date))}</small></h3>
      <p class="wi-big">${F.int(v.wi_bp_sys)}<span class="wi-slash">/</span>${F.int(v.wi_bp_dia)} <small>mmHg</small></p>
      ${level ? `<p><span class="wi-level ${F.escape(level.niveau)}">${F.escape(level.libelle)}</span>${F.isNum(v.wi_pulse) ? ` <span class="wi-sub">· pouls ${F.int(v.wi_pulse)} bpm</span>` : ""}</p>` : ""}
      ${avg.jours >= 2 ? `<p class="wi-sub">Moyenne des ${F.int(avg.jours)} jours mesurés sur 7 : <b>${F.int(avg.wi_bp_sys)}/${F.int(avg.wi_bp_dia)}</b>${d.niveau_7j ? ` (${F.escape(d.niveau_7j.libelle.toLowerCase())})` : ""}</p>` : ""}
      <p class="wi-foot">Repères de la Société européenne d'hypertension. Seul un médecin peut poser un diagnostic.</p>
    </article>`;
}

function sleepCard(d, ctx) {
  const v = d.valeurs || {};
  const parts = PHASES.filter(([k]) => F.isNum(v[k]) && v[k] > 0);
  const total = parts.reduce((sum, [k]) => sum + v[k], 0);
  const bar = total ? `<div class="wi-phases" role="img" aria-label="${F.escape(parts.map(([k, l]) => `${l} ${F.duration(v[k])}`).join(", "))}">${parts.map(([k, , cls]) => `<span class="${cls}" style="flex:${v[k]}" title="${F.escape(F.duration(v[k]))}"></span>`).join("")}</div>
      <p class="wi-legend">${parts.map(([k, l, cls]) => `<span><i class="${cls}"></i>${l} ${F.escape(F.duration(v[k]))}</span>`).join("")}</p>` : "";
  const extra = [
    F.isNum(v.wi_bed_h) && F.isNum(v.wi_rise_h) ? `${F.clock(v.wi_bed_h)} → ${F.clock(v.wi_rise_h)}` : "",
    F.isNum(v.wi_sleep_hr) ? `FC ${F.int(v.wi_sleep_hr)} bpm` : "",
    F.isNum(v.wi_sleep_resp) ? `${F.dec1(v.wi_sleep_resp)} resp/min` : "",
    F.isNum(v.wi_wake_count) ? `${F.int(v.wi_wake_count)} réveil${v.wi_wake_count > 1 ? "s" : ""}` : "",
  ].filter(Boolean);
  return `<article class="wi-card">
      <h3>${icon("moon")}Dernière nuit <small>${F.escape(when(d.date))}</small></h3>
      <p class="wi-big">${F.escape(F.duration(v.wi_sleep_s))}${F.isNum(v.wi_sleep_score) ? ` <small>score ${F.int(v.wi_sleep_score)}/100</small>` : ""}</p>
      ${bar}
      ${extra.length ? `<p class="wi-sub">${extra.map(F.escape).join(" · ")}</p>` : ""}
      ${F.isNum(d.moyenne_7j) ? `<p class="wi-sub">Moyenne des 7 dernières nuits : <b>${F.escape(F.duration(d.moyenne_7j))}</b>${trend(ctx.meta("wi_sleep_s"), v.wi_sleep_s, d.moyenne_7j)}</p>` : ""}
    </article>`;
}

function activityCard(d, ctx) {
  const v = d.valeurs || {};
  const extra = [
    F.isNum(v.wi_distance_km) ? `${F.dec1(v.wi_distance_km)} km` : "",
    F.isNum(v.wi_active_s) ? `${F.duration(v.wi_active_s)} actif` : "",
    F.isNum(v.wi_cal_active) ? `${F.int(v.wi_cal_active)} kcal actives` : "",
  ].filter(Boolean);
  return `<article class="wi-card">
      <h3>${icon("activity")}Activité <small>${F.escape(when(d.date))}</small></h3>
      <p class="wi-big">${F.int(v.wi_steps)} <small>pas</small>${trend(ctx.meta("wi_steps"), v.wi_steps, d.moyenne_7j)}</p>
      ${extra.length ? `<p class="wi-sub">${extra.map(F.escape).join(" · ")}</p>` : ""}
      ${F.isNum(d.moyenne_7j) ? `<p class="wi-sub">Moyenne sur 7 jours : <b>${F.int(d.moyenne_7j)} pas</b></p>` : ""}
    </article>`;
}

export const withings = {
  ownHead: true,
  title: () => "Withings",
  async render(body, p, ctx) {
    const d = await ctx.get("/api/withings/resume");
    const st = d.etat || {};
    const cards = [d.corps && bodyCard(d.corps, ctx), d.tension && pressureCard(d.tension), d.sommeil && sleepCard(d.sommeil, ctx),
      d.activite && activityCard(d.activite, ctx)].filter(Boolean);
    let status;
    if (st.refus) {
      status = `<span class="wi-warn">${icon("warning")}Withings n'accepte plus l'accès de Foulée : <a href="#/reglages?section=withings">reconnecte ton compte</a>.</span>`;
    } else if (st.demo) {
      status = "Appareils fictifs (mode démo)";
    } else if (!st.connecte) {
      status = `Compte non connecté · <a href="#/reglages?section=withings">Réglages → Withings</a>`;
    } else {
      status = `Dernière synchro ${F.escape(F.relative(st.derniere_synchro))}`;
    }
    body.classList.add("scroll");
    body.innerHTML = `<div class="wi">
        <header class="wi-head">
          <span class="club-badge wi-badge">${icon("scale")}</span>
          <div class="club-title"><h2>Withings</h2><p>${status}</p></div>
          <a class="btn btn-ghost icon-btn club-edit" href="#/reglages?section=withings" title="Réglages Withings" aria-label="Réglages Withings">${icon("settings")}</a>
        </header>
        ${cards.length ? `<div class="wi-cards">${cards.join("")}</div>` : `<p class="wi-empty">${icon("info")}<span>${st.connecte
          ? "Pas encore de mesure Withings. Pèse-toi ou prends ta tension : la mesure arrive avec la prochaine synchro (toutes les 3 heures par défaut)."
          : "Relie ton compte Withings dans <a href=\"#/reglages?section=withings\">Réglages → Withings</a> : tes pesées, ta tension et tes nuits s'afficheront ici."}</span></p>`}
      </div>`;
  },
};
