"""Diagnostic : un appel par flux Garmin, et un rapport qui ne contient AUCUNE de tes valeurs.

Le rapport liste, pour chaque flux : le statut HTTP, le nombre d'éléments, les
noms des champs reçus et les métriques que Foulée a su en tirer. C'est ce qu'il
faut pour vérifier que les parseurs collent à ce que ta montre envoie vraiment.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .. import config, fitfile
from . import parse
from .client import GarminError, GarminSession


def shape(value: Any, depth: int = 0, max_depth: int = 3) -> list[str]:
    pad = "    " * depth
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)) and depth < max_depth:
                kind = "objet" if isinstance(item, dict) else f"liste[{len(item)}]"
                lines.append(f"{pad}- {key} : {kind}")
                sample = item if isinstance(item, dict) else (item[0] if item else None)
                if sample is not None:
                    lines += shape(sample, depth + 1, max_depth)
            else:
                lines.append(f"{pad}- {key} : {type(item).__name__ if item is not None else 'null'}")
    elif isinstance(value, list):
        lines.append(f"{pad}(liste de {len(value)} éléments)")
        if value:
            lines += shape(value[0], depth + 1, max_depth)
    return lines


def run() -> Path:
    today = date.today()
    yesterday = today - timedelta(days=1)
    report: list[str] = [f"Diagnostic Foulée — {datetime.now():%d/%m/%Y %H:%M}", ""]
    tests = [
        ("Profil", "get_user_profile_settings", (), {}, None),
        ("Résumés quotidiens", "get_daily_summaries", (yesterday - timedelta(days=2), yesterday), {},
         (parse.daily_summary_items, parse.parse_daily_summary)),
        ("Sommeil", "get_daily_sleep_summaries", (yesterday - timedelta(days=2), today), {},
         (parse.sleep_items, parse.parse_sleep)),
        ("VFC", "get_daily_hrv_summaries", (yesterday - timedelta(days=6), today), {},
         (parse.hrv_items, parse.parse_hrv)),
        ("Body Battery", "get_daily_body_battery", (yesterday, today), {}, None),
        ("Poids", "get_weight_measurements", (today - timedelta(days=90), today), {},
         (parse.weight_items, parse.parse_weight)),
        ("Zones FC", "get_heart_rate_zones", (), {}, None),
        ("Âge fitness", "get_fitness_age", (today,), {}, None),
        ("Séances", "search_activities", (), {"start": 0, "limit": 3}, None),
    ]
    first_activity = None
    with GarminSession() as session:
        for label, method, args, kwargs, parser in tests:
            report.append(f"== {label} ({method})")
            try:
                payload = session.call(method, *args, **kwargs)
            except GarminError as exc:
                report += [f"   ERREUR : {exc}", ""]
                continue
            if payload is None:
                report += ["   Réponse vide", ""]
                continue
            report.append("   OK")
            report += ["   " + line for line in shape(payload)[:80]]
            if parser:
                extractor, normalizer = parser
                found: set[str] = set()
                items = extractor(payload)
                for item in items:
                    _, values = normalizer(item)
                    found |= {k for k, v in values.items() if v is not None}
                report.append(f"   → {len(items)} élément(s), métriques comprises : {', '.join(sorted(found)) or 'aucune'}")
            if method == "search_activities":
                items = parse.items_of(payload, "activityList")
                if items:
                    row = parse.parse_activity(items[0])
                    filled = sorted(k for k, v in (row or {}).items() if v is not None and k not in ("name", "description"))
                    report.append(f"   → champs de séance compris : {', '.join(filled)}")
                    first_activity = items[0].get("activityId")
            report.append("")
        if first_activity:
            report.append("== Fichier FIT de la dernière séance")
            try:
                content = session.download_activity(first_activity)
                fit = fitfile.extract_fit(content or b"")
                if not fit:
                    report.append("   Pas de fichier FIT dans la réponse")
                else:
                    decoded = fitfile.decode(fit)
                    streams = decoded["streams"]
                    report.append(f"   OK — sport : {decoded['sport']} / {decoded['sub_sport']}")
                    report.append(f"   points : {len(streams.get('t', []))}, courbes : {', '.join(k for k in streams if k != 't')}")
                    report.append(f"   tours : {len(decoded['laps'])}, avertissements : {decoded['warnings'] or 'aucun'}")
            except (GarminError, ValueError) as exc:
                report.append(f"   ERREUR : {exc}")
        report.append("")
        report.append(f"Appels effectués : {session.calls}")
    path = config.data_dir() / f"diagnostic-{datetime.now():%Y%m%d-%H%M%S}.txt"
    path.write_text("\n".join(report), encoding="utf-8")
    return path
