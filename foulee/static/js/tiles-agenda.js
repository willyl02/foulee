// Calendrier d'entraînement : la vue « Calendrier » (le mois jour par jour, les prochaines séances) et les
// séances prévues de « Ta semaine ». Elles viennent du calendrier relié dans les Réglages (lien iCal : il ne
// s'affiche jamais, il reste dans le coffre du serveur).
import * as F from "./format.js";
import { icon } from "./icons.js";

export const SPORT_ICON = {
  course: "run", trail: "run", velo: "activity", natation: "wave", marche: "map", rando: "map", renfo: "dumbbell",
  souplesse: "heart", cardio: "bolt",
};

const STATUS = {
  fait: { icon: "check", label: "Fait" },
  manque: { icon: "close", label: "Manqué" },
  aujourdhui: { icon: "clock", label: "Aujourd'hui" },
  a_venir: { icon: "calendar", label: "À venir" },
  passe: { icon: "calendar", label: "Passé" },
};
const DOW = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];

/** Icône d'une séance prévue : le drapeau pour une course, sinon le sport. */
function planIcon(p) {
  if (p.type === "course") return icon("flag");
  if (p.type === "autre") return icon("calendar");
  return icon(SPORT_ICON[p.sport] || "activity");
}

/** « 09:30 » → « 9 h 30 » */
export function hour(text) {
  if (!text) return "";
  const [h, m] = text.split(":");
  return `${Number(h)} h ${m}`;
}

/** « Séance prévue · Course à pied · 9 h 30 · Fontainebleau » */
function planMeta(p) {
  const parts = [p.coach ? "Proposée par ton coach" : p.type === "course" ? "Course" : p.type === "seance" ? "Séance prévue" : "Événement"];
  if (p.type === "seance" && p.sport_label) parts.push(p.sport_label);
  if (p.heure) parts.push(hour(p.heure));
  else if (p.fin) parts.push(`jusqu'au ${F.dateLong(p.fin, { weekday: false })}`);
  if (p.lieu) parts.push(p.lieu);
  return parts.join(" · ");
}

function planTitle(p) {
  const state = STATUS[p.statut]?.label;
  return `${p.type === "course" ? "Course" : "Prévu"} : ${p.titre}${p.heure ? ` (${hour(p.heure)})` : ""}${p.type !== "autre" && state ? ` — ${state.toLowerCase()}` : ""}`;
}

/** Puce d'une séance prévue dans « Ta semaine » : son état (fait, manqué, à venir) et son titre. */
export function weekPlanChip(p) {
  const mark = p.type === "course" ? icon("flag") : p.statut === "fait" ? icon("check") : p.statut === "manque" ? icon("close") : planIcon(p);
  return `<button type="button" class="wday-plan is-${F.escape(p.statut)} is-${F.escape(p.type)}${p.coach ? " is-coach" : ""}" data-plan-day="${F.escape(p.date)}" title="${F.escape(planTitle(p))}">
    ${mark}<span>${F.escape(p.titre)}${p.type === "course" && p.heure ? ` · ${F.escape(hour(p.heure))}` : ""}</span></button>`;
}

/** « 3 faites · 1 manquée » : bilan d'une liste de séances prévues. */
export function tallyText(t, { short = false } = {}) {
  if (!t?.prevues) return "";
  const parts = [`${t.prevues} prévue${t.prevues > 1 ? "s" : ""}`];
  if (t.faites) parts.push(`${t.faites} faite${t.faites > 1 ? "s" : ""}`);
  if (t.manquees) parts.push(`${t.manquees} manquée${t.manquees > 1 ? "s" : ""}`);
  if (!short && t.a_venir) parts.push(`${t.a_venir} à venir`);
  return parts.join(" · ");
}

