"""Partie 3 — Foulée au quotidien (les vues) et Partie 4 — Le renfo."""
from kit import box, chip, code, fr, howto, icon, legend, note, row, shot, ul


def part3(D):
    D.part("Foulée au quotidien", "Chaque vue répond à une question : comment je suis ce matin, qu'est-ce que je fais "
           "aujourd'hui, où en est mon entraînement, qu'a donné ma séance.",
           ["L'Accueil : ta forme, ta semaine, ton objectif, tes allures et tes records",
            "« Aujourd'hui » : ta séance du jour, la météo et ton créneau",
            "Le calendrier, l'entraînement, la séance et son effet",
            "La récup selon tes postes de travail, et une vue pour ta course",
            "Ton club FFA, ta balance Withings et tes séances Strava"],
           img="accueil-haut")

    D.view("Volet de gauche › <b>Accueil</b>", "Accueil : ta journée en un coup d'œil",
           "La première chose que tu vois le matin : ta forme, ta semaine et ton objectif, sans fouiller.",
           "accueil-haut", [(470, 243), (290, 410), (320, 764), (1530, 410), (410, 1062), (1440, 1408)], [
               "Ta journée : ton poste (matin ou soir), le compte à rebours de ta course, ton club et la dernière synchro.",
               "Forme du jour : sommeil, VFC, FC de repos, Body Battery, fraîcheur… comparés à tes propres habitudes, avec "
               "un verdict clair.",
               "Chaque signal a sa petite courbe des dernières semaines (détail à la page suivante).",
               "Ton objectif : compte à rebours, temps visé, allure cible et part de ta VMA.",
               "Ta semaine : séances faites, postes de travail et jours de repos ; et tes séances prévues, si ton "
               "calendrier est relié.",
               "Le bilan de la semaine face à ta moyenne : séances, kilomètres, durée, D+ et charge.",
           ], max_w=176, max_h=104, cols=True)

    D.view("Volet de gauche › <b>Accueil</b>", "Forme du jour : tes signaux en courbes",
           "Les chiffres que tu lisais dans les infobulles sont de petites courbes : en un coup d'œil, tu vois si ta nuit, "
           "ta VFC ou ta FC de repos sortent de tes habitudes.",
           "forme", [(262, 192), (532, 192), (792, 192), (1062, 192), (262, 424), (532, 424), (810, 424)], [
               "FC de repos : 30 jours, et ta moyenne en pointillé.",
               "VFC de la nuit : 30 nuits, et ta zone habituelle (celle de Garmin) en fond vert.",
               "Durée de sommeil : 14 nuits, face à ton besoin.",
               "Score de sommeil : 14 nuits, repère à 80.",
               "Body Battery au réveil : repère à 70.",
               "Fraîcheur : 30 jours, et la zone de charge productive (−10 à −30) en fond vert.",
               "SpO2 de la nuit : repère à 95 %.",
           ], max_w=176, max_h=112, cols=True,
           after=note("Le dernier point prend la couleur de l'état (vert, orange, rouge). Survole un point ou une barre : "
                      "sa date et sa valeur."))

    D.view("Volet de gauche › <b>Accueil</b>", "Accueil : tes allures et tes records",
           "Plus bas sur l'Accueil, de quoi préparer tes séances et suivre tes progrès.",
           "accueil-bas", [(428, 34), (230, 236), (1210, 34), (508, 642), (932, 642)], [
               "Tes allures d'entraînement calculées sur ta VMA, de l'endurance au lactique, en min/km et en km/h.",
               "Les temps de passage sur piste, du 200 au 800 m.",
               "Un test VAMEVAL intégré pour mesurer ta VMA.",
               "Ta journée en courbe : Body Battery, stress, fréquence cardiaque…",
               "Tes records sur la période choisie, face à tes records absolus.",
           ], max_w=176, max_h=116)

    # --- Aujourd'hui ---
    D.page("Volet de gauche › <b>Aujourd'hui</b>", "Ma séance du jour",
           "La vue « Aujourd'hui » est une seule carte, qui répond chaque matin à trois questions. Comment je suis ? "
           "Qu'est-ce que je fais ? Quand courir ?",
           shot("b-jour", [(1, 85, 136), (2, 95, 381), (3, 932, 580), (4, 76, 686), (5, 1119, 358), (6, 1450, 807)], 176, 76)
           + legend([
               "Le verdict du jour, d'après ta nuit, ta FC de repos et ta Body Battery : séance normale, prudence ou "
               "journée facile.",
               "Ce qui est prévu aujourd'hui, depuis ton calendrier Garmin : la séance et son esquisse…",
               "… et chaque étape avec l'allure à tenir, calculée sur ta VMA.",
               "Déjà dans ton calendrier Garmin : ta montre l'a à la synchro.",
               "Ton créneau : le meilleur moment pour courir, entre la pluie, le vent, le froid et la nuit, hors de tes "
               "heures de travail si tu es posté.",
               "La météo heure par heure, près de ta dernière sortie (Open-Meteo, sans compte).",
           ], cols=True)
           + shot("b-ressenti", [(7, 1000, 293), (8, 1330, 400)], 176, 60)
           + legend([
               "Après la séance : la séance faite face à la prévue, et ton ressenti de 1 à 10…",
               "… avec un mot. Tu as un coach dans Foulée ? « Envoyer à mon coach » le lui transmet.",
           ], start=7))

    D.page("Volet de gauche › <b>Aujourd'hui</b>", "Le temps passé dans chaque zone de FC",
           "Nouveau dans la 0.8.3. Sous ta séance du jour, le temps passé dans chaque zone de fréquence cardiaque, "
           "comme dans Garmin Connect : la zone 5 en haut, une barre à la couleur de la zone, le temps et la part de la séance.",
           shot("n83-jour", max_w=132, max_h=124, cap="La colonne de droite de « Aujourd'hui » : la météo, puis le temps par zone FC.")
           + ul([
               "Les couleurs sont celles de tes zones (Réglages › Entraînement › Zones FC › Couleurs des zones).",
               "Le calcul suit la méthode que tu as choisie pour tes zones : pourcentage de la FC max, ou de la réserve "
               "cardiaque.",
               "Une séance sans fréquence cardiaque (un renfo au poids du corps, par exemple) n'affiche pas le tableau.",
           ]))

    # --- Calendrier ---
    D.page("Volet de gauche › <b>Calendrier</b>", "Calendrier : ton plan, face à ce que tu fais",
           "Publie ton calendrier Garmin Connect et colle son lien dans les Réglages : tes séances prévues et tes courses "
           "arrivent dans Foulée, et la vue Calendrier s'ajoute juste après l'Accueil.",
           shot("beta-calendrier", [(1, 54, 104), (2, 962, 230), (3, 20, 600), (4, 604, 752), (5, 976, 1104), (6, 1684, 436)], 176, 104)
           + legend([
               "Ta prochaine course et son compte à rebours.",
               "Tes prochaines séances prévues, jour après jour.",
               "Le mois : séances prévues, courses, et séances faites (« hors plan » quand elles n'étaient pas prévues).",
               "Une séance prévue puis faite est cochée en vert. Un jour passé sans séance du même sport : « manquée ».",
               "La course, en rouge dans le mois.",
               "Un clic sur un jour : la consigne de chaque séance prévue, et la séance faite, qui s'ouvre d'un clic.",
           ], cols=True)
           + note("Le lien de ton calendrier reste secret : rangé dans le coffre de Windows, comme ta clé Garmin, et jamais "
                  "montré en entier."))

    D.view("Volet de gauche › <b>Entraînement</b>", "Entraînement : ton volume et ta charge",
           "Pour progresser sans se blesser : le volume, la charge et la fraîcheur, semaine après semaine.",
           "entrainement", [(424, 182), (1264, 178), (230, 591), (272, 1008)], [
               "Tes kilomètres, semaine après semaine.",
               "Kilomètres et charge des 7 derniers jours, face aux 4 semaines d'avant.",
               "Forme et fatigue : charge aiguë (7 jours), charge chronique (42 jours) et fraîcheur.",
               "Le ratio aiguë / chronique, avec sa zone de confort (de 0,8 à 1,3).",
           ], max_w=176, max_h=122,
           after=note("Plus bas dans cette vue : le temps passé par zone de FC et d'allure, et la liste de tes séances."))

    D.view("Volet de gauche › <b>Séance</b>", "Séance : chaque sortie dans le détail",
           "Choisis une séance : tout est là, du tracé aux tours.",
           "beta-seance", [(1006, 168), (74, 242), (140, 450), (932, 450), (140, 1066)], [
               "Choisis n'importe quelle séance, ou passe de l'une à l'autre avec les flèches.",
               "Le résumé : distance, durée, allure, FC, D+, charge, cadence, effets aérobie et anaérobie, découplage…",
               "Le tracé sur la carte (OpenStreetMap ou IGN).",
               "Fréquence cardiaque, allure et altitude, alignées sur le temps.",
               "Les tours, avec les plus rapides en gras.",
           ], max_w=176, max_h=120)

    D.view("Volet de gauche › <b>Séance</b>", "Séance : l'effet d'entraînement",
           "Sous le résumé de chaque séance, le Training Effect calculé par ta montre Garmin, en deux jauges aux couleurs "
           "de Garmin Connect.",
           "effet", [(1196, 214), (171, 414), (65, 777), (500, 470), (749, 414), (1214, 414), (1214, 610)], [
               "Dans le résumé de chaque séance : les effets aérobie et anaérobie.",
               "L'effet aérobie, de 0 à 5 : ce que la séance apporte à ton endurance.",
               "Son niveau, avec les mots et les couleurs de Garmin Connect, et ce qu'il veut dire.",
               "Les petits traits : tes séances du même sport des 4 semaines précédentes.",
               "L'effet anaérobie : ce que la séance apporte à tes efforts brefs et très intenses.",
               "L'avantage principal de la séance selon Garmin : base, tempo, seuil, VO2 max, sprint…",
               "Sa place parmi tes séances du même sport des 4 semaines d'avant.",
           ], max_w=176, max_h=90, cols=True)

    D.page("Volet de gauche › <b>Séance</b>", "Séance : le temps par zone de FC et d'allure",
           "Nouveau dans la 0.8.3. Dans la vue Séance, une tuile donne le temps passé dans chaque zone de fréquence "
           "cardiaque et, pour une course, dans chaque zone d'allure.",
           shot("n83-seance-zones", max_w=176, max_h=50,
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
                  "dessous."))

    D.view("Volet de gauche › <b>Récup &amp; postes</b>", "Récup &amp; postes : quand le travail s'en mêle",
           "Pensé pour les horaires décalés : Foulée connaît ton planning (matin, soir, repos) et compare ta récupération "
           "selon le poste.",
           "recup", [(330, 160), (1400, 296), (292, 797), (348, 1196), (1100, 1190)], [
               "Semaines du matin contre semaines du soir : sommeil, heure de lever, VFC, FC de repos, Body Battery, stress.",
               "L'écart net, dit en clair (« 2 h 19 plus tôt »).",
               "Les courbes, sur fond coloré selon le poste de la semaine.",
               "Les liens entre tes données : ici, ta VFC suit ton sommeil.",
               "Le calendrier de tes nuits, de la plus courte à la plus longue.",
           ], max_w=176, max_h=120)

    D.view("Volet de gauche › <b>Ta course</b>", "Une vue pour ta course",
           "Une vue créée pour préparer un semi-marathon. La tienne se compose avec les mêmes tuiles (partie 6).",
           "capsemi", [(154, 182), (916, 182), (292, 591), (998, 591)], [
               "L'objectif : compte à rebours, temps visé et allure cible.",
               "Tes fractions rapides face à ton allure cible : tu vois si tu t'en rapproches.",
               "Le volume depuis le début de la préparation.",
               "La charge et la fraîcheur, pour arriver frais le jour J.",
           ], max_w=176, max_h=122)

    D.view("Volet de gauche › <b>Mon club</b>", "Mon club : ton club FFA",
           "Coche « Je fais partie d'un club » dans les Réglages, donne le numéro de club de ta licence : la vue s'ajoute "
           "toute seule.",
           "club", [(510, 214), (36, 230), (36, 326), (270, 403), (1120, 403)], [
               "Ton club, son numéro et la saison FFA en cours.",
               "Le logo de ton club (partie 6 : la logothèque).",
               "En un clic, le classement du club sur athle.fr (saison en cours ou précédente), sa page et son site.",
               "Les coordonnées du club, remplies en un copier-coller de sa fiche sur athle.fr (floutées ici).",
               "Ta licence, avec un rappel un mois avant la fin de validité (numéro flouté ici).",
           ], max_w=176, max_h=96)

    D.view("Volet de gauche › <b>Withings</b>", "Withings : ta balance dans Foulée",
           "Connecte ton compte Withings dans les Réglages (tout est expliqué pas à pas), et la vue s'ajoute toute seule, "
           "avec les tuiles des mesures que tes appareils prennent.",
           "withings", [(70, 300), (500, 480), (34, 902), (768, 902), (1205, 24)], [
               "Le dernier passage sur la balance : poids, masse grasse et musculaire, eau, os, graisse viscérale, IMC, "
               "métabolisme de base…",
               "L'écart avec la pesée d'il y a un mois : en vert quand il va dans le bon sens, en rouge sinon.",
               "Ton poids dans le temps.",
               "Ta composition corporelle : masse grasse et masse musculaire.",
               "Les pastilles de connexion : vertes quand la dernière synchro a abouti, rouges sinon.",
           ], max_w=176, max_h=116,
           after=note("Tension (tensiomètre), sommeil (Sleep Analyzer) ou pas (montre Withings) : leurs tuiles arrivent "
                      "d'elles-mêmes si tes appareils les mesurent."))

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
           shot("resume-strava", [(1, 215, 270), (2, 505, 270)], 176, 28)
           + legend([
               "Une séance Garmin que Strava a aussi : son titre, sa description et ses kudos sur Strava.",
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
            "L'équilibre entre la chaîne avant et la chaîne arrière",
            "Chaque exercice et sa progression",
            "Le détail d'une séance de renfo",
            "Tes réglages de renfo : objectif de la semaine et ratio cible"],
           img="renfo-haut")

    D.view("Volet de gauche › <b>Renfo</b>", "Renfo : les muscles que tu travailles",
           "La vue Renfo arrive avec ta première séance de musculation détaillée.",
           "renfo-haut", [(34, 268), (34, 436), (34, 600), (962, 232)], [
               "Sur la période choisie : séances, rythme par semaine, séries, tonnage et temps d'effort.",
               "Tes séances semaine après semaine, face à ton objectif (réglable, 2 par semaine par défaut).",
               "Les séries par muscle, du plus au moins travaillé, et ceux que tu as laissés de côté. Une série compte pour "
               "1 sur un muscle principal, pour ½ sur un secondaire.",
               "La carte du corps, face et dos : la couleur dit combien chaque muscle a travaillé.",
           ], max_w=176, max_h=118,
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
           "equilibre", [(460, 129), (300, 250), (706, 462), (716, 158), (988, 234), (577, 201), (2095, 100)], [
               "Le rapport avant : arrière, en séries : « 1 : 1,5 », c'est 1,5 série derrière pour 1 devant. Et le verdict.",
               "L'échelle, de tout à l'avant à tout à l'arrière ; en vert, ta cible.",
               "Le conseil : ce qui manque, et quels exercices ajouter.",
               "Paire par paire, en ailes de papillon : bas du corps, haut du corps, tronc, bras, bas de jambe.",
               "La paire qui penche vers l'avant est signalée.",
               "Le latéral et la rotation (bonds latéraux, planche latérale…) sont comptés à part.",
               "Semaine après semaine, face à la bande de la cible.",
           ], max_w=176, max_h=62, cols=True, after=families)

    D.view("Volet de gauche › <b>Renfo</b>", "Renfo : chaque exercice et ta progression",
           "Plus bas dans la vue Renfo : tous tes exercices de la période, comment chacun compte dans l'équilibre avant / "
           "arrière, et comment ils évoluent d'une séance à l'autre.",
           "renfo-exercices", [(8, 187), (8, 332), (922, 226), (963, 120), (1320, 188), (1635, 120)], [
               "Chaque exercice, en français.",
               "Son étiquette : comment il compte dans l'équilibre (avant, arrière, latéral et rotation à part, ou non compté).",
               "Ses muscles principaux, puis secondaires (en italique).",
               "Le nombre de séances et de séries où tu l'as fait.",
               "Ta dernière séance avec cet exercice : séries × répétitions (ou durée) et charge.",
               "L'évolution : la charge si tu en portes une, sinon les répétitions ou la durée par série ; en vert quand ça "
               "progresse. Un clic ouvre la séance.",
           ], max_w=176, max_h=110, cols=True,
           after=note("Une séance corrigée dans l'appli Garmin Connect se met à jour à la synchro suivante."))

    D.view("Volet de gauche › <b>Séance</b>", "Séance : le détail d'un renfo",
           "Ouvre une séance de musculation : ses exercices s'affichent sous le résumé, avec l'équilibre de la séance.",
           "seance-renfo", [(594, 75), (-14, 376), (-14, 513), (-14, 623), (-14, 786), (-14, 1117), (1382, 332)], [
               "Le résumé : durée, FC, charge, effets d'entraînement…",
               "Le bilan : séries, répétitions, tonnage et temps d'effort.",
               "L'équilibre avant / arrière de la séance : ici 12 séries devant, 12 derrière, 1 : 1, dans la cible.",
               "L'échelle, avec la bande verte de ta cible.",
               "Le conseil : ici, le bas du corps et le tronc penchent vers l'avant, et les exercices à ajouter.",
               "Chaque exercice porte son étiquette : avant, arrière, latéral (compté à part) ou non compté (l'échauffement).",
               "Les muscles travaillés pendant la séance.",
           ], max_w=176, max_h=112, cols=True,
           after=note("Pour une course ou une sortie à vélo, cette tuile s'efface d'elle-même."))

    # --- Réglages du renfo (0.8.3) ---
    D.page("Réglages › Entraînement › <b>Renfo</b>", "Tes réglages de renfo",
           "Nouveau dans la 0.8.3. Une rubrique rassemble tout ce qui concerne ton renfo : ce que tu vises par semaine, "
           "l'équilibre que tu cherches, et ce que Foulée met dans les séances qu'il te prépare.",
           row(shot("n83-reglages-renfo-light", max_w=74, max_h=138),
               ul([
               "<b>Séances par semaine</b> : ton objectif, celui qui sert de repère dans la vue Renfo et dans les conseils.",
               "<b>Ratio avant / arrière cible</b> : quatre profils. <i>Coureur</i> (de 1:1 à 1:2, visé 1:1,5), "
               "<i>Équilibré</i> (0,8 à 1,25), <i>Renfort arrière</i> (1,5 à 3) ou <i>Personnalisé</i>, où tu fixes toi-même "
               "les bornes. Le profil choisi change la bande verte de l'échelle, le verdict et les conseils, partout dans "
               "Foulée.",
               "<b>Les conseils qui vont avec</b> : chaque profil explique en une phrase ce qu'il vise et pour qui il est "
               "fait, et l'échelle montre tout de suite où tombe ta cible.",
               "<b>Ton niveau</b> : débutant, intermédiaire ou confirmé. Il règle le nombre de séries et de répétitions des "
               "séances que l'Atelier te propose.",
               "<b>Ton matériel</b> : élastique, haltères, kettlebell, barre, banc, TRX, step… Une séance proposée ne retient "
               "que des exercices que tu peux faire ; les autres sont signalés « matériel manquant ».",
               "<b>Récup entre les séries</b>, et <b>échauffement et étirements</b> : à ajouter ou non aux séances envoyées "
               "sur ta montre.",
               "<b>Tes jours de renfo</b> : les jours où tu fais ton renfo d'habitude, pour que Foulée propose la bonne date.",
               ]), grow=1))
