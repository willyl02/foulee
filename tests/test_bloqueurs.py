"""Aucun fichier de l'interface ne doit porter un nom que les bloqueurs de pub et de pistage arrêtent.

En 0.8.2b1, « analyse.js » (comme « analytics.js » des listes EasyPrivacy) était refusé par le navigateur
(net::ERR_BLOCKED_BY_CLIENT) : app.js ne se chargeait plus, la fenêtre restait sur « Chargement… »."""

import re

from foulee import config

SUSPECT = re.compile(r"analy|track|stat(s|istic)|\bads?\b|advert|banner|pixel|beacon|telemetr|metrics|counter|"
                     r"tag-?manager|social|share|popup", re.I)


def test_no_static_file_name_looks_like_a_tracker():
    names = [p.relative_to(config.STATIC_DIR).as_posix() for p in config.STATIC_DIR.rglob("*")
             if p.is_file() and "vendor" not in p.parts]
    assert names
    assert [n for n in names if SUSPECT.search(n.rsplit("/", 1)[-1])] == []
