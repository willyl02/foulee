"""Construit le manuel unique de Foulée : uv run --with segno --with pillow --with playwright python build.py

Sortie : ../Foulee-manuel.pdf (le nom ne change pas d'une version à l'autre : les liens restent bons), plus
build/ (le HTML et un aperçu PNG de chaque page, ignorés par git). Puis : python check.py build/Foulee-manuel.html

Pour une nouvelle version : changer VERSION et MOIS dans kit.py, mettre à jour les pages concernées dans parts/,
remplacer ou ajouter les captures dans img/, puis relancer. Les captures doivent être floutées avant d'arriver ici
(numéro de licence, nom de famille, sujet ntfy, clés : rien de tout ça dans le dépôt public).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kit  # noqa: E402
from kit import Doc, MOIS, fr, icon  # noqa: E402
from parts import p1_foulee, p2_quotidien, p3_atelier, p4_eleve, p5_coach  # noqa: E402

HERE = Path(__file__).parent
SUBS = {
    1: "Ce que fait Foulée, ce qu'il te faut, l'interface",
    2: "Télécharger, installer, la clé API Garmin, les mises à jour",
    3: "Accueil, Aujourd'hui, calendrier, séance, récup, club, Withings, Strava",
    4: "Muscles travaillés, équilibre avant / arrière, progression, réglages",
    5: "Séances de course et de renfo, envoi sur la montre, compte sans coach",
    6: "Vues et tuiles, réglages, zones et couleurs, logothèque, aide",
    7: "Tailscale, l'accès depuis le téléphone, le dépannage",
    8: "Le relais du club, ce qui circule, la sécurité",
    9: "Rejoindre son coach, partager, Mon coach, la montre, les notifications",
    10: "Inviter, suivre, proposer des séances, les messages, gérer le groupe",
}


def cover(D):
    strip = "".join(f"<div><b>{fr(t)}</b><p>{fr(d)}</p></div>" for t, d in [
        ("Présentation", "Ce que Foulée fait pour toi, et comment il est pensé."),
        ("Installation", "Du téléchargement au premier import, pas à pas."),
        ("Utilisation", "Chaque vue, chaque réglage, avec des captures réelles."),
        ("Foulée Coach", "Le côté élève et le côté coach, jusque sur la montre."),
    ])
    return f"""
<section class="page mcover">
  <header class="top"><span class="brand"><span class="balise"><i></i><i></i></span>Foulée</span>
    <span class="crumb">{fr(f"Version {D.version} · {MOIS}")}</span></header>
  <div class="logo"><span class="balise big"><i></i><i></i></span><span>Foulée</span></div>
  <p class="title">{fr("Le manuel")}<span class="ver">{D.version}</span></p>
  <p class="tagline">{fr("Présentation, installation et utilisation de Foulée, le tableau de bord des coureurs qui tourne sur "
                          "ton PC, et de Foulée Coach, pour l'élève comme pour le coach. Un seul document, mis à jour à "
                          "chaque version.")}</p>
  <img class="hero" src="../img/v-overview.jpg" alt="">
  <div class="strip">{strip}</div>
  <p class="meta">{fr("Captures réelles de Foulée (données personnelles floutées) et profils de démonstration. Foulée est un "
                      "projet personnel, gratuit, sans compte et sans publicité : github.com/willyl02/foulee. "
                      "Ce manuel remplace les anciens documents séparés (présentation, téléphone, guides de l'élève et "
                      "du coach).")}</p>
</section>"""


def sommaire(D, toc):
    items = "".join(
        f'<li><span class="pn">Partie {n}</span><span class="tt">{fr(t)}<small>{fr(SUBS.get(n, ""))}</small></span>'
        f'<span class="pg">p.&nbsp;{p}</span></li>' for n, t, p in toc)
    guide = "".join(f"<li>{fr(t)}</li>" for t in [
        "Tu découvres Foulée : parties 1 à 3.",
        "Tu installes Foulée : partie 2, puis la partie 7 pour le téléphone.",
        "Ton coach t'a donné un code d'invitation : partie 9 (après la partie 2).",
        "Tu es coach : parties 8 et 10.",
        "Tu n'as pas de coach mais tu veux tes séances sur ta montre : partie 5.",
    ])
    return f"""
<section class="page sommaire">
  <header class="top"><span class="brand"><span class="balise"><i></i><i></i></span>Foulée</span>
    <span class="crumb">{fr("Sommaire")}</span></header>
  <span class="kicker">{fr(f"Foulée {D.version}")}</span>
  <h1>Sommaire</h1>
  <ol class="toc-parts">{items}</ol>
  <div class="box" style="margin-top:4mm"><h2>{icon("list")}{fr("Par où commencer ?")}</h2><ul>{guide}</ul></div>
  <footer class="foot"><span>{fr(f"Foulée {D.version} · manuel · présentation, installation et utilisation · {MOIS}")}</span>
    <span class="pno">N</span></footer>
</section>"""


def main():
    if len(sys.argv) > 1:
        kit.VERSION = sys.argv[1]
    D = Doc(kit.VERSION)
    p1_foulee.part1(D)
    p1_foulee.part2(D)
    p2_quotidien.part3(D)
    p2_quotidien.part4(D)
    p3_atelier.part5(D)
    p3_atelier.part6(D)
    p4_eleve.part7(D)
    p4_eleve.part8(D)
    p4_eleve.part9(D)
    p5_coach.part10(D)
    out = HERE / "build"
    out.mkdir(exist_ok=True)
    html = out / "Foulee-manuel.html"
    total = D.write(cover(D), sommaire(D, D.toc()), html)
    pdf = HERE.parent / "Foulee-manuel.pdf"
    kb = kit.render(html, pdf, out / "pages")
    print(f"{pdf.name} ({D.version}) : {total} pages, {kb} Ko")


if __name__ == "__main__":
    main()
