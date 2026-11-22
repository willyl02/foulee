// Le temps passé dans chaque zone d'une séance (FC ou allure), façon Garmin Connect : la zone 5 en haut, une barre
// à la couleur de la zone (Réglages → Zones FC → Couleurs des zones), le temps et la part de la séance.
import * as C from "./charts.js";
import * as F from "./format.js";

const TITLES = { fc: "Zones de fréquence cardiaque", allure: "Zones d'allure" };

/** table : {noms, bornes, secondes, total} (analysis.zone_tables) ; kind : « fc » ou « allure ». */
export function zoneTableHTML(table, kind, { title = TITLES[kind], sub = "" } = {}) {
  if (!table) return "";
  const total = table.total || table.secondes.reduce((a, b) => a + b, 0);
  const top = Math.max(...table.secondes, 1);
  const colors = C.palette().zones;  // pour l'encre du numéro : foncée sur le gris et l'orange, blanche ailleurs
  const rows = [4, 3, 2, 1, 0].map((i) => {
    const sec = table.secondes[i] || 0;
    const pct = total ? Math.round((sec / total) * 100) : 0;
    return `<li class="zt-row${sec ? "" : " none"}" style="--c:var(--z${i + 1})">
      <span class="zt-z" style="color:${C.inkOn(colors[i])}">Z${i + 1}</span>
      <span class="zt-name"><b>${F.escape(String(table.noms[i] || "").replace(/^Z\d\s+/, ""))}</b><small>${F.escape(table.bornes[i] || "")}</small></span>
      <span class="zt-bar" aria-hidden="true"><i style="width:${sec ? Math.max(1.5, (sec / top) * 100) : 0}%"></i></span>
      <span class="zt-time">${F.escape(F.duration(sec))}</span>
      <span class="zt-pct">${pct} %</span>
    </li>`;
  }).join("");
  const label = `${title} : ${[4, 3, 2, 1, 0].map((i) => `zone ${i + 1}, ${F.duration(table.secondes[i] || 0)}`).join(" ; ")}`;
  return `<section class="zt" aria-label="${F.escape(label)}">
    <header class="zt-head"><h4>${F.escape(title)}</h4><span>${F.escape(sub || `${F.duration(total)} au total`)}</span></header>
    <ol class="zt-rows">${rows}</ol>
  </section>`;
}
