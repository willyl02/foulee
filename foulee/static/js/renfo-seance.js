// « Ma séance de renfo » : la séance proposée d'après les exercices conseillés pour rééquilibrer, à reprendre dans
// l'Atelier (composer, garder, envoyer sur la montre ou en fichier .fit : voir atelier.js).

const clone = (x) => JSON.parse(JSON.stringify(x));
const blank = () => ({ id: "", titre: "", consigne: "", echauffement: true, etirements: true, exercices: [] });

/** La séance proposée d'après les familles à rééquilibrer : le premier exercice (le plus simple) de chacune. */
export function presetFrom(compenser) {
  const fams = compenser?.familles || [];
  if (!fams.length) return null;
  const side = compenser.cote === "avant" ? "avant" : "arrière";
  return {
    ...blank(),
    titre: `Renfo rééquilibrage ${side}`,
    consigne: "Qualité d'exécution avant le nombre de répétitions.",
    exercices: fams.flatMap((f) => f.exercices.slice(0, 2)).slice(0, 5).map((e) => fromLibrary(e)),
  };
}

function fromLibrary(e) {
  const m = /^\s*(\d+)\s*[×x]\s*(.+)$/.exec(e.dosage || "");
  return { nom: e.nom, series: e.series || (m ? Number(m[1]) : 3), reps: e.reps || (m ? m[2] : ""), recup_s: /\bs$/.test(e.reps || "") ? 30 : 45 };
}

let pending = null;

/** Ouvre l'Atelier sur l'onglet Renfo, avec une séance déjà composée (pas encore gardée) ou sur mes séances. */
export function openInAtelier(preset = null) {
  pending = preset ? clone(preset) : null;
  location.hash = "#/atelier?onglet=renfo";
}

/** La séance laissée par openInAtelier (une seule fois). */
export function takePending() {
  const out = pending;
  pending = null;
  return out;
}
