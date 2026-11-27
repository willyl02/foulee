"""Partie 3 — Foulée au quotidien (les vues) et Partie 4 — Le renfo.

Captures « v-… » : la session de William, 27 novembre 2026 (photo de profil, coordonnées du président, n° de licence
et départ / arrivée des tracés floutés). Les pastilles se placent en pixels de l'image.
"""
from kit import box, chip, code, fr, howto, icon, legend, note, row, shot, ul


def part3(D):
    D.part("Foulée au quotidien", "Chaque vue répond à une question : comment je suis ce matin, qu'est-ce que je fais "
           "aujourd'hui, où en est mon entraînement, qu'a donné ma séance.",
           ["L'Accueil : ta forme, ta semaine, tes objectifs, tes allures et tes records",
            "« Aujourd'hui » : ta séance du jour, la météo et ton créneau",
            "Le calendrier, l'entraînement, la séance et son effet",
            "La récup selon tes postes de travail, et tes objectifs de course",
            "Ton club FFA, ta balance Withings et tes séances Strava"],
           img="v-accueil-haut")

    D.view("Volet de gauche › <b>Accueil</b>", "Accueil : ta journée en un coup d'œil",
           "La première chose que tu vois le matin : ta forme, ta semaine et tes objectifs, sans fouiller.",
           "v-accueil-haut", [(700, 160), (25, 329), (135, 462), (1050, 289), (265, 752), (12, 1000)], [
               "Ta journée : ton poste (matin ou soir), le compte à rebours de ta course, ton club et la dernière synchro. "
               "Le logo de ton club s'affiche à côté du bonjour (partie 6).",
               "Forme du jour : sommeil, VFC, FC de repos, Body Battery, fraîcheur… comparés à tes propres habitudes, avec "
               "un verdict clair.",
               "Chaque signal a sa petite courbe des dernières semaines (détail à la page suivante).",
               "Tes objectifs : ta course principale (compte à rebours, temps visé, allure cible, part de ta VMA) et les "
               "suivantes.",
               "Ta semaine : séances faites, postes de travail et jours de repos ; et tes séances prévues, si ton "
               "calendrier est relié.",
               "Le bilan de la semaine face à ta moyenne : séances, kilomètres, durée, D+, charge et séances prévues faites.",
           ], max_w=176, max_h=118, cols=True)

    D.view("Volet de gauche › <b>Accueil</b>", "Forme du jour : tes signaux en courbes",
           "Les chiffres sont accompagnés de petites courbes : en un coup d'œil, tu vois si ta nuit, ta VFC ou ta FC de "
           "repos sortent de tes habitudes.",
           "v-forme", [(235, 85), (465, 85), (695, 85), (925, 85), (235, 290), (465, 290), (695, 290)], [
               "FC de repos : 30 jours, et ta moyenne en pointillé.",
               "VFC de la nuit : 30 nuits, et ta zone habituelle (celle de Garmin) en fond vert.",
               "Durée de sommeil : 14 nuits, face à ton besoin.",
               "Score de sommeil : 14 nuits, repère à 80.",
               "Body Battery au réveil : repère à 70.",
               "Fraîcheur : 30 jours, et la zone de charge productive en fond vert.",
               "SpO2 de la nuit : repère à 95 %.",
           ], max_w=176, max_h=100, cols=True,
           after=note("Le liseré de chaque carte prend la couleur de l'état (vert, orange, rouge). Survole un point ou une "
                      "barre : sa date et sa valeur."))

    D.view("Volet de gauche › <b>Accueil</b>", "Accueil : tes allures et tes records",
           "Plus bas sur l'Accueil, de quoi préparer tes séances et suivre tes progrès.",
           "v-accueil-bas", [(290, 28), (10, 190), (1040, 28), (380, 495), (790, 495)], [
               "Tes allures d'entraînement calculées sur ta VMA, de l'endurance au lactique, en min/km et en km/h.",
               "Les temps de passage sur piste, du 200 au 800 m.",
               "Un test VAMEVAL intégré pour mesurer ta VMA.",
               "Ta journée en courbe : Body Battery, stress, fréquence cardiaque…",
               "Tes records sur la période choisie, face à tes records absolus.",
           ], max_w=176, max_h=118)

    # --- Aujourd'hui ---
    D.page("Volet de gauche › <b>Aujourd'hui</b>", "Ma séance du jour",
           "La vue « Aujourd'hui » est une seule carte, qui répond chaque matin à trois questions. Comment je suis ? "
           "Qu'est-ce que je fais ? Quand courir ?",
           shot("v-jour", [(1, 30, 75), (2, 180, 145), (3, 40, 245), (4, 660, 190), (5, 1240, 250)], 176, 80)
           + legend([
               "Le verdict du jour, d'après ta nuit, ta FC de repos et ta Body Battery : séance normale, prudence ou "
               "journée facile.",
               "Ce qui est prévu aujourd'hui, depuis ton calendrier Garmin : renfo, course, avec l'allure de chaque étape "
               "quand la séance en a.",
               "Déjà dans ton calendrier Garmin : ta montre l'a à la synchro.",
               "Ton créneau : le meilleur moment pour courir, entre la pluie, le vent, le froid et la nuit, hors de tes "
               "heures de travail si tu es posté.",
               "La météo heure par heure, près de ta dernière sortie (Open-Meteo, sans compte). Tes heures de travail "
               "sont grisées.",
           ], cols=True)
           + shot("b-ressenti", [(6, 1000, 293), (7, 1330, 400)], 176, 60)
           + legend([
               "Après la séance : la séance faite face à la prévue, et ton ressenti de 1 à 10…",
               "… avec un mot. Tu as un coach dans Foulée ? « Envoyer à mon coach » le lui transmet.",
           ], start=6))

    D.page("Volet de gauche › <b>Aujourd'hui</b>", "Le temps passé dans chaque zone de FC",
           "Nouveau dans la 0.8.3. Sous ta séance du jour, le temps passé dans chaque zone de fréquence cardiaque, "
           "comme dans Garmin Connect : la zone 5 en haut, une barre à la couleur de la zone, le temps et la part de la séance.",
           shot("n83-jour", max_w=132, max_h=124, cap="La colonne de droite de « Aujourd'hui », une fois la séance faite : "
                "la météo, puis le temps par zone FC.")
           + ul([
               "Les couleurs sont celles de tes zones (Réglages › Entraînement › Zones FC › Couleurs des zones).",
               "Le calcul suit tes zones : celles de ta montre, ou celles que tu règles dans Foulée.",
               "Une séance sans fréquence cardiaque n'affiche pas le tableau.",
           ]))

    D.page("Volet de gauche › <b>Calendrier</b>", "Calendrier : ton plan, face à ce que tu fais",
           "Publie ton calendrier Garmin Connect et colle son lien dans les Réglages : tes séances prévues et tes courses "
           "arrivent dans Foulée, et la vue Calendrier s'ajoute juste après l'Accueil.",
           shot("v-calendrier", [(1, 20, 58), (2, 375, 58), (3, 12, 280), (4, 410, 830), (5, 655, 965), (6, 1235, 225)],
                176, 118)
           + legend([
               "Ta prochaine course et son compte à rebours.",
               "Tes prochaines séances prévues, jour après jour.",
               "Le mois : séances prévues, courses, et séances faites (« hors plan » quand elles n'étaient pas prévues).",
               "Une séance prévue puis faite est cochée en vert ; un jour passé sans séance du même sport : « manquée ».",
               "La course, en rouge dans le mois.",
               "Un clic sur un jour : chaque séance prévue, son esquisse, et la séance faite, qui s'ouvre d'un clic.",
           ], cols=True)
           + note("Le lien de ton calendrier reste secret : rangé dans le coffre de Windows, comme ta clé Garmin, et jamais "
                  "montré en entier."))

    D.view("Volet de gauche › <b>Entraînement</b>", "Entraînement : ton volume et ta charge",
           "Pour progresser sans se blesser : le volume, la charge et la fraîcheur, semaine après semaine.",
           "v-entrainement", [(330, 32), (1245, 60), (200, 341), (200, 653)], [
               "Tes kilomètres, semaine après semaine.",
               "Kilomètres et charge des 7 derniers jours, face aux 4 semaines d'avant.",
               "Forme et fatigue : charge aiguë (7 jours), charge chronique (42 jours) et fraîcheur.",
               "Le ratio aiguë / chronique, avec sa zone de confort (de 0,8 à 1,3).",
           ], max_w=176, max_h=120,
           after=note("Plus bas dans cette vue : le temps passé par zone de FC et d'allure, et la liste de tes séances."))

    D.view("Volet de gauche › <b>Séance</b>", "Séance : chaque sortie dans le détail",
           "Choisis une séance : tout est là, du tracé aux tours.",
           "v-seance", [(730, 25), (10, 90), (90, 237), (750, 237), (90, 700)], [
               "Choisis n'importe quelle séance, ou passe de l'une à l'autre avec les flèches.",
               "Le résumé : distance, durée, allure, FC, D+, charge, cadence, effets aérobie et anaérobie, découplage…",
               "Le tracé sur la carte (ici départ et arrivée floutés).",
               "Fréquence cardiaque, allure et altitude, alignées sur le temps.",
               "Les tours, avec les plus rapides en gras.",
           ], max_w=176, max_h=128,
           after=note("Entre le résumé et la carte : l'effet d'entraînement, le temps par zone et l'analyse fraction par "
                      "fraction (pages suivantes)."))

    D.view("Volet de gauche › <b>Séance</b>", "Séance : l'effet d'entraînement",
           "Sous le résumé de chaque séance, le Training Effect calculé par ta montre Garmin, en deux jauges aux couleurs "
           "de Garmin Connect.",
           "v-effet", [(95, 55), (152, 211), (262, 60), (500, 55), (975, 82), (1010, 154)], [
               "L'effet aérobie, de 0 à 5 : ce que la séance apporte à ton endurance.",
               "Son niveau, avec les mots et les couleurs de Garmin Connect, et ce qu'il veut dire.",
               "Les petits traits : tes séances du même sport des 4 semaines précédentes.",
               "L'effet anaérobie : ce que la séance apporte à tes efforts brefs et très intenses.",
               "L'avantage principal de la séance selon Garmin : base, tempo, seuil, VO2 max, sprint…",
               "Sa place parmi tes séances du même sport des 4 semaines d'avant.",
           ], max_w=176, max_h=60, cols=True)

    D.page("Volet de gauche › <b>Séance</b>", "Séance : le temps par zone de FC et d'allure",
           "Nouveau dans la 0.8.3. Dans la vue Séance, une tuile donne le temps passé dans chaque zone de fréquence "
           "cardiaque et, pour une course, dans chaque zone d'allure.",
           shot("v-seance-zones", max_w=176, max_h=60,
                cap="La tuile « Temps par zone », côte à côte : zones de FC et zones d'allure.")
           + ul([
               "La zone 5 en haut, comme dans Garmin Connect : une barre à la couleur de la zone, le temps, et la part de "
               "la séance en pourcentage.",
               "Les zones d'allure se calculent sur ta VMA : elles n'apparaissent que pour les sports où une allure a un "
               "sens (course, trail, marche).",
               "La tuile s'ajoute d'elle-même à ta vue Séance à la mise à jour. Tu peux l'enlever, la déplacer ou choisir "
               "de n'afficher qu'un seul des deux tableaux (roue dentée › FC, allure, ou les deux).",
           ])
           + note("Les bornes de tes zones se règlent dans Réglages › Entraînement › Zones FC, et leurs couleurs juste en "
                  "dessous (partie 6)."))

    D.view("Volet de gauche › <b>Récup &amp; postes</b>", "Récup &amp; postes : quand le travail s'en mêle",
           "Pensé pour les horaires décalés : Foulée connaît ton planning (matin, soir, repos) et compare ta récupération "
           "selon le poste.",
           "v-recup", [(225, 30), (1140, 125), (240, 495), (215, 803), (835, 803)], [
               "Semaines du matin contre semaines du soir : sommeil, heure de lever, VFC, FC de repos, Body Battery, stress.",
               "L'écart net, dit en clair (« 2 h 14 plus tôt »).",
               "Les courbes, sur fond coloré selon le poste de la semaine.",
               "Les liens entre tes données : ici, ta VFC suit ton sommeil.",
               "Le calendrier de tes nuits, de la plus courte à la plus longue.",
           ], max_w=176, max_h=124)

    D.view("Volet de gauche › <b>Objectifs</b>", "Objectifs : ta course, et les suivantes",
           "Une vue pour préparer tes courses : la principale, les suivantes, et tout ce qui dit si tu es prêt. La tienne "
           "se compose avec les mêmes tuiles (partie 6).",
           "v-objectifs", [(215, 74), (720, 70), (300, 491), (215, 799), (810, 799)], [
               "L'objectif principal : compte à rebours, temps visé, allure cible et part de ta VMA.",
               "Les objectifs secondaires, avec l'équivalent de chacun sur ta course principale.",
               "Tes fractions rapides face à ton allure cible : tu vois si tu t'en rapproches.",
               "Le volume semaine après semaine.",
               "La charge et la fraîcheur, pour arriver frais le jour J.",
           ], max_w=176, max_h=124)

    D.view("Volet de gauche › <b>Mon club</b>", "Mon club : ton club FFA",
           "Coche « Je fais partie d'un club » dans les Réglages, donne le numéro de club de ta licence : la vue s'ajoute "
           "toute seule.",
           "v-club", [(455, 47), (25, 30), (15, 126), (170, 181), (895, 181)], [
               "Ton club, son numéro et la saison FFA en cours.",
               "Le logo de ton club, choisi dans la logothèque (partie 6).",
               "En un clic, le classement du club sur athle.fr (saison en cours ou précédente), sa page et son site.",
               "Les coordonnées du club, remplies en un copier-coller de sa fiche sur athle.fr (floutées ici).",
               "Ta licence, avec un rappel un mois avant la fin de validité (numéro flouté ici).",
           ], max_w=176, max_h=76)

    D.view("Volet de gauche › <b>Withings</b>", "Withings : ta balance dans Foulée",
           "Connecte ton compte Withings dans les Réglages (tout est expliqué pas à pas), et la vue s'ajoute toute seule, "
           "avec les tuiles des mesures que tes appareils prennent.",
           "v-withings", [(180, 111), (190, 150), (135, 491), (885, 491)], [
               "Le dernier passage sur la balance : poids, masse grasse et musculaire, eau, os, graisse viscérale, IMC, "
               "métabolisme de base…",
               "L'écart avec une pesée d'il y a un mois : en vert quand il va dans le bon sens, en rouge sinon.",
               "Ton poids dans le temps.",
               "Ta composition corporelle : masse grasse et masse musculaire.",
           ], max_w=176, max_h=110,
           after=note("Tension (tensiomètre), sommeil (Sleep Analyzer) ou pas (montre Withings) : leurs tuiles arrivent "
                      "d'elles-mêmes si tes appareils les mesurent. En haut de la page, une pastille par connexion (Garmin, "
                      "Withings, Strava, calendrier) : verte quand la dernière synchro a abouti."))

    # --- Strava ---
    steps = [
        (1, "Crée l'appli Strava de Foulée",
         fr("Dans les réglages API de Strava (strava.com/settings/api) : un nom sans le mot « Strava », la catégorie "
            "Visualizer, et l'adresse de ton Foulée (bouton « Copier » dans Foulée). Il faut un abonnement Strava pour la "
            "créer ; les autres profils de la maison s'y connectent sans.")),
        (2, "Colle le Client ID et le Client Secret",
         fr("Dans Réglages › Connexions › Strava. Ils vont dans le coffre de Windows, comme ta clé Garmin.")),
        (3, "« Connecter mon compte Strava »",
         fr("Puis « Autoriser » chez Strava : tu reviens dans Foulée et le premier import démarre.")),
    ]
    D.page("Réglages › Connexions › <b>Strava</b>", "Strava : tes séances, d'où qu'elles viennent",
           "En lecture seule. Une montre Coros, Suunto, Polar ou Apple, un compteur de vélo, une séance de muscu notée sur "
           "Strava : tes séances Strava rejoignent les autres. Avec une montre Garmin, Strava apporte le titre, la "
           "description et les kudos de tes séances.",
           shot("v-resume-strava", [(1, 10, 119), (2, 318, 119)], 176, 26)
           + legend([
               "Une séance Garmin que Strava a aussi : « aussi sur Strava », et ses kudos.",
               "« View on Strava » ouvre la séance chez Strava.",
           ])
           + howto(steps, "compact")
           + box("Les règles de Strava, appliquées",
                 f'<p>{fr("Lecture seule : Foulée ne peut rien publier ni modifier. Un cache de 48 heures, pas une "
                           "archive : tout est relu à chaque synchro. Et pas pour l’IA : Claude Desktop ne voit aucune "
                           "donnée Strava.")}</p>', "lock"))


