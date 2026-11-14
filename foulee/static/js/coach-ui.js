// Briques communes des pages coach et élève : appels au relais (par la passerelle de Foulée), avatars, séances,
// fils de messages, tracé GPS, sous-navigation.
import * as api from "./api.js";
import * as F from "./format.js";
import { icon } from "./icons.js";
import { SPORT_ICON } from "./tiles-agenda.js";

const R = "/api/coach/r/";
export const rget = (path, params) => api.get(R + path, params, { fresh: true });
export const rpost = (path, body) => api.post(R + path, body);
export const rput = (path, body) => api.put(R + path, body);
export const rdel = (path) => api.del(R + path);

export const fail = (text) => `<p class="computed warn">${icon("warning")}<span>${F.escape(text)}</span></p>`;
export const loading = (text = "Chargement…") => `<p class="computed co-wait">${F.escape(text)}</p>`;

// --------------------------------------------------------------- avatars
const COLORS = ["#2a78d6", "#d3263a", "#13a06e", "#eb6834", "#8b5cd6", "#b07800", "#0f8a9a", "#c2417a"];

export function initials(name) {
  const parts = String(name || "?").replace(/[^\p{L}\p{N} .-]/gu, "").split(/[\s.-]+/).filter(Boolean);
  return ((parts[0]?.[0] || "?") + (parts.length > 1 ? parts[parts.length - 1][0] : parts[0]?.[1] || "")).toUpperCase();
}

export function avatar(name, { size = "", group = false } = {}) {
  if (group) return `<span class="co-av ${size}" style="background:#3987e5">${icon("club")}</span>`;
  let hash = 0;
  for (const ch of String(name || "")) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return `<span class="co-av ${size}" style="background:${COLORS[hash % COLORS.length]}" aria-hidden="true">${F.escape(initials(name))}</span>`;
}

// --------------------------------------------------------------- séances
export const sportIcon = (sport) => icon(SPORT_ICON[sport] || "activity");

export function km(meters) {
  if (!F.isNum(meters) || meters <= 0) return "";
  return meters >= 1000 ? `${F.dec1(meters / 1000)} km` : `${F.int(meters)} m`;
}

export const dur = (seconds) => (F.isNum(seconds) && seconds > 0 ? F.duration(seconds, { short: true }) : "");

/** « 12,4 km · 57 min · 4:38 /km · FC 158 » */
export function sessionFigures(s, { te = true } = {}) {
  return [km(s.distance_m), dur(s.duree_s), s.allure || (s.vitesse_kmh && !["course", "trail"].includes(s.sport) ? `${F.dec1(s.vitesse_kmh)} km/h` : ""),
    s.fc_moy ? `FC ${F.int(s.fc_moy)}` : "", te && s.effet_aerobie ? `effet aérobie ${F.dec1(s.effet_aerobie)}` : ""].filter(Boolean).join(" · ");
}

export function dayLabel(iso, { year = false } = {}) {
  const today = F.isoDate(new Date());
  if (iso === today) return "aujourd'hui";
  if (iso === F.isoDate(F.addDays(new Date(), -1))) return "hier";
  if (iso === F.isoDate(F.addDays(new Date(), 1))) return "demain";
  return F.dateLong(iso, { year }).replace(/^./, (c) => c.toLowerCase());
}

export const PROP_STATUS = {
  fait: { label: "Faite", cls: "good", icon: "check" },
  manque: { label: "Manquée", cls: "red", icon: "close" },
  aujourdhui: { label: "Aujourd'hui", cls: "blue", icon: "clock" },
  a_venir: { label: "À venir", cls: "", icon: "calendar" },
};

export function statusChip(statut) {
  const s = PROP_STATUS[statut];
  return s ? `<span class="co-chip ${s.cls}">${icon(s.icon)}${s.label}</span>` : "";
}

/** Allure pour un % de VMA : « 4:01 /km ». */
export function paceFor(vma, pct) {
  if (!vma || !pct) return "";
  const secs = Math.round(3600 / (vma * pct / 100));
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")} /km`;
}

