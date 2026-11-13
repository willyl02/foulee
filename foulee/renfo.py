"""Renfo : les exercices de tes séances de renforcement, et les muscles qu'ils travaillent.

Garmin résume chaque séance de renfo exercice par exercice (« summarizedExerciseSets » de la liste des
séances, gardée telle quelle dans la table raw) : catégorie et nom de l'exercice, nombre de séries,
répétitions, durée, charge la plus lourde et tonnage. Ce résumé suit les corrections faites dans
l'appli Garmin Connect (exercice changé, répétitions ajustées) : c'est lui qui fait foi.

Foulée le range dans la table ``exercises``, traduit les exercices en français et en déduit les muscles
travaillés : une série compte pour 1 sur un muscle principal, pour ½ sur un muscle secondaire.

Seules comptent les séances de musculation et de cardio / HIIT (``SPORTS``) : en yoga, Pilates ou
mobilité, la montre « devine » des séries (un haussement d'épaules de 40 minutes…) qui n'en sont pas.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

P, S = 1.0, 0.5  # muscle principal, muscle secondaire
SPORTS = ("renfo", "cardio")  # sports de Foulée dont les exercices comptent (musculation, cardio / HIIT)

# Groupes musculaires de la carte du corps, dans l'ordre d'affichage
MUSCLES: list[tuple[str, str]] = [
    ("pectoraux", "Pectoraux"), ("epaules", "Épaules"), ("biceps", "Biceps"), ("triceps", "Triceps"),
    ("avant_bras", "Avant-bras"), ("abdos", "Abdominaux"), ("obliques", "Obliques"), ("trapezes", "Trapèzes"),
    ("dorsaux", "Dorsaux"), ("lombaires", "Lombaires"), ("fessiers", "Fessiers"), ("abducteurs", "Abducteurs"),
    ("adducteurs", "Adducteurs"), ("quadriceps", "Quadriceps"), ("ischios", "Ischio-jambiers"),
    ("mollets", "Mollets"),
]
MUSCLE_LABELS = dict(MUSCLES)

# Catégories d'exercices de Garmin (profil FIT) : libellé générique et muscles par défaut
CATEGORIES: dict[str, tuple[str, dict[str, float]]] = {
    "bench_press": ("Développé couché", {"pectoraux": P, "triceps": S, "epaules": S}),
    "calf_raise": ("Mollets", {"mollets": P}),
    "cardio": ("Cardio", {"quadriceps": S, "fessiers": S, "mollets": S}),
    "carry": ("Portés", {"avant_bras": P, "trapezes": P, "abdos": S}),
    "chop": ("Bûcheron", {"obliques": P, "abdos": S, "epaules": S}),
    "core": ("Abdos et gainage", {"abdos": P, "obliques": S, "lombaires": S}),
    "crunch": ("Crunchs", {"abdos": P, "obliques": S}),
    "curl": ("Curls", {"biceps": P, "avant_bras": S}),
    "deadlift": ("Soulevé de terre", {"ischios": P, "fessiers": P, "lombaires": P, "trapezes": S, "avant_bras": S}),
    "flye": ("Écartés", {"pectoraux": P, "epaules": S}),
    "hip_raise": ("Ponts fessiers", {"fessiers": P, "ischios": P, "lombaires": S}),
    "hip_stability": ("Stabilité de la hanche", {"abducteurs": P, "fessiers": P}),
    "hip_swing": ("Swings", {"fessiers": P, "ischios": P, "lombaires": S}),
    "hyperextension": ("Extensions lombaires", {"lombaires": P, "fessiers": S, "ischios": S}),
    "lateral_raise": ("Élévations latérales", {"epaules": P, "trapezes": S}),
    "leg_curl": ("Leg curls", {"ischios": P}),
    "leg_raise": ("Relevés de jambes", {"abdos": P, "quadriceps": S}),
    "lunge": ("Fentes", {"quadriceps": P, "fessiers": P, "ischios": S, "adducteurs": S}),
    "olympic_lift": ("Haltérophilie", {"quadriceps": P, "fessiers": P, "trapezes": P, "ischios": S, "epaules": S,
                                       "lombaires": S}),
    "plank": ("Planche et gainage", {"abdos": P, "obliques": S, "epaules": S}),
    "plyo": ("Pliométrie", {"quadriceps": P, "fessiers": P, "mollets": P, "ischios": S}),
    "pull_up": ("Tractions", {"dorsaux": P, "biceps": P, "avant_bras": S, "epaules": S}),
    "push_up": ("Pompes", {"pectoraux": P, "triceps": P, "epaules": S, "abdos": S}),
    "row": ("Rowing", {"dorsaux": P, "trapezes": S, "biceps": S, "epaules": S}),
    "shoulder_press": ("Développé épaules", {"epaules": P, "triceps": S, "trapezes": S}),
    "shoulder_stability": ("Stabilité de l'épaule", {"epaules": P, "trapezes": S}),
    "shrug": ("Haussements d'épaules", {"trapezes": P, "avant_bras": S}),
    "sit_up": ("Relevés de buste", {"abdos": P, "obliques": S}),
    "squat": ("Squats", {"quadriceps": P, "fessiers": P, "ischios": S, "adducteurs": S}),
    "total_body": ("Corps entier", {"quadriceps": S, "fessiers": S, "pectoraux": S, "epaules": S, "abdos": S}),
    "triceps_extension": ("Triceps", {"triceps": P}),
    "warm_up": ("Échauffement et étirements", {}),
    "run": ("Course", {"quadriceps": S, "ischios": S, "mollets": S}),
    "run_indoor": ("Course", {"quadriceps": S, "ischios": S, "mollets": S}),
    "bike": ("Vélo", {"quadriceps": S, "fessiers": S}),
    "bike_outdoor": ("Vélo", {"quadriceps": S, "fessiers": S}),
    "indoor_bike": ("Vélo d'intérieur", {"quadriceps": S, "fessiers": S}),
    "cardio_sensors": ("Cardio", {}),
    "move": ("Mobilité", {}),
    "pose": ("Postures", {}),
    "banded_exercises": ("Exercices avec élastique", {}),
    "battle_rope": ("Cordes ondulatoires", {"epaules": P, "avant_bras": S, "abdos": S}),
    "elliptical": ("Elliptique", {"quadriceps": S, "fessiers": S}),
    "floor_climb": ("Montée d'étages", {"quadriceps": S, "fessiers": S, "mollets": S}),
    "indoor_row": ("Rameur", {"dorsaux": P, "quadriceps": S, "biceps": S}),
    "ladder": ("Échelle de rythme", {"mollets": P, "quadriceps": S}),
    "sandbag": ("Sac lesté", {"quadriceps": S, "fessiers": S, "epaules": S, "abdos": S}),
    "sled": ("Traîneau", {"quadriceps": P, "fessiers": P, "mollets": S}),
    "sledge_hammer": ("Masse", {"epaules": P, "obliques": S, "abdos": S}),
    "stair_stepper": ("Stepper", {"quadriceps": S, "fessiers": S, "mollets": S}),
    "suspension": ("Sangles de suspension", {}),
    "tire": ("Pneu", {"quadriceps": P, "fessiers": P, "lombaires": S, "epaules": S}),
    "unknown": ("Exercice non précisé", {}),
    "texte": ("Noté dans la description Strava", {}),  # séance Strava : l'exercice tel qu'il est écrit
}
# Échauffement, étirements, mobilité : pas du renforcement, ils comptent au plus pour ½ série
LIGHT = {"warm_up", "move", "pose", "cardio_sensors"}
# Catégories trop larges : les muscles se lisent dans le nom de l'exercice
GENERIC = {"warm_up", "move", "pose", "banded_exercises", "suspension", "sandbag", "cardio", "total_body"}

_SWING = {"fessiers": P, "ischios": P, "lombaires": S}
# Exercices dont les muscles diffèrent de leur catégorie : (catégorie ou « * », motif du nom, muscles)
OVERRIDES: list[tuple[str, str, dict[str, float]]] = [
    ("*", r"kettlebell_swing|dumbbell_swing|one_arm_swing|step_out_swing", _SWING),
    ("plank", r"side_plank|lateral_roll", {"obliques": P, "abdos": S, "abducteurs": S}),
    ("plank", r"mountain_climber|bear_crawl|plank_jacks|pike", {"abdos": P, "epaules": S, "quadriceps": S}),
    ("plank", r"reverse_plank", {"fessiers": P, "lombaires": S, "ischios": S}),
    ("hip_raise", r"clam", {"abducteurs": P, "fessiers": S}),
    ("hip_raise", r"inner_thigh", {"adducteurs": P}),
    ("hip_raise", r"leg_circles|leg_lift", {"abducteurs": P, "fessiers": S}),
    ("hip_raise", r"leg_curl", {"ischios": P, "fessiers": P}),
    ("hip_stability", r"dead_bug", {"abdos": P, "obliques": S}),
    ("hip_stability", r"adduction|inner_thigh", {"adducteurs": P}),
    ("hip_stability", r"quadruped|rear_leg|hip_extension", {"fessiers": P, "ischios": S}),
    ("leg_curl", r"good_morning", {"ischios": P, "lombaires": P, "fessiers": S}),
    ("leg_curl", r"hip_raise", {"ischios": P, "fessiers": P}),
    ("plyo", r"lateral|side_to_side|shuffle", {"quadriceps": P, "fessiers": P, "mollets": P, "ischios": S,
                                                "abducteurs": S}),
    ("plyo", r"medicine_ball", {"epaules": P, "abdos": S, "dorsaux": S}),
    ("plyo", r"knee_strike", {"abdos": P, "quadriceps": S}),
    ("squat", r"leg_press", {"quadriceps": P, "fessiers": S}),
    ("squat", r"thruster|wall_ball|to_press|overhead", {"quadriceps": P, "fessiers": P, "ischios": S, "epaules": S}),
    ("squat", r"sumo|plie|wide_stance", {"quadriceps": P, "fessiers": P, "adducteurs": P, "ischios": S}),
    ("lunge", r"side|lateral", {"quadriceps": P, "fessiers": P, "adducteurs": P, "abducteurs": S}),
    ("deadlift", r"single_leg|one_leg|rdl", {"ischios": P, "fessiers": P, "lombaires": S, "abducteurs": S}),
    ("core", r"russian_twist|oblique|side_bend|windmill|crescent", {"obliques": P, "abdos": S}),
    ("core", r"back_extension", {"lombaires": P, "fessiers": S}),
    ("crunch", r"oblique|side|bicycle|cross", {"abdos": P, "obliques": P}),
    ("crunch", r"flutter_kicks|leg_levers|leg_extensions", {"abdos": P, "quadriceps": S}),
    ("hyperextension", r"knee_raises|kicks|knee_tucks", {"abdos": P}),
    ("flye", r"reverse|rear", {"epaules": P, "trapezes": S}),
    ("cardio", r"jump_rope|double_under|triple_under|jacks|ski_moguls", {"mollets": P, "quadriceps": S}),
    ("total_body", r"burpee|squat_thrust|man_makers|squat_plank", {"quadriceps": P, "fessiers": S, "pectoraux": S,
                                                                   "epaules": S, "abdos": S}),
]
# Muscles lus dans le nom, pour les catégories trop larges (le premier motif trouvé l'emporte)
NAME_MUSCLES: list[tuple[str, dict[str, float]]] = [
    (r"side_plank", {"obliques": P, "abdos": S, "abducteurs": S}),
    (r"calf", {"mollets": P}),
    (r"ankle", {"mollets": P}),
    (r"hamstring|leg_curl", {"ischios": P}),
    (r"glute|bridge|hip_thrust|hip_raise|donkey_kick|hip_extension", {"fessiers": P, "ischios": S}),
    (r"clam|fire_hydrant|abduction|band_walk|lateral_walk|it_band", {"abducteurs": P, "fessiers": S}),
    (r"adduction|inner_thigh|butterfly|groin", {"adducteurs": P}),
    (r"squat", {"quadriceps": P, "fessiers": P, "ischios": S}),
    (r"lunge|split", {"quadriceps": P, "fessiers": P, "ischios": S}),
    (r"deadlift|good_morning|rdl", {"ischios": P, "fessiers": P, "lombaires": S}),
    (r"plank|mountain_climber|bear_crawl|dead_?bug|crunch|sit_up|twist|v_up|hollow|boat|ab_", {"abdos": P,
                                                                                               "obliques": S}),
    (r"oblique", {"obliques": P}),
    (r"superman|back_extension|cobra|locust|spine|spinal|thoracic|cat_c", {"lombaires": P}),
    (r"push_?up|chest|pectoral|fly", {"pectoraux": P, "triceps": S, "epaules": S}),
    (r"pull_?up|chin_up|pull_?down|latpull|lat_", {"dorsaux": P, "biceps": S}),
    (r"row|face_pull|pull_apart|power_pull", {"dorsaux": P, "trapezes": S, "epaules": S}),
    (r"press|raise|shoulder|arm_circle|y_fly|external_rotation|internal_rotation|scapula", {"epaules": P}),
    (r"curl|biceps", {"biceps": P}),
    (r"tricep|dip", {"triceps": P}),
    (r"forearm|wrist", {"avant_bras": P}),
    (r"neck|levator", {"trapezes": P}),
    (r"quad|hip_flexor|psoas|lunging", {"quadriceps": P}),
    (r"hip|leg_swing|groiner|pigeon|piriformis|figure_four|90_90", {"fessiers": P, "adducteurs": S}),
    (r"jump|hop|skip|knee_drive|high_kn|burpee|jack|sprint|run|jog", {"quadriceps": S, "mollets": S, "fessiers": S}),
]

# -------------------------------------------------------------- noms en français
# Bases : l'exercice lui-même (genre pour accorder « lesté », « alterné »…) ; m, f, mp, fp
BASES: dict[str, tuple[str, str]] = {
    "squat": ("Squat", "m"), "squats": ("Squat", "m"), "back squat": ("Squat arrière", "m"),
    "back squats": ("Squat arrière", "m"), "front squat": ("Squat avant", "m"), "goblet squat": ("Squat goblet", "m"),
    "split squat": ("Squat fendu", "m"), "bulgarian split squat": ("Squat bulgare", "m"),
    "sumo squat": ("Squat sumo", "m"), "box squat": ("Box squat", "m"), "hack squat": ("Hack squat", "m"),
    "pistol squat": ("Squat pistol", "m"), "overhead squat": ("Squat bras tendus", "m"),
    "jump squat": ("Squat sauté", "m"), "jump squats": ("Squat sauté", "m"), "squat jumps": ("Squat sauté", "m"),
    "squat jump": ("Squat sauté", "m"), "wall squat": ("Chaise", "f"), "wall sit": ("Chaise", "f"),
    "single leg squat": ("Squat sur une jambe", "m"), "one legged squat": ("Squat sur une jambe", "m"),
    "prisoner squat": ("Squat mains derrière la tête", "m"), "plie squat": ("Squat plié", "m"),
    "step up": ("Step-up", "m"), "stepover": ("Passage de banc", "m"), "leg press": ("Presse à cuisses", "f"),
    "thrusters": ("Thruster", "m"), "wall ball": ("Wall ball", "m"),
    "lunge": ("Fente", "f"), "lunges": ("Fente", "f"), "reverse lunge": ("Fente arrière", "f"),
    "side lunge": ("Fente latérale", "f"), "lateral lunge": ("Fente latérale", "f"),
    "walking lunge": ("Fente marchée", "f"), "crossover lunge": ("Fente croisée", "f"),
    "curtsy lunge": ("Fente croisée", "f"), "jump lunge": ("Fente sautée", "f"), "box lunge": ("Fente sur box", "f"),
    "diagonal lunge": ("Fente en diagonale", "f"), "overhead lunge": ("Fente bras tendus", "f"),
    "drop lunge": ("Fente croisée arrière", "f"), "runners lunge to balance": ("Fente du coureur avec équilibre", "f"),
    "lunge matrix": ("Fentes multidirectionnelles", "fp"), "body weight wall squat": ("Chaise", "f"),
    "calf raise": ("Élévation des mollets", "f"), "calf raises": ("Élévation des mollets", "f"),
    "toe raise": ("Élévation des orteils", "f"),
    "plank": ("Planche", "f"), "side plank": ("Planche latérale", "f"), "reverse plank": ("Planche inversée", "f"),
    "mountain climber": ("Mountain climber", "m"), "bear crawl": ("Marche de l'ours", "f"),
    "crunch": ("Crunch", "m"), "reverse crunch": ("Crunch inversé", "m"), "bicycle crunch": ("Crunch vélo", "m"),
    "bicycle": ("Crunch vélo", "m"), "sit up": ("Relevé de buste", "m"), "v up": ("V-up", "m"),
    "russian twist": ("Rotation russe", "f"), "dead bug": ("Dead bug", "m"), "deadbug": ("Dead bug", "m"),
    "leg raise": ("Relevé de jambes", "m"), "knee raise": ("Relevé de genoux", "m"),
    "hanging leg raise": ("Relevé de jambes suspendu", "m"), "hanging knee raise": ("Relevé de genoux suspendu", "m"),
    "flutter kicks": ("Battements de jambes", "mp"), "hollow rock": ("Hollow rock", "m"),
    "superman": ("Superman", "m"), "superman from floor": ("Superman", "m"), "back extension": ("Extension lombaire", "f"),
    "inchworm": ("Chenille", "f"), "bird dog": ("Bird dog", "m"),
    "opposite arm and leg balance": ("Bird dog", "m"),
    "hip raise": ("Pont fessier", "m"), "bridge": ("Pont", "m"), "glute bridge": ("Pont fessier", "m"),
    "hip thrust": ("Hip thrust", "m"), "clams": ("Clamshell", "m"), "clam shells": ("Clamshell", "m"),
    "clam bridge": ("Pont avec clamshell", "m"), "fire hydrant": ("Fire hydrant", "m"),
    "fire hydrant kicks": ("Fire hydrant", "m"), "donkey kick": ("Donkey kick", "m"),
    "hip circles": ("Cercles de hanches", "mp"), "lateral band walks": ("Pas chassés avec élastique", "mp"),
    "lateral walks with band at ankles": ("Pas chassés, élastique aux chevilles", "mp"),
    "side lying leg raise": ("Élévation latérale de la jambe", "f"),
    "standing hip abduction": ("Abduction de hanche debout", "f"), "hip abduction": ("Abduction de hanche", "f"),
    "standing adduction": ("Adduction de hanche debout", "f"), "quadruped hip extension": ("Extension de hanche à quatre pattes", "f"),
    "kettlebell swing": ("Swing kettlebell", "m"), "swing": ("Swing", "m"), "one arm swing": ("Swing à un bras", "m"),
    "leg curl": ("Leg curl", "m"), "hamstring curl": ("Leg curl", "m"), "hamstring curls": ("Leg curl", "m"),
    "good morning": ("Good morning", "m"),
    "swiss ball hip raise and leg curl": ("Pont et leg curl sur swiss ball", "m"),
    "single leg swiss ball hip raise and leg curl": ("Pont et leg curl sur swiss ball, sur une jambe", "m"),
    "deadlift": ("Soulevé de terre", "m"), "romanian deadlift": ("Soulevé de terre roumain", "m"),
    "straight leg deadlift": ("Soulevé de terre jambes tendues", "m"), "sumo deadlift": ("Soulevé de terre sumo", "m"),
    "single leg deadlift": ("Soulevé de terre sur une jambe", "m"),
    "single leg romanian deadlift": ("Soulevé de terre roumain sur une jambe", "m"),
    "push up": ("Pompe", "f"), "push ups": ("Pompe", "f"), "pull up": ("Traction", "f"),
    "pull ups": ("Traction", "f"), "chin up": ("Traction en supination", "f"),
    "lat pulldown": ("Tirage vertical", "m"), "row": ("Rowing", "m"), "inverted row": ("Rowing inversé", "m"),
    "bent over row": ("Rowing buste penché", "m"), "upright row": ("Tirage menton", "m"), "face pull": ("Face pull", "m"),
    "bench press": ("Développé couché", "m"), "chest press": ("Développé pectoraux", "m"),
    "floor press": ("Développé au sol", "m"), "shoulder press": ("Développé épaules", "m"),
    "overhead press": ("Développé au-dessus de la tête", "m"), "military press": ("Développé militaire", "m"),
    "push press": ("Push press", "m"), "arnold press": ("Développé Arnold", "m"),
    "biceps curl": ("Curl biceps", "m"), "hammer curl": ("Curl marteau", "m"), "curl": ("Curl", "m"),
    "wrist curl": ("Curl poignets", "m"), "triceps extension": ("Extension des triceps", "f"),
    "kickback": ("Kickback triceps", "m"), "dip": ("Dips", "mp"), "bench dip": ("Dips sur banc", "mp"),
    "body weight dip": ("Dips", "mp"), "triceps pressdown": ("Extension des triceps à la poulie", "f"),
    "lateral raise": ("Élévation latérale", "f"), "front raise": ("Élévation frontale", "f"),
    "shrug": ("Haussement d'épaules", "m"), "flye": ("Écarté", "m"), "reverse flye": ("Oiseau", "m"),
    "farmers walk": ("Marche du fermier", "f"), "farmers carry": ("Marche du fermier", "f"),
    "burpee": ("Burpee", "m"), "jumping jacks": ("Jumping jacks", "mp"), "jump rope": ("Corde à sauter", "f"),
    "box jump": ("Saut sur box", "m"), "high box jump": ("Saut sur box haute", "m"),
    "lateral leap and hop": ("Bonds latéraux", "mp"), "split jacks": ("Jacks fendus", "mp"),
    "squat jacks": ("Squat jacks", "mp"), "high knees": ("Montées de genoux", "fp"),
    "butt kicks": ("Talons-fesses", "mp"), "depth jump": ("Saut en contrebas", "m"),
    "medicine ball slam": ("Slam au médecine-ball", "m"), "lateral slide": ("Glissade latérale", "f"),
    "ankle circles": ("Cercles de chevilles", "mp"),
    "ankle dorsiflexion with band": ("Flexion dorsale de cheville avec élastique", "f"),
    "arm circles": ("Cercles de bras", "mp"), "shoulder circles": ("Cercles d'épaules", "mp"),
    "forward and backward leg swings": ("Balancés de jambe avant-arrière", "mp"),
    "side to side leg swings": ("Balancés de jambe latéraux", "mp"),
    "walking high knees": ("Montées de genoux en marchant", "fp"),
    "walking high kicks": ("Jambes tendues en marchant", "fp"),
    "walking knee hugs": ("Genou à la poitrine en marchant", "m"), "cat camel": ("Chat-vache", "m"),
    "cat cow": ("Chat-vache", "m"), "thoracic rotation": ("Rotation thoracique", "f"),
    "neck rotations": ("Rotations du cou", "fp"), "neck tilts": ("Inclinaisons du cou", "fp"),
    "quadruped rocking": ("Bascule à quatre pattes", "f"), "walkout": ("Walkout", "m"),
    "stretch calf": ("Étirement des mollets", "m"), "stretch hamstring": ("Étirement des ischios", "m"),
    "standing hamstring stretch": ("Étirement des ischios debout", "m"), "glutes stretch": ("Étirement des fessiers", "m"),
    "stretch hip flexor and quad": ("Étirement des fléchisseurs de hanche et des quadriceps", "m"),
    "stretch lunging hip flexor": ("Étirement du psoas en fente", "m"), "stretch pigeon pose": ("Posture du pigeon", "f"),
    "stretch childs pose": ("Posture de l'enfant", "f"), "stretch cobra": ("Cobra", "m"),
    "stretch butterfly": ("Papillon", "m"), "stretch lying it band": ("Étirement de la bandelette ilio-tibiale", "m"),
    "stretch lying piriformis": ("Étirement du piriforme", "m"),
    "stretch lying knee to chest": ("Genou à la poitrine, allongé", "m"),
    "stretch lying spinal twist": ("Torsion du dos, allongé", "f"), "stretch 90 90": ("Étirement 90-90", "m"),
    "stretch front split": ("Grand écart facial", "m"), "stretch quad": ("Étirement des quadriceps", "m"),
    "stretch obliques": ("Étirement des obliques", "m"), "stretch pectoral": ("Étirement des pectoraux", "m"),
    "stretch neck": ("Étirement du cou", "m"), "stretch lat": ("Étirement des dorsaux", "m"),
    "stretch forearms": ("Étirement des avant-bras", "m"), "stretch abs": ("Étirement des abdominaux", "m"),
    # gainage, abdos, dos
    "side bend": ("Inclinaison latérale", "f"), "windmill": ("Moulin", "m"), "turkish get up": ("Turkish get-up", "m"),
    "half turkish get up": ("Demi turkish get-up", "m"), "ab wheel": ("Roue abdominale", "f"), "rollout": ("Rollout", "m"),
    "jackknife": ("Jackknife", "m"), "pike": ("Pike", "m"), "l sit": ("L-sit", "m"),
    "toes to elbows": ("Pieds aux coudes", "mp"), "knees to elbow": ("Genoux aux coudes", "mp"),
    "toes to bar": ("Pieds à la barre", "mp"), "the hundred": ("Hundred (Pilates)", "m"),
    "roll up": ("Roll-up (Pilates)", "m"), "teaser": ("Teaser (Pilates)", "m"), "the teaser": ("Teaser (Pilates)", "m"),
    "scissors": ("Ciseaux", "mp"), "criss cross": ("Criss-cross", "m"), "swimming": ("Nageur (Pilates)", "m"),
    "90 degree static hold": ("Gainage statique à 90°", "m"), "plank leg lift": ("Planche jambe levée", "f"),
    "cross crunch": ("Crunch croisé", "m"), "mcgill curl up": ("Curl-up de McGill", "m"), "curl up": ("Curl-up", "m"),
    "sit ups": ("Relevé de buste", "m"), "leg levers": ("Leviers de jambes", "mp"),
    "leg raises": ("Relevé de jambes", "m"), "knee raises": ("Relevé de genoux", "m"),
    "straight leg raise": ("Relevé de jambe tendue", "m"), "single leg raise": ("Relevé d'une jambe", "m"),
    "leg lowering drill": ("Descente de jambes contrôlée", "f"),
    "single leg lowering drill": ("Descente d'une jambe contrôlée", "f"), "leg drops": ("Descente de jambes", "f"),
    "spine extension": ("Extension du dos", "f"), "hyperextension": ("Hyperextension", "f"),
    "reverse hyperextension": ("Hyperextension inversée", "f"), "cobra": ("Cobra", "m"),
    "opposite arm and leg lift": ("Élévation bras et jambe opposés", "f"),
    "quadruped": ("Gainage à quatre pattes", "m"), "ab twist": ("Rotation du buste", "f"),
    # hanches, fessiers, jambes
    "leg circles": ("Cercles de jambe", "mp"), "leg lift": ("Élévation de jambe", "f"),
    "inner thigh lift": ("Adduction de hanche sur le côté", "f"),
    "inner thigh side lift": ("Adduction de hanche sur le côté", "f"),
    "inner thigh circles": ("Cercles de jambe en adduction", "mp"), "rear leg raise": ("Élévation de jambe arrière", "f"),
    "hip internal rotation": ("Rotation interne de hanche", "f"), "hip adduction": ("Adduction de hanche", "f"),
    "hip extension": ("Extension de hanche", "f"), "leg abduction": ("Abduction de jambe", "f"),
    "leg adduction": ("Adduction de jambe", "f"), "leg extension": ("Extension de jambe", "f"),
    "abduction stretch": ("Étirement des abducteurs", "m"), "forward lunge": ("Fente avant", "f"),
    "rear lunge": ("Fente arrière", "f"), "quarter squat": ("Quart de squat", "m"),
    "squat to press": ("Squat développé", "m"), "plyo squats": ("Squat pliométrique", "m"),
    "split jump": ("Fente sautée", "f"), "box jump overs": ("Sauts par-dessus la box", "mp"),
    "box jump overs over the box": ("Sauts par-dessus la box", "mp"), "knee strike": ("Coup de genou", "m"),
    "jumping jack": ("Jumping jack", "m"), "throw": ("Lancer", "m"), "throws": ("Lancer", "m"),
    # haut du corps, épaules
    "external rotation": ("Rotation externe", "f"), "internal rotation": ("Rotation interne", "f"),
    "shoulder external rotation": ("Rotation externe de l'épaule", "f"),
    "shoulder abduction": ("Abduction de l'épaule", "f"), "shoulder extension": ("Extension de l'épaule", "f"),
    "shoulder flexion to 90 degrees": ("Flexion de l'épaule à 90°", "f"), "pull apart": ("Écartement d'élastique", "m"),
    "latpull": ("Tirage vertical", "m"), "fly": ("Écarté", "m"), "side raise": ("Élévation latérale", "f"),
    "tricep extension": ("Extension des triceps", "f"), "tricep kickback": ("Kickback triceps", "m"),
    # échauffement, étirements, mobilité
    "stretch piriformis": ("Étirement du piriforme", "m"), "stretch side": ("Étirement latéral", "m"),
    "stretch side lunge": ("Étirement en fente latérale", "m"),
    "stretch standing it band": ("Étirement de la bandelette ilio-tibiale debout", "m"),
    "stretch triceps": ("Étirement des triceps", "m"), "triceps stretch": ("Étirement des triceps", "m"),
    "biceps stretch": ("Étirement des biceps", "m"), "stretch shoulder": ("Étirement de l'épaule", "m"),
    "stretch cat cow": ("Chat-vache", "m"), "stretch forward glutes": ("Étirement des fessiers", "m"),
    "stretch lunge with spinal twist": ("Fente avec torsion du buste", "f"),
    "stretch straddle": ("Étirement jambes écartées", "m"), "stretch side split": ("Grand écart latéral", "m"),
    "upper back stretch": ("Étirement du haut du dos", "m"), "ankle stretch": ("Étirement des chevilles", "m"),
    "marching in place": ("Marche sur place", "f"), "shoulder rolls": ("Rotations des épaules", "fp"),
    "chest openers": ("Ouverture de la poitrine", "f"), "groiners": ("Groiners", "mp"), "scorpion": ("Scorpion", "m"),
    "stretch scorpion": ("Scorpion", "m"), "ankle lunges": ("Fentes de mobilité de cheville", "fp"),
    "three way ankle mobilization": ("Mobilisation de cheville dans 3 directions", "f"),
    "ninety ninety hip switch": ("Bascule 90-90 des hanches", "f"), "active frog": ("Grenouille active", "f"),
    "walking leg cradles": ("Berceau de jambe en marchant", "m"),
    "inverted hamstring stretch": ("Étirement des ischios en équilibre", "m"),
    "walkout from push up position": ("Walkout depuis la position de pompe", "m"),
    "back roll foam roller": ("Rouleau de massage pour le dos", "m"),
    "latissimus dorsi foam roll": ("Rouleau de massage pour les dorsaux", "m"),
}

WEIGHTED = ("lesté", "lestée")
# Précisions : texte invariable, ou (masculin, féminin) accordé avec l'exercice ; rang = ordre d'écriture
MODIFIERS: dict[str, tuple[Any, int]] = {
    "alternating": (("alterné", "alternée"), 0), "reverse": (("inversé", "inversée"), 0),
    "lateral": (("latéral", "latérale"), 0), "side": (("latéral", "latérale"), 0),
    "isometric": ("statique", 0), "static": ("statique", 0), "hold": ("statique", 0),
    "jump": (("sauté", "sautée"), 0), "jumping": (("sauté", "sautée"), 0), "walking": (("marché", "marchée"), 0),
    "sliding": (("glissé", "glissée"), 0), "on sliding discs": (("glissé", "glissée"), 0),
    "incline": (("incliné", "inclinée"), 0), "decline": (("décliné", "déclinée"), 0),
    "explosive": (("explosif", "explosive"), 0), "partial": (("partiel", "partielle"), 0),
    "standing": ("debout", 1), "seated": ("assis", 1), "kneeling": ("à genoux", 1),
    "half kneeling": ("sur un genou", 1), "lying": ("allongé", 1), "side lying": ("allongé sur le côté", 1),
    "prone": ("sur le ventre", 1), "supine": ("sur le dos", 1), "bent over": ("buste penché", 1),
    "single leg": ("sur une jambe", 2), "one leg": ("sur une jambe", 2), "one legged": ("sur une jambe", 2),
    "single arm": ("à un bras", 2), "one arm": ("à un bras", 2),
    "bent knee": ("genoux fléchis", 3), "straight leg": ("jambes tendues", 3), "wide stance": ("jambes écartées", 3),
    "wide grip": ("prise large", 3), "close grip": ("prise serrée", 3), "neutral grip": ("prise neutre", 3),
    "reverse grip": ("prise inversée", 3), "underhand grip": ("prise en supination", 3),
    "overhand grip": ("prise en pronation", 3), "elevated feet": ("pieds surélevés", 3),
    "feet elevated": ("pieds surélevés", 3), "front foot elevated": ("pied avant surélevé", 3),
    "elevated front foot": ("pied avant surélevé", 3), "back foot elevated": ("pied arrière surélevé", 3),
    "overhead": ("bras au-dessus de la tête", 3), "3 way": ("dans 3 directions", 3),
    "body weight": ("au poids du corps", 3), "bench": ("sur banc", 3), "on bench": ("sur banc", 3),
    "with foot on bench": ("pied sur un banc", 3), "with feet on bench": ("pieds sur un banc", 3),
    "swiss ball": ("sur swiss ball", 3), "on swiss ball": ("sur swiss ball", 3),
    "on a swiss ball": ("sur swiss ball", 3), "with feet on swiss ball": ("pieds sur swiss ball", 3),
    "with feet on a swiss ball": ("pieds sur swiss ball", 3), "stability ball": ("sur swiss ball", 3),
    "bosu ball": ("sur Bosu", 3), "on bosu ball": ("sur Bosu", 3), "box": ("sur box", 3),
    "dumbbell": ("avec haltères", 4), "dumbbells": ("avec haltères", 4),
    "offset dumbbell": ("avec un haltère d'un côté", 4), "barbell": ("à la barre", 4), "ez bar": ("à la barre EZ", 4),
    "kettlebell": ("avec kettlebell", 4), "cable": ("à la poulie", 4), "band": ("avec élastique", 4),
    "banded": ("avec élastique", 4), "with band": ("avec élastique", 4), "resistance band": ("avec élastique", 4),
    "medicine ball": ("avec médecine-ball", 4), "with medicine ball": ("avec médecine-ball", 4),
    "smith machine": ("à la Smith machine", 4), "trx": ("au TRX", 4), "suspended": ("en suspension", 4),
    "with dumbbell": ("avec haltère", 4), "with dumbbells": ("avec haltères", 4), "with barbell": ("à la barre", 4),
    "with kettlebell": ("avec kettlebell", 4), "with rotation": ("avec rotation", 5), "and rotation": ("avec rotation", 5),
    "with twist": ("avec rotation", 5), "with reach": ("bras tendu", 5), "with arm reach": ("bras tendu", 5),
    "with reach back": ("bras vers l'arrière", 5), "with knee lift": ("avec montée de genou", 5),
    "with knee drive": ("avec montée de genou", 5), "to balance": ("avec équilibre", 5),
    "with leg lift": ("jambe levée", 5), "with arm raise": ("bras levé", 5), "with leg extension": ("jambe tendue", 5),
    "with static hold": ("avec maintien", 5), "with side bend": ("avec inclinaison latérale", 5),
    "with diagonal reach": ("bras en diagonale", 5),
    "extended": (("étendu", "étendue"), 0), "cross body": (("croisé", "croisée"), 0), "cross": (("croisé", "croisée"), 0),
    "double": ("double", 0), "modified": (("modifié", "modifiée"), 0), "negative": (("négatif", "négative"), 0),
    "full": (("complet", "complète"), 0), "low": (("bas", "basse"), 0), "high": (("haut", "haute"), 0),
    "elevated": (("surélevé", "surélevée"), 0), "plyometric": ("pliométrique", 0), "spiderman": ("Spiderman", 0),
    "hanging": (("suspendu", "suspendue"), 1), "quadruped": ("à quatre pattes", 1), "donkey": ("buste penché", 1),
    "straight arm": ("bras tendus", 3), "crossed arms": ("bras croisés", 3), "crossed arm": ("bras croisés", 3),
    "raised legs": ("jambes levées", 3), "cross leg": ("jambes croisées", 3), "two point": ("sur deux appuis", 3),
    "three way": ("dans 3 directions", 3), "45 degree": ("à 45°", 3), "on a bench": ("sur banc", 3),
    "on floor": ("au sol", 3), "with bench": ("dos sur un banc", 3), "staggered": ("pieds décalés", 3),
    "air": ("au poids du corps", 3), "balancing": ("en équilibre", 3), "zercher": ("Zercher", 3),
    "star": ("en étoile", 3), "onto box": ("sur une box", 3), "in and out": ("écart-serré", 3),
    "in n out": ("écart-serré", 3), "butterfly": ("en papillon", 3), "pilates": ("Pilates", 3), "front": ("avant", 3),
    "side to side": ("d'un côté à l'autre", 3), "with heels raised": ("talons surélevés", 3),
    "with knee squeeze": ("genoux serrés", 3), "with hands on bench": ("mains sur un banc", 3),
    "with hands on swiss ball": ("mains sur swiss ball", 3), "with feet on bosu ball": ("pieds sur Bosu", 3),
    "with foot on bosu ball": ("pied sur Bosu", 3), "with foot on foam roller": ("pied sur un rouleau", 3),
    "with foot on medicine ball": ("pied sur un médecine-ball", 3), "with head on bosu ball": ("tête sur Bosu", 3),
    "with head on swiss ball": ("tête sur swiss ball", 3), "with elbow on bosu ball": ("coude sur Bosu", 3),
    "ring": ("aux anneaux", 4), "ghd": ("au banc GHD", 4), "with ball": ("avec ballon", 4),
    "with body bar": ("avec barre légère", 4), "suitcase": ("en valise", 4),
    "lift": ("avec élévation", 5), "leg lifts": ("jambe levée", 5), "and hold": ("avec maintien", 5),
    "with knee to elbow": ("genou au coude", 5), "knee twist": ("avec rotation du genou", 5),
    "with oblique crunch": ("avec crunch oblique", 5), "with knee tuck": ("genou ramené", 5),
    "knee tucks": ("avec genoux ramenés", 5), "with knee circle": ("avec cercles du genou", 5),
    "with reach under": ("avec passage du bras dessous", 5), "with shoulder touch": ("avec touché d'épaule", 5),
    "with diagonal arm lift": ("bras levé en diagonale", 5), "with diagonal leg lift": ("jambe levée en diagonale", 5),
    "with opposite arm and leg lift": ("bras et jambe opposés levés", 5), "with leg pull": ("jambe levée", 5),
    "with opposite arm and leg reach": ("bras et jambe opposés tendus", 5), "and row": ("avec rowing", 5),
    "and press": ("avec développé", 5), "shifting": ("avec transfert", 5), "marching": ("en marchant", 5),
    "rolling": ("en roulant", 5), "cycling": ("avec pédalage", 5), "elbow to knee": ("coude au genou", 5),
    "in external rotation": ("en rotation externe", 5), "side kick": ("avec coup de pied latéral", 5),
    "weighted": (WEIGHTED, 6),
}


def _agree(word: Any, gender: str) -> str:
    if isinstance(word, str):
        return word
    text = word[1] if gender.startswith("f") else word[0]
    return text + "s" if gender.endswith("p") else text


def _translate(name: str) -> str | None:
    """« single_leg_standing_calf_raise » → « Élévation des mollets debout sur une jambe ».
    Rien (None) dès qu'un mot n'est pas connu : on ne devine pas."""
    words = name.split("_")
    weighted = words[0] == "weighted"
    if weighted:
        words = words[1:]
    best: tuple[int, int] | None = None
    for i in range(len(words)):
        for j in range(len(words), i, -1):
            if " ".join(words[i:j]) in BASES:
                if best is None or j - i > best[1] - best[0]:
                    best = (i, j)
                break
    if best is None:
        return None
    label, gender = BASES[" ".join(words[best[0]:best[1]])]
    found: list[tuple[int, str]] = []
    for part in (words[:best[0]], words[best[1]:]):
        k = 0
        while k < len(part):
            for size in range(min(6, len(part) - k), 0, -1):
                phrase = " ".join(part[k:k + size])
                if phrase in MODIFIERS:
                    word, rank = MODIFIERS[phrase]
                    text = _agree(word, gender)
                    if text not in label and all(text != t for _, t in found):
                        found.append((rank, text))
                    k += size
                    break
            else:
                return None
    found.sort(key=lambda item: item[0])
    text = " ".join([label] + [t for _, t in found])
    if weighted:
        text += " " + _agree(WEIGHTED, gender)
    return text


def _humanize(name: str) -> str:
    return name.replace("_", " ").strip()


def exercise_name(category: str | None, name: str | None) -> str:
    """Nom français d'un exercice ; à défaut, la catégorie suivie du nom de Garmin.
    Un exercice lu dans une description Strava garde le nom écrit (le plus souvent l'anglais des salles)."""
    category = (category or "unknown").lower()
    if category == "texte" and name:
        return name
    label = CATEGORIES.get(category, (_humanize(category).capitalize(), {}))[0]
    if not name:
        return label
    name = name.lower()
    translated = _translate(name)
    if translated:
        return translated
    return f"{label} ({_humanize(name)})"


def exercise_muscles(category: str | None, name: str | None) -> dict[str, float]:
    """Muscles travaillés : 1 = principal, 0,5 = secondaire."""
    category = (category or "unknown").lower()
    name = (name or "").lower()
    if category == "texte":
        return text_muscles(name)
    muscles: dict[str, float] | None = None
    for cat, pattern, values in OVERRIDES:
        if (cat == "*" or cat == category) and name and re.search(pattern, name):
            muscles = values
            break
    if muscles is None and category in GENERIC and name:
        for pattern, values in NAME_MUSCLES:
            if re.search(pattern, name):
                muscles = values
                break
    if muscles is None:
        muscles = CATEGORIES.get(category, ("", {}))[1]
    if category in LIGHT:
        muscles = {m: min(w, S) for m, w in muscles.items()}
    return dict(muscles)


# Exercice écrit en toutes lettres (description Strava) : mots-clés anglais et français → catégorie de Garmin,
# pour la carte des muscles. Le premier qui correspond l'emporte (« leg curl » avant « curl »).
TEXT_CATEGORIES: list[tuple[str, str]] = [
    (r"leg curl|hamstring curl|nordic|leg curl|curl (?:des )?ischio", "leg_curl"),
    (r"leg extension|extension (?:des )?quadri|leg press|presse à cuisses", "squat"),
    (r"calf|mollet", "calf_raise"),
    (r"bench|chest press|développé couché|developpe couche|dips?\b", "bench_press"),
    (r"incline press|développé incliné", "bench_press"),
    (r"overhead press|shoulder press|military|développé (?:militaire|épaules?|assis)|arnold", "shoulder_press"),
    (r"lateral raise|élévations? latérales?|front raise|élévations? frontales?", "lateral_raise"),
    (r"deadlift|soulevé de terre|souleve de terre|rdl|romanian", "deadlift"),
    (r"hip thrust|glute bridge|pont fessier|pont\b|bridge", "hip_raise"),
    (r"swing", "hip_swing"),
    (r"lunge|fente|split squat|bulgarian|step.?up", "lunge"),
    (r"squat|goblet|pistol", "squat"),
    (r"pull.?up|chin.?up|traction|lat pull|pulldown|tirage vertical", "pull_up"),
    (r"row|rowing|tirage", "row"),
    (r"push.?up|pompe", "push_up"),
    (r"fly|flye|écarté|ecarte|pec deck", "flye"),
    (r"skull|tricep|kickback|extension (?:des )?triceps|pushdown", "triceps_extension"),
    (r"curl", "curl"),
    (r"shrug|haussement", "shrug"),
    (r"face pull|band pull|rotation externe|external rotation|y.?raise", "shoulder_stability"),
    (r"plank|planche|gainage|hollow|dead bug", "plank"),
    (r"crunch|sit.?up|relevé de buste|abdo", "crunch"),
    (r"leg raise|relevé de jambes|knee raise", "leg_raise"),
    (r"russian twist|oblique|woodchop|bûcheron", "chop"),
    (r"back extension|hyperextension|good morning|lombaire|superman", "hyperextension"),
    (r"farmer|carry|marche du fermier", "carry"),
    (r"burpee|jump|saut|box|plyo|bond", "plyo"),
    (r"clean|snatch|épaulé|arraché|jerk", "olympic_lift"),
    (r"abduct|clamshell|monster walk|band walk", "hip_stability"),
    (r"rope|corde", "battle_rope"),
    (r"rameur|rower|ergo", "indoor_row"),
]


def text_category(name: str) -> str | None:
    """Catégorie de Garmin d'un exercice écrit en toutes lettres (anglais ou français) ; None s'il n'est pas reconnu."""
    low = (name or "").lower()
    return next((category for pattern, category in TEXT_CATEGORIES if re.search(pattern, low)), None)


def text_muscles(name: str) -> dict[str, float]:
    """Muscles d'un exercice écrit en toutes lettres (anglais ou français) ; rien s'il n'est pas reconnu."""
    category = text_category(name)
    return dict(CATEGORIES[category][1]) if category else {}


# ----------------------------------------------------- équilibre avant / arrière
# Chaîne antérieure contre chaîne postérieure, en séries : le repère des préparateurs physiques est 1:1
# (une série de tirage pour une série de poussée, une de soulevé de terre roumain pour une de squat),
# et jusqu'à 1:2 en faveur de l'arrière pour un coureur. Chaque exercice est rangé par son mouvement
# (une famille), d'après sa catégorie et son nom chez Garmin, ou ce qui est écrit dans la description Strava.
CHAIN_FAMILIES: dict[str, tuple[str, str, str, str]] = {  # clé → (nom, chaîne, exemples, nom court)
    "genou": ("Dominante genou", "avant", "squats, fentes, step-up, chaise", "genou"),
    "poussee": ("Poussée", "avant", "pompes, développés, élévations", "poussée"),
    "abdos": ("Abdos et gainage", "avant", "planche, crunchs, relevés de jambes", "abdos"),
    "biceps": ("Biceps", "avant", "curls", "biceps"),
    "releveurs": ("Releveurs du pied", "avant", "élévations des orteils", "releveurs"),
    "hanche": ("Dominante hanche", "arriere", "soulevé de terre roumain, hip thrust, pont, leg curl, swing", "hanche"),
    "tirage": ("Tirage", "arriere", "rowing, tractions, oiseau, face pull", "tirage"),
    "lombaires": ("Lombaires", "arriere", "superman, extensions lombaires, bird dog", "lombaires"),
    "triceps": ("Triceps", "arriere", "dips, extensions des triceps", "triceps"),
    "mollets": ("Mollets", "arriere", "élévations des mollets", "mollets"),
    "mixte": ("Corps entier", "mixte", "burpees, portés, haltérophilie", "corps entier"),
    "lateral": ("Latéral et rotation", "neutre", "planche latérale, bonds latéraux, abduction, rotations", "latéral"),
}
CHAIN_LABELS = {"avant": "Avant", "arriere": "Arrière", "mixte": "Corps entier", "neutre": "Latéral"}
# Les paires du repère 1:1, de la plus importante pour un coureur à la moins importante :
# (clé, nom, famille avant, famille arrière, à ajouter derrière, à ajouter devant)
CHAIN_PAIRS: list[tuple[str, str, str, str, str, str]] = [
    ("bas", "Bas du corps", "genou", "hanche", "du soulevé de terre roumain, du hip thrust ou du leg curl",
     "des squats, des fentes ou des step-up"),
    ("haut", "Haut du corps", "poussee", "tirage", "du rowing, des tractions ou de l'oiseau",
     "des pompes ou du développé"),
    ("tronc", "Tronc", "abdos", "lombaires", "du superman, des extensions lombaires ou du bird dog",
     "de la planche ou des crunchs"),
    ("bras", "Bras", "biceps", "triceps", "des dips ou des extensions des triceps", "des curls"),
    ("jambe", "Bas de jambe", "releveurs", "mollets", "des élévations des mollets",
     "des élévations des orteils (releveurs, contre les périostites)"),
]
# Pas du renforcement de l'avant ou de l'arrière : échauffement, mobilité, cardio, exercice non précisé
CHAIN_SKIP = LIGHT | {"unknown", "cardio", "run", "run_indoor", "bike", "bike_outdoor", "indoor_bike", "elliptical",
                      "floor_climb", "indoor_row", "ladder", "stair_stepper", "battle_rope"}
CHAIN_CATEGORY: dict[str, str] = {  # famille par défaut de chaque catégorie de Garmin
    "bench_press": "poussee", "push_up": "poussee", "shoulder_press": "poussee", "flye": "poussee",
    "lateral_raise": "poussee", "squat": "genou", "lunge": "genou", "plyo": "genou", "sled": "genou",
    "core": "abdos", "crunch": "abdos", "sit_up": "abdos", "plank": "abdos", "leg_raise": "abdos",
    "curl": "biceps", "pull_up": "tirage", "row": "tirage", "shrug": "tirage", "shoulder_stability": "tirage",
    "deadlift": "hanche", "hip_raise": "hanche", "hip_swing": "hanche", "leg_curl": "hanche",
    "olympic_lift": "hanche", "tire": "hanche", "hyperextension": "lombaires", "triceps_extension": "triceps",
    "calf_raise": "mollets", "total_body": "mixte", "carry": "mixte", "sandbag": "mixte", "chop": "lateral",
    "hip_stability": "lateral", "sledge_hammer": "lateral",
}
# Le nom de l'exercice l'emporte sur sa catégorie : (catégorie ou « * », motif sur le nom simplifié — minuscules
# sans accents, mots séparés par « _ » et encadrés par « _ » —, famille ou None pour « pas compté »).
# Le premier qui correspond l'emporte : l'arrière de l'épaule avant les élévations, le latéral avant la planche…
CHAIN_RULES: list[tuple[str, str, str | None]] = [
    # écrit à la main dans Strava : du cardio, pas du renforcement
    ("texte", r"jump_rope|corde_a_sauter|jumping_jacks?_|_jacks_|rameur|elliptique|_velo_|footing|tapis_de_course"
              r"|course_a_pied", None),
    # l'épaule : l'arrière (rotation externe, oiseau, face pull…), puis l'avant (élévations, rotation interne) ;
    # pas les rotations de hanche
    ("*", r"^(?!.*_(?:hip|leg|hanche)_).*(?:external_rotation|rotations?_externes?|face_pull|pull_apart|reverse_fly"
          r"|rear_delt|rear_fly|bent_over_lateral|_[ytw]_raise|_[ytw]_fly|scapula|oiseau|band_pull|shoulder_extension)",
     "tirage"),
    ("*", r"^(?!.*_(?:hip|leg|hanche)_).*(?:lateral_raise|side_raise|front_raise|elevations?_laterales?"
          r"|elevations?_frontales?|internal_rotation|shoulder_abduction|shoulder_flexion)", "poussee"),
    ("push_up", r"_row_", "mixte"),  # pompe et rowing
    ("push_up", r".", "poussee"),
    ("total_body", r".", "mixte"),
    ("olympic_lift", r"clean.*(?:jerk|press)", "mixte"),
    ("olympic_lift", r"jerk|press", "poussee"),
    ("olympic_lift", r"clean|snatch|pull|deadlift|swing", "hanche"),
    # latéral et rotation : ni devant ni derrière
    ("*", r"side_plank|planche_laterale|copenhag|side_bend|windmill|russian_twist|rotation_russe|oblique|wood_?chop"
          r"|bucheron|pallof|core_press|_chop_|hip_drop|lateral_(?:leap|hop|plyo|slide|walk|band|step|lunge|shuffle"
          r"|bound|jump|swing)|side_(?:lunge|step|shuffle|to_side|lying_leg|kick|lying_hip)|shuffle|skater|abduct"
          r"|adduct|clam|fire_hydrant|inner_thigh|monster_walk|band_walk|pas_chasses?|fentes?_laterales?"
          r"|bonds?_lateraux|lateraux|_rotations?_du_buste|hip_(?:internal_|external_)?rotation", "lateral"),
    ("hip_raise", r"leg_circles|leg_lift", "lateral"),
    ("crunch", r".", "abdos"),
    ("sit_up", r".", "abdos"),
    # puis le mouvement, d'où qu'il vienne
    ("*", r"swing|leg_curl|hamstring|ischio|nordic|good_morning|deadlift|souleve_de_terre|_rdl_|hip_thrust|hip_press"
          r"|glute|fessier|bridge|_pont_|hip_raise|hip_extension|donkey_kick|rear_leg_(?:raise|extension)"
          r"|reverse_hyper|pull_through", "hanche"),
    ("*", r"tricep|_dips?_|skull", "triceps"),
    ("*", r"calf|mollet|heel_raise", "mollets"),
    ("*", r"toe_raise|tibialis|releveur|orteils", "releveurs"),
    ("*", r"superman|back_extension|hyperextension|extensions?_lombaires?|lombaire|bird_dog|opposite_arm_and_leg"
          r"|arm_and_leg_extension|reverse_plank|planche_inversee|swimming|nageur", "lombaires"),
    ("*", r"burpee|turkish_get_up|man_maker|squat_thrust|sprawl|farmer|_carry_|marche_du_fermier", "mixte"),
    ("plyo", r"medicine_ball|throw|slam", "mixte"),
    ("*", r"dead_?bug|hollow|crunch|sit_?ups?_|curl_up|v_up|leg_raise|knee_raise|knee_to_chest|knee_tuck"
          r"|releves?_de_(?:jambes|genoux|buste)|toes_to_bar|mountain_climber|bear_crawl|ab_wheel|rollout|jackknife"
          r"|l_sit|knee_strike|plank|planche|gainage|abdo", "abdos"),
    ("*", r"squat|lunge|fentes?_|step_?up|leg_press|presse|leg_extension|wall_sit|chaise|pistol|thruster|wall_ball",
     "genou"),
    ("*", r"pull_?ups?_|chin_?ups?_|traction|pull_?down|lat_?pull|_row|rowing|tirage|shrug|haussement", "tirage"),
    ("*", r"push_?ups?_|pompe|bench_press|chest_press|developpe|_press_|_fly_|flye|ecarte", "poussee"),
    ("*", r"curl|biceps", "biceps"),
]
# Pour un exercice que rien d'autre ne range : la famille de ses muscles principaux
MUSCLE_FAMILY = {
    "pectoraux": "poussee", "epaules": "poussee", "biceps": "biceps", "abdos": "abdos", "quadriceps": "genou",
    "triceps": "triceps", "trapezes": "tirage", "dorsaux": "tirage", "lombaires": "lombaires",
    "fessiers": "hanche", "ischios": "hanche", "mollets": "mollets", "obliques": "lateral",
    "abducteurs": "lateral", "adducteurs": "lateral",
}


def _simple(text: str) -> str:
    """« Soulevé de terre (roumain) » → « souleve_de_terre_roumain »."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", plain).strip("_")


def _family_from_muscles(muscles: dict[str, float]) -> str | None:
    families = [MUSCLE_FAMILY[m] for m, w in muscles.items() if w >= P and m in MUSCLE_FAMILY]
    chains = {CHAIN_FAMILIES[f][1] for f in families}
    if not families:
        return None
    if {"avant", "arriere"} <= chains:
        return "mixte"
    return next((f for f in families if CHAIN_FAMILIES[f][1] != "neutre"), families[0])


def chain_family(category: str | None, name: str | None) -> str | None:
    """Famille de mouvement d'un exercice (« genou », « hanche », « lateral »…) ; None s'il ne compte pas dans
    l'équilibre (échauffement, cardio, exercice non précisé ou pas reconnu)."""
    category = (category or "unknown").lower()
    if category in CHAIN_SKIP:
        return None
    key = _simple(name or "")
    if key:
        padded = f"_{key}_"
        for cat, pattern, family in CHAIN_RULES:
            if (cat == "*" or cat == category) and re.search(pattern, padded):
                return family
    if category == "texte":
        category = text_category(name or "") or "unknown"
        if category in CHAIN_SKIP:
            return None
    if category in CHAIN_CATEGORY:
        return CHAIN_CATEGORY[category]
    return _family_from_muscles(exercise_muscles(category, name))


def chain_info(category: str | None, name: str | None) -> dict | None:
    """La famille d'un exercice telle que l'interface la montre ; None s'il ne compte pas."""
    family = chain_family(category, name)
    if family is None:
        return None
    label, chain, _, _ = CHAIN_FAMILIES[family]
    return {"famille": family, "nom": label, "chaine": chain, "chaine_nom": CHAIN_LABELS[chain]}


def _number(value: float) -> str:
    """12 → « 12 », 12.5 → « 12,5 »."""
    value = round(value, 1)
    return str(int(value)) if value == int(value) else f"{value:.1f}".replace(".", ",")


def ratio_text(ratio: float | None) -> str:
    """Le rapport « avant : arrière » comme les préparateurs l'écrivent : « 1 : 1,5 », « 1 : 0,75 »."""
    if ratio is None:
        return "tout à l'arrière"
    shown = (f"{ratio:.2f}" if ratio < 1 else f"{ratio:.1f}").rstrip("0").rstrip(".")
    return "1 : " + shown.replace(".", ",")


BALANCE_ZONES: dict[str, tuple[str, str]] = {  # zone → (verdict, explication)
    "avant": ("Trop d'avant", "Plus de séries devant que derrière : la chaîne postérieure (fessiers, ischios, "
                              "dos, mollets) est en retard."),
    "proche": ("Presque à l'équilibre", "Un peu plus de séries devant que derrière : encore quelques séries "
                                        "côté arrière pour atteindre 1:1."),
    "cible": ("Dans la cible", "Entre 1:1 et 1:2 : l'équilibre conseillé pour un coureur, un peu plus de travail "
                               "derrière que devant."),
    "arriere": ("Très orienté arrière", "Au-delà de 1:2 : ne laisse pas tomber l'avant (quadriceps, gainage), utile "
                                        "en descente et pour tenir le bassin."),
    "arriere_fort": ("Presque tout à l'arrière", "Presque rien devant : quadriceps et gainage ont aussi leur place, "
                                                 "même pour un coureur."),
    "vide": ("Rien à comparer", "Aucune série rangée devant ou derrière : échauffement, cardio, latéral ou exercice "
                                "non précisé."),
}


def balance_zone(front: float, back: float) -> tuple[str, float | None]:
    """Zone du rapport arrière / avant (arrondi comme il s'affiche, pour que l'affichage et la zone concordent)."""
    if front <= 0:
        return ("arriere_fort" if back > 0 else "vide"), None
    ratio = back / front
    ratio = round(ratio, 2) if ratio < 1 else round(ratio, 1)
    if ratio < 0.8:
        return "avant", ratio
    if ratio < 1:
        return "proche", ratio
    if ratio <= 2:
        return "cible", ratio
    return ("arriere" if ratio <= 4 else "arriere_fort"), ratio


def _lean(front: float, back: float) -> str:
    zone, _ = balance_zone(front, back)
    return {"avant": "avant", "proche": "equilibre", "cible": "equilibre", "vide": "equilibre"}.get(zone, "arriere")


def balance(rows: list[dict]) -> dict:
    """Équilibre avant / arrière d'un ensemble d'exercices, en séries (« corps entier » : ½ de chaque côté ;
    latéral et rotation : à part, ni devant ni derrière)."""
    per_family: dict[str, float] = defaultdict(float)
    skipped = 0.0
    for e in rows:
        family = chain_family(e["category"], e["name"])
        if family is None:
            skipped += e["sets"]
        else:
            per_family[family] += e["sets"]
    mixed = per_family.get("mixte", 0.0)

    def side(chain: str) -> float:
        return sum(v for f, v in per_family.items() if CHAIN_FAMILIES[f][1] == chain) + mixed / 2

    front, back = side("avant"), side("arriere")
    zone, ratio = balance_zone(front, back)
    verdict, explanation = BALANCE_ZONES[zone]
    total = front + back
    pairs = []
    for key, label, fam_front, fam_back, add_back, add_front in CHAIN_PAIRS:
        a, b = per_family.get(fam_front, 0.0), per_family.get(fam_back, 0.0)
        if not a and not b:
            continue
        pair_zone, pair_ratio = balance_zone(a, b)
        enough = a + b >= max(3.0, 0.1 * total)  # assez de séries pour juger de la paire
        pairs.append({
            "cle": key, "nom": label,
            "avant": {"famille": fam_front, "nom": CHAIN_FAMILIES[fam_front][0], "court": CHAIN_FAMILIES[fam_front][3],
                      "series": round(a, 1)},
            "arriere": {"famille": fam_back, "nom": CHAIN_FAMILIES[fam_back][0], "court": CHAIN_FAMILIES[fam_back][3],
                        "series": round(b, 1)},
            "ratio": pair_ratio, "ratio_texte": ratio_text(pair_ratio) if a else None,
            "penche": _lean(a, b) if enough else None,
            "ajouter_arriere": add_back, "ajouter_avant": add_front, "_zone": pair_zone,
        })
    advice = _balance_advice(zone, pairs)
    short = _balance_advice(zone, pairs, short=True)
    for p in pairs:
        p.pop("_zone")
    families = [{"cle": f, "nom": CHAIN_FAMILIES[f][0], "chaine": CHAIN_FAMILIES[f][1],
                 "exemples": CHAIN_FAMILIES[f][2], "series": round(v, 1)}
                for f, v in sorted(per_family.items(), key=lambda kv: -kv[1]) if v]
    return {
        "avant": round(front, 1), "arriere": round(back, 1),
        "ratio": ratio, "ratio_texte": ratio_text(ratio) if zone != "vide" else None,
        "part_arriere": round(back / total, 3) if total else None,
        "zone": zone, "verdict": verdict, "explication": explanation, "conseil": advice,
        "conseil_court": short,  # sans les chiffres des paires, quand elles sont dessinées à côté
        "paires": pairs, "familles": families,
        "mixte": round(mixed, 1), "neutre": round(per_family.get("lateral", 0.0), 1), "non_comptees": round(skipped, 1),
    }


PAIR_WORDS = {  # paire → (sujet, verbe, séries devant, séries derrière)
    "bas": ("le bas du corps", "penche", "côté genou", "côté hanche"),
    "haut": ("le haut du corps", "penche", "de poussée", "de tirage"),
    "tronc": ("le tronc", "penche", "d'abdos", "de lombaires"),
    "bras": ("les bras", "penchent", "de biceps", "de triceps"),
    "jambe": ("le bas de jambe", "penche", "de releveurs", "de mollets"),
}


def _pair_phrase(pair: dict) -> str:
    """« 32 séries côté genou pour 24 côté hanche », « 10 séries d'abdos, aucune de lombaires »."""
    _, _, front_word, back_word = PAIR_WORDS[pair["cle"]]
    a, b = pair["avant"]["series"], pair["arriere"]["series"]
    front = f"{_number(a)} série{'s' if a >= 2 else ''} {front_word}"
    return f"{front} pour {_number(b)} {back_word}" if b else f"{front}, aucune {back_word}"


def _balance_advice(zone: str, pairs: list[dict], short: bool = False) -> str | None:
    """Ce qu'il y a à faire, paire par paire (le bas du corps d'abord : c'est lui qui compte le plus en course).
    ``short`` : sans les séries de chaque paire (la tuile les dessine juste à côté)."""
    if zone == "vide":
        return None
    forward = [p for p in pairs if p["penche"] == "avant"][:2]
    if forward:
        first = forward[0]
        subject, verb, _, _ = PAIR_WORDS[first["cle"]]
        if short:
            subjects = " et ".join(PAIR_WORDS[p["cle"]][0] for p in forward)
            text = f"{subjects} {verb if len(forward) == 1 else 'penchent'} vers l'avant"
        else:
            text = f"{subject} {verb} vers l'avant ({_pair_phrase(first)})"
            if len(forward) > 1:
                text += f", {PAIR_WORDS[forward[1]['cle']][0]} aussi ({_pair_phrase(forward[1])})"
        text = f"Bon équilibre d'ensemble, mais {text}" if zone == "cible" else text[0].upper() + text[1:]
        add = ", et ".join(p["ajouter_arriere"] for p in forward)
        return f"{text} : ajoute {add}." if short else f"{text}. Ajoute {add}."
    if zone in ("avant", "proche"):
        biggest = max(pairs, key=lambda p: p["avant"]["series"] - p["arriere"]["series"], default=None)
        if biggest and biggest["avant"]["series"] > biggest["arriere"]["series"]:
            return f"Ajoute des séries côté arrière, par exemple {biggest['ajouter_arriere']}."
        return "Ajoute quelques séries côté arrière : tirage, soulevé de terre roumain, hip thrust."
    if zone in ("arriere", "arriere_fort"):
        light = [p for p in pairs if p["cle"] in ("bas", "tronc") and p["avant"]["series"] < p["arriere"]["series"]]
        hint = ", et ".join(p["ajouter_avant"] for p in light[:2]) or "des squats, des fentes ou de la planche"
        return f"Garde aussi un peu d'avant : {hint}."
    return "Rien à corriger : continue comme ça."


# ------------------------------------------------------------------ stockage
def parse_summary(item: dict) -> list[dict]:
    """Résumé d'une séance par exercice (« summarizedExerciseSets » de Garmin), dans l'ordre reçu."""
    entries = item.get("summarizedExerciseSets") if isinstance(item, dict) else None
    if not isinstance(entries, list):
        return []
    out = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        def number(key: str, factor: float = 1.0) -> float:
            value = entry.get(key)
            try:
                value = float(value) * factor
            except (TypeError, ValueError):
                return 0.0
            return value if value == value and value > 0 else 0.0

        sets = int(number("sets"))
        if sets <= 0:
            continue
        category = str(entry.get("category") or "unknown").strip().lower() or "unknown"
        name = str(entry.get("subCategory") or "").strip().lower() or None
        out.append({
            "category": category, "name": name, "sets": sets, "reps": int(number("reps")),
            "duration_s": round(number("duration", 0.001), 1), "max_kg": round(number("maxWeight", 0.001), 2),
            "volume_kg": round(number("volume", 0.001), 1),
        })
    return out


def totals(exercises: list[dict]) -> dict[str, float]:
    """Séries, répétitions, tonnage et temps d'effort d'une séance (valeurs « extra » de la séance)."""
    if not exercises:
        return {}
    return {
        "sets": sum(e["sets"] for e in exercises),
        "reps": sum(e["reps"] for e in exercises),
        "volume": round(sum(e["volume_kg"] for e in exercises), 1),
        "sets_effort": round(sum(e["duration_s"] for e in exercises)),
    }


def store_exercises(conn: sqlite3.Connection, activity_id: str, item: dict) -> int:
    """Range les exercices d'une séance déjà enregistrée (remplace ceux d'avant : Garmin Connect a pu être
    corrigé, jusqu'au type d'activité). Rien pour une séance hors ``SPORTS``."""
    conn.execute("DELETE FROM exercises WHERE activity_id = ?", (activity_id,))
    row = conn.execute("SELECT sport FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row or row["sport"] not in SPORTS:
        return 0
    exercises = parse_summary(item)
    for idx, e in enumerate(exercises):
        conn.execute(
            "INSERT INTO exercises(activity_id, idx, category, name, sets, reps, duration_s, max_kg, volume_kg) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (activity_id, idx, e["category"], e["name"], e["sets"], e["reps"], e["duration_s"], e["max_kg"],
             e["volume_kg"]),
        )
    return len(exercises)


def rebuild(conn: sqlite3.Connection) -> int:
    """Relit les exercices de toutes les séances gardées en brut (migration, « foulee reparse »)."""
    count = 0
    for row in conn.execute(
        "SELECT a.id, r.payload FROM raw r JOIN activities a ON a.source = r.source AND a.source_id = r.key "
        "WHERE r.source = 'garmin' AND r.kind = 'activity' AND r.payload LIKE '%summarizedExerciseSets%'"
    ).fetchall():
        try:
            item = json.loads(row["payload"])
        except ValueError:
            continue
        count += 1 if store_exercises(conn, row["id"], item) else 0
    return count


# ------------------------------------------------------------------ lecture
def _key(category: str, name: str | None) -> str:
    return f"{category}/{(name or '').lower() if category == 'texte' else name or ''}"


def _per_set(e: dict) -> dict:
    """Ce qu'on lit d'un coup d'œil : « 4 × 8 », « 4 × 30 s », « 32 répétitions en 3 séries »."""
    sets, reps, duration = e["sets"], e["reps"], e["duration_s"]
    timed = reps <= sets and duration / max(sets, 1) >= 10
    if timed:
        return {"mode": "temps", "par_serie_s": round(duration / sets), "texte": None}
    if reps and reps % sets == 0:
        return {"mode": "reps", "par_serie": reps // sets, "texte": None}
    return {"mode": "reps", "par_serie": None, "texte": f"{reps} répétitions"} if reps else {"mode": "aucun"}


def describe(e: dict) -> dict:
    """Un exercice tel que l'interface et Claude le montrent."""
    muscles = exercise_muscles(e["category"], e["name"])
    return {
        "cle": _key(e["category"], e["name"]),
        "inconnu": e["category"] == "unknown",  # exercice pas choisi sur la montre (ni reconnu par elle)
        "nom": exercise_name(e["category"], e["name"]),
        "nom_garmin": e["name"] or e["category"],
        "categorie": CATEGORIES.get(e["category"], (e["category"], {}))[0],
        "series": e["sets"], "repetitions": e["reps"], "duree_s": e["duration_s"],
        "charge_max_kg": e["max_kg"] or None, "tonnage_kg": e["volume_kg"] or None,
        "detail": _per_set(e),
        "muscles": [{"cle": m, "nom": MUSCLE_LABELS[m], "role": "principal" if w >= P else "secondaire"}
                    for m, w in sorted(muscles.items(), key=lambda kv: -kv[1])],
        "chaine": chain_info(e["category"], e["name"]),  # avant, arrière, corps entier, latéral (ou None)
    }


def _muscle_load(rows: list[dict]) -> dict[str, float]:
    """Séries par muscle (1 par série sur un muscle principal, ½ sur un secondaire)."""
    load: dict[str, float] = defaultdict(float)
    for e in rows:
        for muscle, weight in exercise_muscles(e["category"], e["name"]).items():
            load[muscle] += e["sets"] * weight
    return {m: round(load[m], 1) for m, _ in MUSCLES if load.get(m)}


def _rows(conn: sqlite3.Connection, where: str, params: list[Any]) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT e.*, a.date, a.start_local, a.name AS seance, a.id AS seance_id FROM exercises e "
        f"JOIN activities a ON a.id = e.activity_id WHERE {where} ORDER BY a.start_local, e.idx", params)]


