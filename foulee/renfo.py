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


def text_muscles(name: str) -> dict[str, float]:
    """Muscles d'un exercice écrit en toutes lettres (anglais ou français) ; rien s'il n'est pas reconnu."""
    low = (name or "").lower()
    for pattern, category in TEXT_CATEGORIES:
        if re.search(pattern, low):
            return dict(CATEGORIES[category][1])
    return {}


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
        "semaines": [{"debut": k.isoformat(), "seances": int(v["seances"]), "series": int(v["series"])}
                     for k, v in sorted(counts.items())],
        "noms_muscles": MUSCLE_LABELS,
    }


def has_any(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM exercises LIMIT 1").fetchone() is not None
