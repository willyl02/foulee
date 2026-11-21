"""Pièges JavaScript repérés dans l'interface, vérifiés sur tout le code."""

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "foulee" / "static" / "js"


def _handlers(source: str):
    for match in re.finditer(r"async \((e|ev|event)\) => \{", source):
        name, start, depth, i = match.group(1), match.end(), 1, match.end()
        while i < len(source) and depth:
            depth += {"{": 1, "}": -1}.get(source[i], 0)
            i += 1
        yield name, source[start:i], source[:match.start()].count("\n") + 1


def test_no_current_target_after_await():
    """Après un await, event.currentTarget vaut null : le bouton se garde dans une variable avant
    (0.8.3 : « Cannot set properties of null » après « Envoyer à mon coach »)."""
    found = []
    for path in sorted(JS.glob("*.js")):
        for name, body, line in _handlers(path.read_text(encoding="utf-8")):
            first = body.find("await ")
            if first >= 0 and f"{name}.currentTarget" in body[first:]:
                found.append(f"{path.name}:{line}")
    assert not found, "e.currentTarget utilisé après un await : " + ", ".join(found)
