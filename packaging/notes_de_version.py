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
**Installer ou mettre à jour** (déjà installé ? Foulée se met à jour tout seul : Réglages → Mises à jour)

- **Windows** : télécharge `Foulee-Setup-{version}.exe` ci-dessous et double-clique dessus (pas besoin d'être
  administrateur). Windows peut afficher « Windows a protégé votre ordinateur » (installateur non signé) :
  clique sur « Informations complémentaires », puis « Exécuter quand même ».
- **Mac** : `Foulee-{version}-mac-arm64.dmg` pour un Mac Apple Silicon (M1, M2, M3, M4…), `-mac-intel.dmg`
  pour un Mac Intel (menu Pomme → À propos de ce Mac). Ouvre le .dmg et glisse Foulée dans Applications.
  L'application n'est pas signée par Apple : au premier lancement, macOS refuse de l'ouvrir ; va dans
  Réglages Système → Confidentialité et sécurité, tout en bas, « Ouvrir quand même », puis confirme.

Empreintes SHA-256 : voir `SHA256SUMS.txt`.
"""


def notes(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # « ## 0.4.0 » ne doit pas attraper « ## 0.4.0b1 » : rien de collé au numéro
    match = re.search(rf"^## \[?{re.escape(version)}\]?(?![\w.])[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    body = match.group(1).strip() if match else f"Foulée {version}."
    return body + "\n" + FOOTER.format(version=version)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(notes(sys.argv[1]))
