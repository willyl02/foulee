"""Partie 1 — Foulée, c'est quoi ? et Partie 2 — Installer Foulée."""
from kit import (KEY_PAGE, RELEASES, box, cards, chip, code, fr, howto, icon, legend, linkcard, note, row, shot, table, ul)


def part1(D):
    D.part("Foulée, c'est quoi ?", "Un tableau de bord pour coureurs, qui tourne sur ton PC : ta forme du jour, ton "
           "entraînement, ta récupération, ton plan et ton objectif course, à partir de ta montre Garmin.",
           ["Ce que Foulée fait, et ce qu'il ne fait pas",
            "Ce qu'il te faut pour commencer",
            "L'interface en un coup d'œil"],
           img="v-overview")

    # --- En bref ---
    grid = cards([
        ("Tes données restent chez toi", "Une base sur ton PC. Foulée ne contacte que Garmin (et Withings, Strava ou ton "
         "calendrier si tu les branches), GitHub pour les mises à jour, et le fond de carte.", "lock"),
        ("Des vues à ta main", "32 types de tuiles à ajouter, déplacer, redimensionner. Crée autant de vues que tu veux.", "layers"),
        ("Pensé pour le coureur", "VMA et allures, objectif course, charge et fraîcheur, effet d'entraînement de chaque "
         "séance, zones, records… et ton renfo, équilibré entre l'avant et l'arrière.", "run"),
        ("Ton plan d'entraînement", "Relie ton calendrier Garmin Connect : séances prévues et courses, face à ce que tu as "
         "vraiment fait.", "calendar"),
        ("Horaires décalés", "Matin, soir, repos : Foulée compare ton sommeil et ta récup selon ton poste de travail.", "briefcase"),
        ("Toute la famille", "Plusieurs profils, chacun ses données, ses vues, sa clé Garmin, avec un code si besoin.", "user"),
        ("Claude Desktop", "Pose tes questions en français à l'IA de Claude, qui lit tes données si tu l'y autorises.", "chat"),
        ("Ton club FFA", "Ton club, ta licence et le classement du club sur athle.fr, en un clic.", "club"),
        ("Aussi sur ton téléphone", "Installé sur un serveur à la maison, Foulée s'ouvre partout via Tailscale.", "laptop"),
        ("Withings et Strava", "Ta balance Withings, et tes séances Strava (Coros, Suunto, Polar, Apple…) avec leurs kudos.", "sync"),
        ("Un coach, si tu veux", "Ton coach te prépare tes séances et les envoie jusque sur ta montre. Sans coach aussi : "
         "l'Atelier te laisse les construire toi-même.", "dumbbell"),
        ("Gratuit, sans compte", "Pas d'abonnement, pas de compte Foulée, pas de pub, pas de serveur chez quelqu'un d'autre.", "check"),
    ], cls="three")
    needs = box("Il te faut", ul(["Une montre Garmin, synchronisée avec Garmin Connect.",
                                  "Un compte Garmin Connect, et ta clé API personnelle (gratuite, créée en une minute).",
                                  "Un PC sous Windows 10 ou 11, allumé assez souvent pour la synchro."]), "check")
    origin = box("", f'<p>{fr("Un projet personnel de William, coureur en horaires décalés, qui voulait voir sa forme, son "
                              "entraînement et sa récupération au même endroit, à sa façon. Fait par un coureur, pour des coureurs.")}</p>')
    D.page("En bref", "Foulée, c'est quoi ?",
           "Foulée récupère tes données Garmin (séances, sommeil, VFC, FC de repos, Body Battery…) grâce à ta clé API "
           "personnelle, et, si tu le veux, celles de ta balance Withings. Il les range dans une base sur ton PC et te les "
           "montre dans des tableaux de bord que tu composes.",
           grid + f'<div class="two"><div>{needs}</div><div>{origin}</div></div>')

    # --- L'interface ---
    D.page("L'interface", "L'interface en un coup d'œil",
           "Tes vues à gauche, leurs tuiles à droite. Clair le jour, sombre la nuit (pour les levers à 4 h).",
           shot("v-overview", [(1, 205, 170), (2, 175, 484), (3, 200, 582), (4, 110, 681), (5, 1255, 75), (6, 1530, 75),
                               (7, 955, 150), (8, 800, 150), (9, 30, 735), (10, 30, 867)], 182, 112)
           + legend([
               "Le volet de gauche : tes vues. Chacune répond à une question : ma forme, ma semaine, ma course…",
               "« Nouvelle vue » : crée-en autant que tu veux.",
               "Le site de ton club et tes sites externes (Campus Coach, Strava…), ouverts dans Foulée.",
               "L'Atelier, pour construire tes séances de course et de renfo (partie 5).",
               "« Modifier la vue » : ajoute, déplace et redimensionne les tuiles ; la période des graphiques est juste à côté.",
               "Plusieurs profils : chacun ses données, ses vues et ses réglages.",
               "Ta journée : ton poste, le compte à rebours de ta course, ton club, la dernière synchro.",
               "Le logo de ton club, dans le bandeau d'accueil.",
               "L'aide intégrée et le bouton « Un bug, une idée ? ».",
               "La synchro avec Garmin (et Withings, Strava, ton calendrier si tu les branches) : automatique, ou d'un clic.",
           ], cols=True))