export const GENRES = {
  echauffement: { label: "Échauffement", color: "#6fa8dc" },
  corps: { label: "Corps de séance", color: "#e69138" },
  calme: { label: "Retour au calme", color: "#93c47d" },
  libre: { label: "Libre", color: "#a7b1ac" },
};

/** Un bloc, lisible : « 3 × 10 min · 88 % VMA · récup 2 min ». */
export function blockSize(b) {
  const size = [];
  if (b.duree_min) size.push(b.duree_min >= 1 ? `${String(b.duree_min).replace(".", ",")} min` : `${Math.round(b.duree_min * 60)} s`);
  if (b.distance_m) size.push(b.distance_m >= 1000 ? `${String(b.distance_m / 1000).replace(".", ",")} km` : `${b.distance_m} m`);
  return `${(b.repetitions || 1) > 1 ? `${b.repetitions} × ` : ""}${size.join(" / ")}`;
}

export function blockIntensity(b) {
  if (b.pct_vma) return `${b.pct_vma} % VMA`;
  if (b.zone_fc) return `zone FC ${b.zone_fc}`;
  return "";
}

export function blockRest(b) {
  if ((b.repetitions || 1) < 2 || !(b.recup_min || b.recup_texte)) return "";
  const rest = b.recup_min ? (b.recup_min >= 1 ? `${String(b.recup_min).replace(".", ",")} min` : `${Math.round(b.recup_min * 60)} s`) : "";
  return `récup ${[rest, b.recup_texte].filter(Boolean).join(" ")}`;
}

/** Le déroulé d'une séance proposée, bloc par bloc, avec l'allure de cet élève si on connaît sa VMA. */
export function blocksHtml(blocs, vma) {
  return `<div class="co-blocks">${(blocs || []).map((b) => {
    const genre = GENRES[b.genre] || GENRES.corps;
    const pace = b.pct_vma ? paceFor(vma, b.pct_vma) : "";
    const sub = [blockIntensity(b), blockRest(b), b.note].filter(Boolean).join(" · ");
    return `<div class="co-blk"><i style="background:${genre.color}"></i>
      <div><b>${F.escape(b.nom || genre.label)}</b><span>${F.escape([blockSize(b), sub].filter(Boolean).join(" · "))}</span></div>
      <span class="co-val">${F.escape(pace || blockIntensity(b) || "")}</span></div>`;
  }).join("")}</div>`;
}

/** Durée totale estimée d'une séance (minutes) ; les blocs à la distance comptent avec l'allure si elle est connue. */
export function totalMinutes(blocs, vma) {
  let total = 0;
  let meters = 0;
  for (const b of blocs || []) {
    const reps = b.repetitions || 1;
    let one = b.duree_min || 0;
    if (!one && b.distance_m) {
      meters += reps * b.distance_m;
      const speed = vma && b.pct_vma ? vma * b.pct_vma / 100 : vma ? vma * 0.7 : 10;
      one = (b.distance_m / 1000) / speed * 60;
    } else if (one && vma) {
      meters += reps * one / 60 * (vma * (b.pct_vma || 65) / 100) * 1000;
    }
    total += reps * one + (reps > 1 ? (reps - 1) * (b.recup_min || 0) : 0);
  }
  return { minutes: Math.round(total), km: meters ? Math.round(meters / 100) / 10 : null };
}

