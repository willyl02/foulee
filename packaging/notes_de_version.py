"""Notes d'une version GitHub, tirées de CHANGELOG.md.

    python packaging/notes_de_version.py 0.4.0b1 > notes.md

Ce qui précède la ligne « --- » apparaît aussi dans Foulée (Réglages → Mises à jour).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOOTER = """
---
**Installer ou mettre à jour** : télécharge `Foulee-Setup-{version}.exe` ci-dessous et double-clique dessus
(pas besoin d'être administrateur). Déjà installé ? Foulée se met à jour tout seul : Réglages → Mises à jour.

Windows peut afficher « Windows a protégé votre ordinateur » (installateur non signé) :
clique sur « Informations complémentaires », puis « Exécuter quand même ».

Empreinte SHA-256 : voir `SHA256SUMS.txt`.
"""


def notes(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[?{re.escape(version)}\]?[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    body = match.group(1).strip() if match else f"Foulée {version}."
    return body + "\n" + FOOTER.format(version=version)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes(sys.argv[1]))