/** Pas de calendrier relié : une ligne et, sur la machine elle-même, le bouton qui mène aux Réglages. */
function notLinked(body, ctx) {
  const local = ctx.boot.acces === "local";
  body.innerHTML = `<div class="agenda-empty">
    <p>${local ? "Relie ton calendrier Garmin Connect (ou un agenda iCal) : ta prochaine course et tes prochaines séances s'afficheront ici." : "Aucun calendrier d'entraînement relié : son lien se colle depuis le PC où tourne Foulée, ou par Tailscale."}</p>
    ${local ? `<a class="btn" href="#/reglages?section=calendrier">${icon("calendar")}Relier mon calendrier</a>` : ""}
  </div>`;
}

const DAY_SHORT = ["Dim.", "Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam."];

const when = (iso, today) => {
  const days = Math.round((F.parseDate(iso) - F.parseDate(today)) / 86400000);
  if (days === 0) return "Aujourd'hui";
  if (days === 1) return "Demain";
  return `${DAY_SHORT[F.parseDate(iso).getDay()]} ${F.dateShort(iso)}`;
};

function countdown(days) {
  return days === 0 ? "C'est aujourd'hui" : days === 1 ? "Demain" : `J−${days}`;
}

// ------------------------------------------------------------ prochaines séances
export const a_venir = {
  title: () => "Prochaines séances",
  async render(body, p, ctx) {
    const today = F.isoDate(new Date());
    const days = Number(p.jours) || 14;
    const d = await ctx.get("/api/calendrier", { start: today, end: F.isoDate(F.addDays(new Date(), days - 1)) });
    body.classList.add("upcoming-body");
    if (!d.lie && !d.evenements.length) return notLinked(body, ctx);
    const items = d.evenements.filter((e) => e.type !== "autre" || e.date !== today);
    const race = d.prochaine_course;
    const n = d.bilan.prevues;
    ctx.sub(n ? `${n} prévue${n > 1 ? "s" : ""} sur ${days} jours` : `Rien de prévu sur ${days} jours`);
    body.innerHTML = `<div class="upcoming">
      ${race ? `<button type="button" class="up-race" data-plan-day="${F.escape(race.date)}" title="${F.escape(`${race.titre}, ${F.dateLong(race.date, { year: true })}`)}">
          <span class="up-count">${icon("flag")}<b>${countdown(race.dans_jours)}</b></span>
          <span class="up-race-text"><b>${F.escape(race.titre)}</b><small>${F.escape([F.dateLong(race.date), hour(race.heure), race.lieu].filter(Boolean).join(" · "))}</small></span>
        </button>` : ""}
      ${items.length ? `<ol class="up-list">${items.map((e) => `<li>
          <button type="button" class="up-item is-${F.escape(e.statut)} is-${F.escape(e.type)}${e.coach ? " is-coach" : ""}" data-plan-day="${F.escape(e.date)}" title="${F.escape(planTitle(e))}">
            <span class="up-when">${F.escape(when(e.date, today))}${e.heure ? ` · ${F.escape(hour(e.heure))}` : ""}</span>
            <span class="up-name">${planIcon(e)}<b>${F.escape(e.titre)}</b></span>
            <small>${e.statut === "fait" ? `${icon("check")}Fait` : F.escape(e.type === "course" ? "Course" : e.sport_label || "Séance")}</small>
          </button></li>`).join("")}</ol>`
        : `<p class="up-none">${race ? "Pas d'autre séance prévue" : "Rien de prévu"} dans les ${days} prochains jours.</p>`}
    </div>`;
    body.querySelectorAll("[data-plan-day]").forEach((b) => b.addEventListener("click", () => ctx.openDay(b.dataset.planDay)));
    // Des cartes au-delà du bord : le bord droit s'estompe, pour inviter à faire défiler
    const list = body.querySelector(".up-list");
    if (list) {
      const edge = () => list.classList.toggle("overflows", list.scrollLeft + list.clientWidth < list.scrollWidth - 2);
      list.addEventListener("scroll", edge, { passive: true });
      requestAnimationFrame(edge);
    }
  },
};

// ----------------------------------------------------------------- le mois
function monthStart(iso) {
  const d = F.parseDate(iso);
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function gridBounds(first) {
  const start = F.mondayOf(first);
  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0);
  const end = F.addDays(F.mondayOf(last), 6);
  return { start, end };
}