def part4(D):
    D.part("Le renfo", "Foulée lit le détail de tes séances de musculation dans Garmin Connect : exercices, séries, "
           "répétitions, charges. Il en tire les muscles travaillés, l'équilibre avant / arrière et ta progression.",
           ["Les muscles que tu travailles, et la carte du corps",
            "L'équilibre entre la chaîne avant et la chaîne arrière, et quoi ajouter",
            "Chaque exercice et sa progression",
            "Le détail d'une séance de renfo",
            "Tes réglages de renfo : objectif de la semaine et ratio cible"],
           img="v-renfo-haut")

    D.view("Volet de gauche › <b>Renfo</b>", "Renfo : les muscles que tu travailles",
           "La vue Renfo arrive avec ta première séance de musculation détaillée.",
           "v-renfo-haut", [(8, 80), (160, 121), (140, 267), (945, 70)], [
               "Sur la période choisie : séances, rythme par semaine, séries, tonnage et temps d'effort.",
               "Tes séances semaine après semaine, face à ton objectif (Réglages › Entraînement › Renfo).",
               "Les séries par muscle, du plus au moins travaillé, et ceux que tu as laissés de côté. Une série compte pour "
               "1 sur un muscle principal, pour ½ sur un secondaire.",
               "La carte du corps, face et dos : la couleur dit combien chaque muscle a travaillé.",
           ], max_w=176, max_h=110,
           after=note("Les exercices viennent de ta montre (activité « Musculation », un exercice choisi à chaque série) ou "
                      "d'un entraînement de renfo préparé dans Garmin Connect, traduits en français."))

    families = box("Comment chaque exercice est rangé",
                   f'<p><b>{fr("Devant")}</b>{fr(" : squats, fentes, chaise · pompes, développés, élévations · planche, "
                                                  "crunchs · curls · releveurs du pied")}</p>'
                   f'<p><b>{fr("Derrière")}</b>{fr(" : soulevé de terre roumain, hip thrust, leg curl, swing · rowing, "
                                                    "tractions, oiseau · superman, extensions lombaires · dips, triceps · "
                                                    "mollets")}</p>'
                   f'<p><b>{fr("À part")}</b>{fr(" : « corps entier » (burpees, portés) compte ½ de chaque côté ; latéral et "
                                                  "rotation ne comptent ni devant ni derrière ; échauffement et cardio ne "
                                                  "comptent pas.")}</p>', "balance")
    D.view("Volet de gauche › <b>Renfo</b>", "Renfo : l'équilibre avant / arrière",
           "Les préparateurs physiques équilibrent la chaîne antérieure et la chaîne postérieure : 1:1, et jusqu'à 1:2 en "
           "faveur de l'arrière pour un coureur, car la propulsion vient des fessiers, des ischios et des mollets.",
           "v-equilibre", [(240, 71), (12, 152), (8, 225), (395, 75), (500, 128), (392, 182), (1250, 62)], [
               "Le rapport avant : arrière, en séries : « 1 : 1,4 », c'est 1,4 série derrière pour 1 devant. Et le verdict.",
               "L'échelle, de tout à l'avant à tout à l'arrière ; en vert, ta cible.",
               "Le conseil : ce qui manque, et quels exercices ajouter.",
               "Paire par paire, en ailes de papillon : bas du corps, tronc, bas de jambe…",
               "La paire qui penche vers l'avant est signalée.",
               "Le latéral et la rotation (bonds latéraux, planche latérale…) sont comptés à part.",
               "Semaine après semaine, face à la bande de la cible.",
           ], max_w=176, max_h=46, cols=True,
           after=shot("v-renfo-conseils", max_w=150, max_h=55,
                      cap="Juste en dessous, « exercices pour rééquilibrer » : de quoi compléter, et « En faire une séance "
                          "pour ma montre » l'ouvre dans l'Atelier.")
           + families)

    D.view("Volet de gauche › <b>Renfo</b>", "Renfo : chaque exercice et ta progression",
           "Plus bas dans la vue Renfo : tous tes exercices de la période, comment chacun compte dans l'équilibre avant / "
           "arrière, et comment ils évoluent d'une séance à l'autre.",
           "v-renfo-exercices", [(140, 99), (8, 118), (458, 118), (612, 66), (845, 66), (1060, 66)], [
               "Chaque exercice, en français.",
               "Son étiquette : comment il compte dans l'équilibre (avant, arrière, latéral et rotation à part, ou non compté).",
               "Ses muscles principaux, puis secondaires (en italique).",
               "Le nombre de séances et de séries où tu l'as fait.",
               "Ta dernière séance avec cet exercice : séries × répétitions (ou durée) et charge.",
               "L'évolution : la charge si tu en portes une, sinon les répétitions ou la durée ; en vert quand ça progresse.",
           ], max_w=176, max_h=70, cols=True,
           after=note("Une séance corrigée dans l'appli Garmin Connect se met à jour à la synchro suivante."))

    D.view("Volet de gauche › <b>Séance</b>", "Séance : le détail d'un renfo",
           "Ouvre une séance de musculation : ses exercices s'affichent sous le résumé, avec l'équilibre de la séance.",
           "v-seance-renfo", [(225, 111), (8, 280), (195, 359), (8, 413), (8, 480), (8, 607), (985, 270)], [
               "Le résumé : durée, FC, charge, effets d'entraînement…",
               "Le bilan : séries, répétitions, tonnage et temps d'effort.",
               "L'équilibre avant / arrière de la séance : ici 12 séries devant, 12 derrière, 1 : 1, dans la cible.",
               "L'échelle, avec la bande verte de ta cible.",
               "Le conseil : ce qui penche, et les exercices à ajouter.",
               "Chaque exercice porte son étiquette : avant, arrière, latéral (compté à part) ou non compté.",
               "Les muscles travaillés pendant la séance.",
           ], max_w=176, max_h=130, cols=True,
           after=note("Pour une course ou une sortie à vélo, cette tuile s'efface d'elle-même."))

    D.page("Réglages › Entraînement › <b>Renfo</b>", "Tes réglages de renfo",
           "Nouveau dans la 0.8.3. Une rubrique rassemble tout ce qui concerne ton renfo : ce que tu vises par semaine, "
           "l'équilibre que tu cherches, et ce que Foulée met dans les séances qu'il te prépare.",
           row(shot("v-reglages-renfo", max_w=86, max_h=138),
               ul([
                   "<b>Objectif de la semaine</b> : le nombre de séances visé, repère de la vue Renfo et des conseils.",
                   "<b>Équilibre avant / arrière visé</b> : quatre profils. <i>Coureur</i> (de 1:1 à 1:2, visé 1:1,5), "
                   "<i>Équilibré</i> (0,8 à 1,25), <i>Priorité à l'arrière</i> (1,5 à 3) ou <i>À ma façon</i>, où tu "
                   "fixes toi-même les bornes. Le profil choisi change la bande verte de l'échelle, le verdict et les "
                   "conseils, partout dans Foulée.",
                   "<b>Les conseils qui vont avec</b> : chaque profil dit en une phrase ce qu'il vise et pour qui il est "
                   "fait ; sous l'échelle, les règles de base (chaîne postérieure en premier, corriger en ajoutant…).",
                   "<b>Niveau</b> : débutant, intermédiaire ou confirmé. Il règle le nombre de séries proposé dans "
                   "l'Atelier et dans les séances toutes faites.",
                   "<b>Matériel à disposition</b> : tous les exercices, ou seulement ceux que tu peux faire avec ce que tu "
                   "as (élastique, haltères, kettlebell, banc, swiss ball…).",
                   "<b>Mes séances composées</b> : tes séances de renfo de l'Atelier, retrouvées ici.",
               ]), grow=1))