def session(conn: sqlite3.Connection, activity_id: str) -> dict | None:
    """Exercices d'une séance, muscles travaillés et totaux ; None si ce n'est pas une séance de renfo."""
    row = conn.execute("SELECT sport FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if not row or row["sport"] not in SPORTS:
        return None
    rows = _rows(conn, "e.activity_id = ?", [activity_id])
    if not rows and row["sport"] != "renfo":
        return None
    return {
        "exercices": [describe(e) for e in rows],
        "muscles": _muscle_load(rows),
        "series": sum(e["sets"] for e in rows),
        "repetitions": sum(e["reps"] for e in rows),
        "tonnage_kg": round(sum(e["volume_kg"] for e in rows), 1) or None,
        "effort_s": round(sum(e["duration_s"] for e in rows)) or None,
        "equilibre": balance(rows),
        "noms_muscles": MUSCLE_LABELS,
    }


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def period(conn: sqlite3.Connection, start: date, end: date, weeks: int = 12) -> dict:
    """Bilan du renfo sur une période : séances, muscles, exercices (avec leur progression), et la
    régularité des dernières semaines (quelle que soit la période)."""
    rows = _rows(conn, "a.date BETWEEN ? AND ?", [start.isoformat(), end.isoformat()])
    sessions = conn.execute(
        "SELECT a.id, a.date, a.start_local, a.name, a.duration_s FROM activities a "
        "WHERE a.date BETWEEN ? AND ? AND (a.sport = 'renfo' OR EXISTS (SELECT 1 FROM exercises e "
        "WHERE e.activity_id = a.id)) ORDER BY a.start_local DESC", (start.isoformat(), end.isoformat()),
    ).fetchall()
    by_session: dict[str, list[dict]] = defaultdict(list)
    for e in rows:
        by_session[e["activity_id"]].append(e)
    listed = []
    for s in sessions:
        items = by_session.get(s["id"], [])
        listed.append({
            "id": s["id"], "date": s["date"], "debut": s["start_local"], "nom": s["name"], "duree_s": s["duration_s"],
            "exercices": len(items), "series": sum(e["sets"] for e in items),
            "tonnage_kg": round(sum(e["volume_kg"] for e in items), 1) or None,
            "muscles": _muscle_load(items),
        })

    groups: dict[str, list[dict]] = defaultdict(list)
    for e in rows:
        groups[_key(e["category"], e["name"])].append(e)
    exercises = []
    for key, items in groups.items():
        first = items[0]
        info = describe({**first, "sets": sum(i["sets"] for i in items), "reps": sum(i["reps"] for i in items),
                         "duration_s": sum(i["duration_s"] for i in items),
                         "max_kg": max(i["max_kg"] for i in items),
                         "volume_kg": round(sum(i["volume_kg"] for i in items), 1)})
        history = []
        for i in items:
            detail = _per_set(i)
            history.append({
                "date": i["date"], "seance_id": i["activity_id"], "series": i["sets"], "repetitions": i["reps"],
                "charge_kg": i["max_kg"] or None, "tonnage_kg": i["volume_kg"] or None,
                "par_serie": detail.get("par_serie"), "par_serie_s": detail.get("par_serie_s"),
            })
        info.update({
            "seances": len({i["activity_id"] for i in items}),
            "derniere": items[-1]["date"],
            "historique": history,
        })
        exercises.append(info)
    exercises.sort(key=lambda x: (x["inconnu"], -x["seances"], -x["series"], x["nom"]))  # non précisés en dernier

    # Régularité : séances de renfo par semaine (lundi → dimanche), les dernières semaines jusqu'à « end »
    last = _week_start(end)
    first_week = last - timedelta(weeks=weeks - 1)
    counts: dict[date, dict[str, float]] = {first_week + timedelta(weeks=k): {"seances": 0, "series": 0}
                                            for k in range(weeks)}
    for r in conn.execute(
        "SELECT a.date, (SELECT COALESCE(SUM(e.sets), 0) FROM exercises e WHERE e.activity_id = a.id) AS sets "
        "FROM activities a WHERE a.date BETWEEN ? AND ? AND (a.sport = 'renfo' OR EXISTS "
        "(SELECT 1 FROM exercises e WHERE e.activity_id = a.id))",
        (first_week.isoformat(), (last + timedelta(days=6)).isoformat()),
    ):
        week = _week_start(date.fromisoformat(r["date"]))
        if week in counts:
            counts[week]["seances"] += 1
            counts[week]["series"] += r["sets"] or 0
    # Équilibre avant / arrière semaine par semaine, sur les mêmes semaines
    by_week: dict[date, list[dict]] = defaultdict(list)
    for e in _rows(conn, "a.date BETWEEN ? AND ?", [first_week.isoformat(), (last + timedelta(days=6)).isoformat()]):
        by_week[_week_start(date.fromisoformat(e["date"]))].append(e)

    def week_balance(week: date) -> dict | None:
        if not by_week.get(week):
            return None
        b = balance(by_week[week])
        return {k: b[k] for k in ("avant", "arriere", "ratio", "ratio_texte", "part_arriere", "zone", "verdict")}

    return {
        "debut": start.isoformat(), "fin": end.isoformat(),
        "seances": listed,
        "nb_seances": len(listed),
        "series": sum(s["series"] for s in listed),
        "repetitions": sum(e["reps"] for e in rows),
        "tonnage_kg": round(sum(e["volume_kg"] for e in rows), 1) or None,
        "effort_s": round(sum(e["duration_s"] for e in rows)) or None,
        "muscles": _muscle_load(rows),
        "exercices": exercises,
        "equilibre": balance(rows),
        "semaines": [{"debut": k.isoformat(), "seances": int(v["seances"]), "series": int(v["series"]),
                      "equilibre": week_balance(k)} for k, v in sorted(counts.items())],
        "noms_muscles": MUSCLE_LABELS,
    }


def has_any(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM exercises LIMIT 1").fetchone() is not None