def part2(D):
    D.part("Installer Foulée", "Cinq minutes, sans être administrateur, puis une dizaine de minutes pour le premier "
           "import. Ensuite, Foulée se synchronise tout seul.",
           ["Télécharger le fichier d'installation",
            "L'installation pas à pas, et l'avertissement de Windows",
            "Le premier lancement et le premier import",
            "Créer ta clé API Garmin, et la garder secrète",
            "Les mises à jour, et la désinstallation"],
           img="bienvenue")

    # --- Télécharger ---
    side = (legend([
        "La page des versions du projet, sur GitHub : la plus récente est en haut.",
        "Clique sur Foulee-Setup-0.8.3.exe (le numéro change à chaque version) : le téléchargement démarre, 37 Mo. Les "
        "autres fichiers (dont ceux pour Mac) ne servent pas à l'installation sur Windows.",
        "« Latest » : la dernière version stable. Tu veux les nouveautés avant tout le monde ? Coche « Recevoir les "
        "versions bêta » dans Réglages › Application › Mises à jour, et Foulée te proposera chaque nouvelle bêta.",
    ]) + linkcard("La page des versions de Foulée", RELEASES, "github.com/willyl02/foulee/releases",
                  "Pas besoin de compte GitHub pour télécharger.")
        + note("Ton navigateur hésite à garder le fichier parce qu'il est encore peu téléchargé ? Normal pour un petit "
               "projet : choisis « Conserver » dans le menu du téléchargement. Seulement pour un fichier venu de cette page."))
    D.page("Pour démarrer › <b>Télécharger</b>", "Télécharger Foulée",
           "Foulée s'installe à partir d'un seul fichier, « Foulee-Setup » suivi du numéro de version, publié sur la page "
           "du projet, sur GitHub. Il faut un PC sous Windows 10 ou 11 (ou, pour les plus aguerris, un petit serveur Linux "
           "à la maison : voir le README du projet).", side)

    # --- Installer ---
    steps = [
        (1, "Lance l'installation", fr("Double-clique sur le fichier téléchargé (Foulee-Setup-0.8.3.exe par exemple), dans "
                                       "ton dossier Téléchargements. Pas besoin d'être administrateur : Foulée s'installe "
                                       "pour toi seul, dans ton dossier utilisateur.")),
        (2, "« Windows a protégé votre ordinateur » ?",
         fr("Normal : l'installateur n'est pas signé (le certificat d'un éditeur est payant). Clique sur ")
         + chip("Informations complémentaires") + fr(", puis sur ") + chip("Exécuter quand même")
         + fr(". L'avertissement s'affiche parce que le fichier est peu téléchargé, pas parce qu'il serait dangereux.")),
        (3, "Deux cases, déjà cochées",
         fr("« Créer une icône sur le Bureau » et « Lancer Foulée à l'ouverture de session » : garde la seconde, c'est elle "
            "qui permet la synchro automatique toutes les 3 heures. Puis « Suivant » et « Installer ».")),
        (4, "« Terminer », et Foulée s'ouvre",
         fr("Dans ton navigateur, sur la page de bienvenue (page suivante). Son icône se range près de l'horloge, sous la "
            "flèche ^ si Windows la cache : un clic ouvre Foulée, un clic droit propose « Synchroniser maintenant » et "
            "« Quitter Foulée ».")),
    ]
    know = box("Bon à savoir", ul([
        "Foulée tourne en arrière-plan, sans fenêtre : pour l'ouvrir, clique sur son icône près de l'horloge, ou lance "
        "« Foulée » depuis le menu Démarrer.",
        "Tant qu'il tourne, la synchro se fait toute seule toutes les 3 heures (au réveil du PC si elle a été manquée).",
        "Foulée s'ouvre dans ton navigateur, mais tout reste sur ton PC : l'adresse commence par 127.0.0.1, ta machine.",
    ]))
    D.page("Pour démarrer › <b>Installer</b>", "Installer Foulée, pas à pas",
           "Cinq minutes, sans être administrateur. L'assistant d'installation est en français : il suffit presque de "
           "cliquer sur « Suivant ».", howto(steps) + know)

    # --- Premier lancement ---
    maj = box("Ensuite, les mises à jour viennent à toi",
              f'{shot("alerte", max_w=150, max_h=30)}<p>'
              + fr("Foulée regarde toutes les 3 heures si une nouvelle version est sortie. Si oui, ce message apparaît en "
                   "haut à droite : un clic montre les nouveautés, « Installer maintenant », et Foulée se relance une "
                   "minute plus tard. Tes données, ta clé et tes vues ne bougent pas.") + "</p>", "download")
    D.page("Pour démarrer › <b>Premier lancement</b>", "Premier lancement : la page de bienvenue",
           "À la première ouverture, Foulée te guide en trois étapes. Compte une dizaine de minutes, premier import compris.",
           row(shot("bienvenue", [(1, 22, 312), (2, 22, 819), (3, 22, 1237), (4, 1425, 1596)], 84, 112),
               legend([
               "Ta clé API Garmin : crée-la sur le site de Garmin, colle-la ici, puis « Tester et enregistrer ». Tout est "
               "expliqué page suivante.",
               "Le premier import : choisis depuis quand (2 ans conseillé). Compte quelques minutes ; tu peux utiliser "
               "Foulée pendant ce temps. Ensuite, la synchro se fait toute seule.",
               "Claude Desktop, facultatif : un bouton relie Foulée à Claude, pour lui poser tes questions en français.",
               "Pas de clé sous la main ? Une démo complète, avec des données fictives. Le bandeau « Quitter la démo » te "
               "ramène ensuite à tes vraies données.",
           ]), grow=1) + maj
           + note("Désinstaller : Paramètres de Windows › Applications › Foulée. Tu choisis alors de garder tes données "
                  "(pour réinstaller plus tard) ou de les effacer.", "trash"))

    # --- Clé API ---
    steps = [
        (1, "Ouvre la page « API personnelle » de Garmin Connect",
         fr("Sur le site de Garmin Connect, connecté à ton compte : ") + code("connect.garmin.com/app/settings/personalApiToken")
         + fr(" (ou Paramètres › API personnelle). Le lien de la page de bienvenue de Foulée y mène directement.")),
        (2, "Crée ta clé", fr("« Créer une clé », accepte les conditions, choisis la durée (1 an conseillé), puis « Créer ».")),
        (3, "Copie-la tout de suite !",
         fr("Avec le bouton ") + chip("Copier") + fr(" de Garmin. La clé ne s'affiche qu'une seule fois, juste après sa "
            "création : une fois la page fermée, impossible de la revoir, il faudra en créer une nouvelle. Pour la garder, "
            "range-la dans ton gestionnaire de mots de passe, nulle part ailleurs.")),
        (4, "Colle-la dans Foulée",
         fr("Étape 1 de la page de bienvenue (ou Réglages › Connexions › Clé API Garmin) : colle la clé, qui commence par ")
         + code("GCDC_") + fr(", puis ") + chip("Tester et enregistrer")
         + fr(". Foulée la fait vérifier par Garmin avant de l'enregistrer, et la synchro peut commencer.")),
    ]
    secret = box("Garde-la secrète",
                 f'<p>{fr("Elle ouvre tes données Garmin, comme un mot de passe. Personne n’a besoin de la connaître, pas "
                           "même William : ne l’envoie à personne, ni dans un message ni dans un rapport de bug, et pas de "
                           "capture d’écran tant qu’elle est affichée. Foulée la range dans le Gestionnaire d’identification "
                           "de Windows et ne la montre plus jamais.")}</p>', "lock", cls="warn")
    expire = box("Expirée, perdue ou régénérée ?",
                 f'<p>{fr("Garmin prévient par e-mail une semaine environ avant l’expiration. Crée une nouvelle clé sur la "
                           "même page (l’ancienne cesse de fonctionner), puis Réglages › Connexions › Clé API Garmin › "
                           "« Remplacer la clé ». Si Garmin refuse ta clé, un bandeau rouge te le dit et la synchro se met "
                           "en pause.")}</p>', "reset")
    D.page("Pour démarrer › <b>Clé API Garmin</b>", "Ta clé API Garmin",
           "C'est elle qui autorise Foulée à lire tes données chez Garmin : séances, sommeil, VFC… Gratuite et personnelle, "
           "elle se crée en une minute sur le site de Garmin Connect. Le plus simple : depuis le PC où tu as installé Foulée.",
           howto(steps, "compact")
           + f'<div class="two"><div>{secret}</div><div>{expire}</div></div>'
           + note("Toute la famille ? Chaque profil a sa propre clé, créée avec son propre compte Garmin. Et une même clé "
                  "sert à la fois sur ton PC et sur un serveur.", "user"))