const monthName = (first) => {
  const text = F.periodLong(F.isoDate(first), "mois");
  return text.charAt(0).toUpperCase() + text.slice(1);
};

function dayLabel(iso, plans, acts) {
  const parts = [F.dateLong(iso)];
  plans.forEach((p) => parts.push(planTitle(p)));
  if (acts.length) parts.push(`${acts.length} séance${acts.length > 1 ? "s" : ""} faite${acts.length > 1 ? "s" : ""}`);
  return parts.join(". ");
}

function activityLine(a) {
  const amount = a.distance_km ? `${F.dec1(a.distance_km)} km` : a.duree;
  return `${icon(SPORT_ICON[a.sport] || "activity")}<span>${F.escape(amount)}</span>`;
}

function dayPanel(iso, d, today) {
  const plans = d.evenements.filter((e) => e.date === iso);
  const linked = new Set(plans.map((p) => p.seance_id).filter(Boolean));
  const acts = d.seances.filter((a) => a.date === iso);
  const extra = acts.filter((a) => !linked.has(a.id));
  const none = !d.lie ? (extra.length ? "" : "Aucune séance ce jour-là.")
    : iso > today ? "Rien de prévu ce jour-là." : iso === today ? "Rien de prévu aujourd'hui." : "Rien n'était prévu ce jour-là.";
  const race = plans.find((p) => p.type === "course" && iso >= today);
  const days = Math.round((F.parseDate(iso) - F.parseDate(today)) / 86400000);
  return `<header class="aday-head"><h3>${F.escape(F.dateLong(iso, { year: F.parseDate(iso).getFullYear() !== new Date().getFullYear() }))}</h3>
      ${iso === today ? `<span class="badge">Aujourd'hui</span>` : race ? `<span class="badge is-race">${countdown(days)}</span>` : ""}</header>
    ${plans.length ? plans.map((p) => {
      const done = p.seance_id ? acts.find((a) => a.id === p.seance_id) : null;
      return `<article class="aplan is-${F.escape(p.statut)} is-${F.escape(p.type)}${p.coach ? " is-coach" : ""}">
        <div class="aplan-title">${planIcon(p)}<b>${F.escape(p.titre)}</b>
          ${p.type !== "autre" ? `<span class="aplan-state">${icon(STATUS[p.statut]?.icon || "calendar")}${F.escape(STATUS[p.statut]?.label || "")}</span>` : ""}</div>
        <p class="aplan-meta">${F.escape(planMeta(p))}</p>
        ${p.description ? `<p class="aplan-desc">${F.escape(p.description)}</p>` : ""}
        ${p.coach ? `<a class="aplan-coach" href="#/coach">${icon("user")}Le détail et tes allures dans « Mon coach »</a>` : ""}
        ${p.coach && p.coach_id ? `<a class="aplan-coach" href="/api/coach/seances/${p.coach_id}.fit" download>${icon("download")}Le fichier pour ta montre (.fit)</a>` : ""}
        ${done ? `<button type="button" class="aplan-done" data-act="${F.escape(done.id)}">${activityLine(done)}<b>${F.escape(done.nom || done.sport_label)}</b><small>${F.escape(done.duree)}</small>${icon("right")}</button>` : ""}
      </article>`;
    }).join("") : none ? `<p class="aday-none">${none}</p>` : ""}
    ${extra.length ? `<h4 class="aday-sub">${plans.length ? "Fait aussi ce jour-là" : "Fait ce jour-là"}</h4>
      ${extra.map((a) => `<button type="button" class="aplan-done" data-act="${F.escape(a.id)}">${activityLine(a)}<b>${F.escape(a.nom || a.sport_label)}</b><small>${F.escape(a.duree)}</small>${icon("right")}</button>`).join("")}` : ""}`;
}

export const agenda = {
  title: () => "Calendrier d'entraînement",
  async render(body, p, ctx, tile, keep) {
    const today = F.isoDate(new Date());
    const asked = ctx.query?.get("jour");
    let selected = /^\d{4}-\d{2}-\d{2}$/.test(asked || "") ? asked : today;
    let month = monthStart(selected);
    let data = null;
    body.classList.add("agenda-body");

    const load = async () => {
      const { start, end } = gridBounds(month);
      data = await ctx.get("/api/calendrier", { start: F.isoDate(start), end: F.isoDate(end) });
    };

    const remember = () => {  // le jour choisi survit au rechargement de la page, sans redessiner la vue
      const [path, query] = location.hash.split("?");
      const params = new URLSearchParams(query || "");
      params.set("jour", selected);
      history.replaceState(null, "", `${path}?${params}`);
    };

    const cell = (day) => {
      const iso = F.isoDate(day);
      const plans = data.evenements.filter((e) => e.date === iso);
      const linked = new Set(plans.map((e) => e.seance_id).filter(Boolean));
      const acts = data.seances.filter((a) => a.date === iso);
      const extra = acts.filter((a) => !linked.has(a.id));
      const items = [
        ...plans.map((e) => `<span class="aitem is-${F.escape(e.statut)} is-${F.escape(e.type)}${e.coach ? " is-coach" : ""}">${e.type === "course" ? icon("flag") : e.statut === "fait" ? icon("check") : e.statut === "manque" ? icon("close") : planIcon(e)}<span>${F.escape(e.titre)}</span></span>`),
        ...extra.map((a) => `<span class="aitem is-extra">${activityLine(a)}</span>`),
      ];
      const dots = [...plans.map((e) => `<i class="adot is-${F.escape(e.statut)} is-${F.escape(e.type)}${e.coach ? " is-coach" : ""}"></i>`), ...extra.map(() => `<i class="adot is-extra"></i>`)].slice(0, 4).join("");
      const classes = ["aday", day.getMonth() !== month.getMonth() ? "out" : "", iso === today ? "today" : "", iso === selected ? "selected" : "",
        plans.some((e) => e.type === "course") ? "has-race" : "", iso < today ? "past" : ""].filter(Boolean).join(" ");
      return `<button type="button" class="${classes}" data-day="${iso}" aria-pressed="${iso === selected}" tabindex="${iso === selected ? 0 : -1}" aria-label="${F.escape(dayLabel(iso, plans, acts))}">
          <span class="aday-top"><span class="aday-num">${day.getDate()}</span><span class="aday-more" aria-hidden="true" hidden></span></span>
          <span class="aday-items" aria-hidden="true">${items.join("")}</span>
          <span class="aday-dots" aria-hidden="true">${dots}</span>
        </button>`;
    };

    // Dans chaque case, ce qui tient en hauteur ; le reste devient « +n » à côté du quantième
    const fit = () => {
      body.querySelectorAll(".aday").forEach((cell) => {
        const box = cell.querySelector(".aday-items");
        const more = cell.querySelector(".aday-more");
        const items = [...box.children];
        items.forEach((item) => { item.hidden = false; });
        let hidden = 0;
        if (box.offsetParent !== null && items.length) {  // (téléphone : des pastilles à la place)
          const limit = box.getBoundingClientRect().bottom + 1;
          const first = items.findIndex((item) => item.getBoundingClientRect().bottom > limit);
          if (first >= 0) {
            items.slice(first).forEach((item) => { item.hidden = true; });
            hidden = items.length - first;
          }
        }
        more.textContent = hidden ? `+${hidden}` : "";
        more.hidden = !hidden;
      });
    };

    const draw = () => {
      const { start, end } = gridBounds(month);
      const days = [];
      for (let d = new Date(start); d <= end; d = F.addDays(d, 1)) days.push(new Date(d));
      const inMonth = data.evenements.filter((e) => F.parseDate(e.date).getMonth() === month.getMonth());
      const t = { prevues: 0, faites: 0, manquees: 0, a_venir: 0 };
      inMonth.filter((e) => e.type !== "autre").forEach((e) => {
        t.prevues += 1;
        if (e.statut === "fait") t.faites += 1;
        else if (e.statut === "manque") t.manquees += 1;
        else t.a_venir += 1;
      });
      ctx.sub([data.lu_le ? `Lu ${F.relative(data.lu_le)}` : "", tallyText(t)].filter(Boolean).join(" · "));
      body.innerHTML = `<div class="agenda">
        <div class="agenda-main">
          <div class="agenda-bar">
            <button class="btn btn-ghost icon-btn" type="button" data-nav="-1" title="Mois précédent" aria-label="Mois précédent">${icon("left")}</button>
            <h3 class="agenda-month" aria-live="polite">${F.escape(monthName(month))}</h3>
            <button class="btn btn-ghost icon-btn" type="button" data-nav="1" title="Mois suivant" aria-label="Mois suivant">${icon("right")}</button>
            ${selected !== today || month.getMonth() !== new Date().getMonth() ? `<button class="btn btn-ghost small" type="button" data-today>Aujourd'hui</button>` : ""}
            <span class="agenda-legend" aria-hidden="true"><i class="adot is-fait"></i>fait<i class="adot is-manque"></i>manqué<i class="adot is-a_venir"></i>prévu<i class="adot is-course"></i>course<i class="adot is-extra"></i>hors plan</span>
          </div>
          ${data.lie ? "" : `<p class="agenda-hint">${icon("info")}<span>Aucun calendrier relié : seules tes séances faites s'affichent.${ctx.boot.acces === "local" ? ` <a href="#/reglages?section=calendrier">Relier mon calendrier</a> pour voir aussi les séances prévues et les courses.` : ""}</span></p>`}
          <div class="agenda-grid" aria-label="${F.escape(monthName(month))}">
            ${DOW.map((d) => `<span class="agenda-dow" aria-hidden="true">${d}</span>`).join("")}
            ${days.map(cell).join("")}
          </div>
        </div>
        <aside class="agenda-day" aria-live="polite">${dayPanel(selected, data, today)}</aside>
      </div>`;
      fit();
      wire();
    };

    const select = async (iso, { focus = false } = {}) => {
      selected = iso;
      remember();
      const wanted = monthStart(iso);
      if (wanted.getTime() !== month.getTime()) {
        month = wanted;
        await load();
        draw();
      } else {
        body.querySelectorAll(".aday").forEach((b) => {
          const on = b.dataset.day === iso;
          b.classList.toggle("selected", on);
          b.setAttribute("aria-pressed", String(on));
          b.tabIndex = on ? 0 : -1;
        });
        body.querySelector(".agenda-day").innerHTML = dayPanel(selected, data, today);
        wireDay();
      }
      if (focus) body.querySelector(`.aday[data-day="${iso}"]`)?.focus();
    };

    const wireDay = () => {
      body.querySelectorAll(".agenda-day [data-act]").forEach((b) => b.addEventListener("click", () => ctx.openActivity(b.dataset.act)));
    };

    const wire = () => {
      body.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", async () => {
        month = new Date(month.getFullYear(), month.getMonth() + Number(b.dataset.nav), 1);
        // le jour choisi suit : même quantième (ou le dernier du mois), aujourd'hui s'il tombe dans ce mois
        const now = new Date();
        const last = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
        selected = now.getFullYear() === month.getFullYear() && now.getMonth() === month.getMonth()
          ? today : F.isoDate(new Date(month.getFullYear(), month.getMonth(), Math.min(F.parseDate(selected).getDate(), last)));
        remember();
        await load();
        draw();
      }));
      body.querySelector("[data-today]")?.addEventListener("click", () => select(today, { focus: true }));
      const grid = body.querySelector(".agenda-grid");
      grid.addEventListener("click", (e) => {
        const day = e.target.closest("[data-day]");
        if (day) select(day.dataset.day);
      });
      grid.addEventListener("keydown", (e) => {
        const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
        if (!step) return;
        e.preventDefault();
        select(F.isoDate(F.addDays(F.parseDate(selected), step)), { focus: true });
      });
      wireDay();
    };

    await load();
    draw();
    // Fenêtre redimensionnée, tuile élargie : les cases se remplissent de nouveau
    let frame = 0;
    const observer = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(fit); });
    observer.observe(body);
    keep?.({ dispose: () => { observer.disconnect(); cancelAnimationFrame(frame); } });
  },
};
