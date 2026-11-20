"""Quelle séance faite répond à quelle séance prévue ? Partagé par le calendrier (chez l'élève) et le relais
(statut des séances du coach), pour que les deux disent la même chose.

Avant la 0.8.2, la première séance prévue du jour prenait la première séance faite du même sport : le
17 novembre, William fait « 21KM-S3-2-Seuil 60 » de son plan, et la « VMA courte » de son coach, prévue le même
jour, passait « faite » chez le coach. Désormais, chaque paire (prévue, faite) du même jour reçoit une note, et
les meilleures paires passent d'abord :

- le nom : la montre nomme une séance faite d'après l'entraînement suivi (« Mézy-Moulins - 21KM-S3-2-Seuil
  60 ») ; le titre prévu dans ce nom, c'est presque une signature ;
- la durée : celle qu'annoncent les blocs (séance du coach, ou esquisse lue dans le texte) face à la durée faite ;
- sinon, même jour et sport compatible suffisent, comme avant (une prévue, une faite : elles vont ensemble).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable

COACH_SUFFIX = re.compile(r"\s*\(coach\)\s*$", re.I)
STOP = {"de", "du", "des", "la", "le", "les", "et", "en", "au", "aux", "a", "un", "une", "sur", "avec", "pour",
        "seance", "course", "pied", "run", "running", "footing"}
BASE = 10.0
NAME_FULL = 100.0
NAME_WORDS = 40.0
DURATION_OK = 15.0
DURATION_OFF = -15.0
RACE = 5.0


def norm(text: str | None) -> str:
    """minuscules, sans accents ni ponctuation : « Mézy-Moulins - 21KM-S3-2-Seuil 60 » → « mezy moulins 21km s3 2 seuil 60 »."""
    text = COACH_SUFFIX.sub("", text or "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _words(text: str) -> set[str]:
    return {w for w in norm(text).split() if (len(w) >= 3 or w.isdigit()) and w not in STOP}


def estimated_minutes(blocks: list[dict] | None, vma: float | None = None) -> float:
    """Durée qu'annoncent des blocs (même calcul que l'esquisse : distance à l'allure visée, 1 min 30 pour un
    bloc « libre »)."""
    total = 0.0
    speed_of = lambda pct: (vma or 15.0) * (pct or 70) / 100  # noqa: E731  km/h
    for b in blocks or []:
        pct = b.get("pct_vma") or {1: 62, 2: 70, 3: 82, 4: 90, 5: 100}.get(b.get("zone_fc"), 70)
        minutes = b.get("duree_min") or 0
        if not minutes and b.get("distance_m"):
            minutes = b["distance_m"] / 1000 / speed_of(pct) * 60
        if not minutes and b.get("libre"):
            minutes = 1.5
        reps = max(1, min(50, int(b.get("repetitions") or 1)))
        rest = b.get("recup_min") or (1.5 if reps > 1 and (b.get("recup_libre") or b.get("recup_texte")) else 0)
        total += minutes * reps + rest * (reps - 1)
    return total


def score(planned: dict, done: dict, fits: Callable[[str | None, str | None], bool],
          vma: float | None = None) -> float | None:
    """Note d'une paire ; None si elle est impossible (sport incompatible, ou rien ne colle)."""
    if not fits(planned.get("sport"), done.get("sport")):
        return None
    note = BASE + (RACE if planned.get("type") == "course" else 0)
    title, name = norm(planned.get("titre")), norm(done.get("nom"))
    if len(title) >= 3 and name and f" {title} " in f" {name} ":
        note += NAME_FULL
    else:
        words = _words(planned.get("titre"))
        if words and name:
            note += NAME_WORDS * len(words & _words(done.get("nom"))) / len(words)
    expected = estimated_minutes(planned.get("blocs"), vma)
    seconds = done.get("duree_s")
    if expected >= 10 and seconds:
        ratio = seconds / 60 / expected
        if 0.6 <= ratio <= 1.6:
            note += DURATION_OK
        elif ratio < 0.35 or ratio > 3:
            note += DURATION_OFF
    return note if note > 0 else None


def assign(planned: list[dict], done: list[dict], fits: Callable[[str | None, str | None], bool],
           vma: float | None = None) -> dict[Any, dict]:
    """{clé de la prévue: la séance faite} pour tous les jours : chaque séance faite sert une fois, les meilleures
    paires d'abord (à note égale, l'ordre des prévues, puis celui des faites).

    planned : [{"cle", "date", "titre", "sport", "type"?, "blocs"?}] ; done : [{"cle", "date", "sport", "nom"?,
    "duree_s"?}]."""
    by_day: dict[str, list[dict]] = {}
    for item in done:
        by_day.setdefault(item["date"], []).append(item)
    pairs = []
    for i, p in enumerate(planned):
        for j, d in enumerate(by_day.get(p["date"], [])):
            note = score(p, d, fits, vma)
            if note is not None:
                pairs.append((-note, i, j, p, d))
    pairs.sort(key=lambda x: (x[0], x[1], x[2]))
    out: dict[Any, dict] = {}
    used: set[Any] = set()
    for _, _, _, p, d in pairs:
        if p["cle"] in out or d["cle"] in used:
            continue
        out[p["cle"]] = d
        used.add(d["cle"])
    return out


def same_session(coach_title: str, coach_date: str, title: str, day: str) -> bool:
    """La séance du coach revenue par le calendrier Garmin (« VMA courte », envoyée sur la montre par Foulée)
    est-elle la même que « VMA courte (coach) » ? Même jour, même titre."""
    a, b = norm(coach_title), norm(title)
    if coach_date != day or not a or not b:
        return False
    return a == b or (len(b) >= 40 and a.startswith(b))  # Garmin coupe le nom d'un entraînement à 50 caractères