// ---------------------------------------------------------- tracé GPS
/** Le tracé, dessiné sans fond de carte (rien ne part vers un service de cartes). */
export function traceSvg(points, { width = 520, height = 300 } = {}) {
  if (!points || points.length < 2) return "";
  const lat0 = points.reduce((a, p) => a + p[0], 0) / points.length;
  const k = Math.cos(lat0 * Math.PI / 180);
  const xy = points.map(([la, lo]) => [lo * k, -la]);
  const xs = xy.map((p) => p[0]);
  const ys = xy.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const pad = 16;
  const scale = Math.min((width - 2 * pad) / (x1 - x0 || 1e-9), (height - 2 * pad) / (y1 - y0 || 1e-9));
  const ox = (width - (x1 - x0) * scale) / 2;
  const oy = (height - (y1 - y0) * scale) / 2;
  const path = xy.map(([x, y], i) => `${i ? "L" : "M"}${((x - x0) * scale + ox).toFixed(1)} ${((y - y0) * scale + oy).toFixed(1)}`).join("");
  const [sx, sy] = [(xy[0][0] - x0) * scale + ox, (xy[0][1] - y0) * scale + oy];
  const [ex, ey] = [(xy.at(-1)[0] - x0) * scale + ox, (xy.at(-1)[1] - y0) * scale + oy];
  return `<svg class="co-trace" viewBox="0 0 ${width} ${height}" role="img" aria-label="Tracé GPS de la séance">
    <path d="${path}" class="co-trace-halo"/><path d="${path}" class="co-trace-line"/>
    <circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="5" class="co-trace-start"/><circle cx="${ex.toFixed(1)}" cy="${ey.toFixed(1)}" r="5" class="co-trace-end"/></svg>`;
}

// --------------------------------------------------- sous-navigation
export function tabs(role, active, { unread = 0 } = {}) {
  const items = role === "coach"
    ? [["eleves", "#/coach", "club", "Mes élèves"], ["messages", "#/coach/messages", "chat", "Messages"], ["proposer", "#/coach/proposer", "plus", "Proposer une séance"]]
    : [["coach", "#/coach", "user", "Mon coach"], ["messages", "#/coach/messages", "chat", "Messages"], ["partage", "#/coach/partage", "lock", "Mon partage"]];
  return `<nav class="co-tabs" aria-label="Coach et élèves">${items.map(([id, href, ic, label]) => `<a href="${href}" class="co-tab" ${id === active ? 'aria-current="page"' : ""}>
    ${icon(ic)}<span>${label}</span>${id === "messages" && unread ? `<span class="co-badge" data-coach-unread>${unread}</span>` : ""}</a>`).join("")}</nav>`;
}

// ------------------------------------------------------------ messages
function clockOf(stamp) { return String(stamp).slice(11, 16).replace(":", " h "); }

export function msgTime(stamp) {
  const day = String(stamp).slice(0, 10);
  return day === F.isoDate(new Date()) ? clockOf(stamp) : `${F.dateShort(day)} · ${clockOf(stamp)}`;
}

function linkify(text) {
  return F.escape(text).replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>').replace(/\n/g, "<br>");
}

function bubble(m, { role, fil, style }) {
  const canPin = role === "coach" && fil === "groupe";
  const canErase = m.moi || role === "coach";
  const tools = `<span class="co-msg-tools">
      ${canPin ? `<button type="button" class="co-mini" data-pin="${m.id}" data-on="${m.epingle ? 0 : 1}" title="${m.epingle ? "Ne plus épingler" : "Épingler en haut du fil"}">${icon("star")}</button>` : ""}
      ${canErase ? `<button type="button" class="co-mini" data-erase="${m.id}" title="Effacer ce message">${icon("trash")}</button>` : ""}</span>`;
  if (style === "comments") {
    return `<div class="co-comment${m.epingle ? " pin" : ""}" data-msg="${m.id}">${avatar(m.auteur.nom)}<div>
      <div class="co-comment-head"><b>${F.escape(m.auteur.nom)}</b>${m.auteur.role === "coach" ? '<span class="co-chip blue">coach</span>' : ""}
      ${m.epingle ? `<span class="co-chip blue">${icon("star")}Épinglé</span>` : ""}<time>${F.escape(msgTime(m.cree_le))}</time>${tools}</div>
      <p>${linkify(m.texte)}</p></div></div>`;
  }
  return `<div class="co-msg ${m.moi ? "me" : "them"}" data-msg="${m.id}">
    ${m.moi ? "" : `<span class="co-msg-who">${F.escape(m.auteur.nom)}</span>`}${linkify(m.texte)}
    <small>${F.escape(clockOf(m.cree_le))}${tools}</small></div>`;
}

/**
 * Un fil (conversation, fil du groupe ou fil d'une séance) : la liste et la zone d'écriture.
 * style « bubbles » (messagerie) ou « comments » (sous une séance, fil du groupe).
 */
export function mountThread(box, { fil, role, style = "bubbles", placeholder = "Écrire un message…", toast, onRead, empty = "Pas encore de message." }) {
  let messages = [];
  let alive = true;
  let loaded = false;  // un fil vide doit aussi remplacer « Chargement… »
  box.innerHTML = `<div class="co-thread ${style}"><div class="co-msgs" data-msgs>${loading()}</div>
    <form class="co-compose" data-compose><textarea rows="1" maxlength="4000" placeholder="${F.escape(placeholder)}" aria-label="${F.escape(placeholder)}"></textarea>
      <button class="btn btn-primary co-send" type="submit" title="Envoyer (Entrée)">${icon("up")}<span class="sr-only">Envoyer</span></button></form></div>`;
  const list = box.querySelector("[data-msgs]");
  const form = box.querySelector("[data-compose]");
  const area = form.querySelector("textarea");

  const draw = () => {
    if (!messages.length) { list.innerHTML = `<p class="co-empty">${F.escape(empty)}</p>`; return; }
    const pinned = style === "comments" ? messages.filter((m) => m.epingle) : [];
    let html = pinned.length ? `<div class="co-pinned">${pinned.map((m) => bubble(m, { role, fil, style })).join("")}</div>` : "";
    let lastDay = "";
    for (const m of messages) {
      if (style === "comments" && m.epingle) continue;
      const day = m.cree_le.slice(0, 10);
      if (style === "bubbles" && day !== lastDay) {
        html += `<span class="co-day-sep">${F.escape(dayLabel(day))}</span>`;
        lastDay = day;
      }
      html += bubble(m, { role, fil, style });
    }
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
    list.innerHTML = html;
    if (style === "bubbles" && atBottom) list.scrollTop = list.scrollHeight;
    list.querySelectorAll("[data-pin]").forEach((b) => b.addEventListener("click", async () => {
      try { await rpost(`messages/${b.dataset.pin}/epingle`, { epingle: b.dataset.on === "1" }); await load(); } catch (err) { toast?.(err.message); }
    }));
    list.querySelectorAll("[data-erase]").forEach((b) => b.addEventListener("click", async () => {
      if (!window.confirm("Effacer ce message ? Il disparaît pour tout le monde.")) return;
      try { await rdel(`messages/${b.dataset.erase}`); messages = messages.filter((m) => String(m.id) !== b.dataset.erase); draw(); } catch (err) { toast?.(err.message); }
    }));
  };

  const load = async () => {
    try {
      const data = await rget(`fils/${encodeURIComponent(fil)}`);
      if (!alive) return null;
      const changed = !loaded || data.messages.length !== messages.length || data.messages.at(-1)?.id !== messages.at(-1)?.id
        || data.messages.some((m, i) => m.epingle !== messages[i]?.epingle);
      loaded = true;
      messages = data.messages;
      if (changed) draw();
      if (style === "bubbles" && changed) list.scrollTop = list.scrollHeight;
      onRead?.(data);
      return data;
    } catch (err) {
      if (alive) list.innerHTML = fail(err.message);
      return null;
    }
  };

  const grow = () => { area.style.height = "auto"; area.style.height = `${Math.min(area.scrollHeight, 180)}px`; };
  area.addEventListener("input", grow);
  area.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = area.value.trim();
    if (!text) return;
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const res = await rpost(`fils/${encodeURIComponent(fil)}`, { texte: text });
      messages.push(res.message);
      area.value = "";
      grow();
      draw();
      list.scrollTop = style === "bubbles" ? list.scrollHeight : list.scrollTop;
      window.dispatchEvent(new CustomEvent("coach:sent"));
    } catch (err) { toast?.(err.message); }
    button.disabled = false;
    area.focus();
  });

  const refresh = () => load();
  const onNews = () => { if (alive && document.body.contains(box)) load(); else stop(); };
  const timer = setInterval(() => { if (!document.hidden) onNews(); }, 15000);
  window.addEventListener("coach:news", onNews);
  function stop() { alive = false; clearInterval(timer); window.removeEventListener("coach:news", onNews); }
  const ready = load();
  return { refresh, stop, ready, focus: () => area.focus() };
}
