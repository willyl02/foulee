"""Partie 5 — L'Atelier (construire ses séances) et Partie 6 — Tes vues et tes réglages."""
from kit import box, cards, chip, code, fr, howto, icon, legend, note, row, shot, table, two, ul

ZONES = [("Z1", "Échauffement", "#9ea8a3"), ("Z2", "Facile", "#2a78d6"), ("Z3", "Aérobie", "#13a06e"),
         ("Z4", "Seuil", "#f08a1c"), ("Z5", "Maximum", "#d3263a")]


def zbar():
    return '<div class="zbar">' + "".join(
        f'<div style="background:{c}"><b>{z}</b><span>{fr(n)}</span></div>' for z, n, c in ZONES) + "</div>"


def part5(D):
    D.part("L'Atelier : tes séances", "Nouveau dans la 0.8.3. Construire une séance de course ou de renfo comme un coach "
           "le ferait, la garder dans ta bibliothèque, et l'envoyer sur ta montre à la date de ton choix.",
           ["Une séance de course : bloc par bloc, avec les allures de ta VMA",
            "Une séance de renfo : à partir d'un modèle, ou de zéro",
            "Reprendre une séance, la modifier, l'enregistrer sous un autre nom",
            "L'envoi sur ta montre, à la date que tu choisis",
            "Et si tu n'as pas de coach : le compte « sans coach »"],
           img="n83-atelier-course")

    D.page("Volet de gauche › <b>Atelier</b>", "L'Atelier, en deux onglets",
           "L'Atelier s'ouvre depuis le volet de gauche. Deux onglets : « Course » pour les séances de course à pied, "
           "« Renfo » pour la musculation. Dans les deux cas, le principe est le même : tu composes, tu gardes, tu envoies.",
           row(shot("n83-rail", max_w=26, max_h=92, cap="Dans le volet de gauche"),
               howto([
                   (1, "Compose ta séance", fr("Un titre, puis des blocs : échauffement, répétitions, récupération, retour "
                                               "au calme. Chaque bloc a sa durée (ou sa distance) et son intensité.")),
                   (2, "Regarde l'aperçu", fr("Foulée affiche la séance comme ta montre la montrera, avec les allures "
                                              "calculées sur ta VMA, et le temps total.")),
                   (3, "Garde-la dans ta bibliothèque", fr("« Enregistrer » la range avec tes autres séances. "
                                                           "« Enregistrer sous » en fait une copie sous un nouveau nom : "
                                                           "idéal pour décliner une séance qui marche bien.")),
                   (4, "Envoie-la sur ta montre", fr("Choisis la date : la séance arrive dans ton calendrier Garmin, et ta "
                                                     "montre l'a à sa prochaine synchro. Sans relais, un fichier .fit fait "
                                                     "le même travail par câble.")),
               ]), grow=1)
           + note("L'Atelier ne remplace pas ton coach : si tu en as un dans Foulée, ses séances continuent d'arriver dans "
                  "« Aujourd'hui ». L'Atelier sert à faire les tiennes, en plus ou à la place."))

    D.page("Atelier › <b>Course</b>", "Une séance de course, bloc par bloc",
           "Comme un coach : des blocs mis bout à bout, avec une intensité donnée en pourcentage de ta VMA, en allure ou "
           "en zone de FC. Foulée traduit tout en allures réelles.",
           shot("n83-atelier-course", max_w=170, max_h=116,
                cap="Une séance de VMA courte : échauffement, 2 × (6 × 30 s / 30 s), retour au calme.")
           + ul([
               "<b>Les blocs</b> : échauffement, effort, récupération, répétitions (un groupe qui se répète), retour au calme.",
               "<b>L'intensité</b> : en pourcentage de ta VMA, en allure au kilomètre, ou en zone de fréquence cardiaque. "
               "L'aperçu montre toujours l'allure qui en découle, d'après ta VMA du moment.",
               "<b>Des exemples prêts à partir</b> : VMA courte, 30/30, seuil, côtes, sortie longue… À prendre tel quel, ou "
               "à modifier.",
               "<b>Le total</b> : durée et distance estimées, pour vérifier que la séance tient dans ton créneau.",
           ]))

    D.page("Atelier › <b>Renfo</b>", "Une séance de renfo, à partir d'un modèle",
           "Sept séances toutes faites, choisies pour les coureurs, et réglées sur ton niveau et ton matériel "
           "(Réglages › Entraînement › Renfo). Tu les prends telles quelles, ou tu les modifies.",
           two(shot("n83-atelier-renfo", max_w=86, max_h=78, cap="Les modèles, et l'équilibre de la séance"),
               shot("n83-atelier-renfo-done", max_w=86, max_h=78, cap="La séance composée, prête à envoyer"))
           + ul([
               "<b>Les modèles</b> : chaîne postérieure, bas du corps, tronc, haut du corps, corps entier, séance courte, "
               "séance d'avant-course.",
               "<b>L'équilibre en direct</b> : à chaque exercice ajouté ou retiré, Foulée recalcule le rapport avant / "
               "arrière de la séance et le place sur ton échelle cible.",
               "<b>Chaque exercice</b> : séries, répétitions (ou durée), récup, et le matériel qu'il demande. Un exercice "
               "que ton matériel ne permet pas est signalé.",
               "<b>Échauffement et étirements</b> : ajoutés au début et à la fin si tu l'as choisi dans tes réglages.",
               "<b>Ta bibliothèque</b> : jusqu'à 60 séances gardées, à rouvrir, modifier et réenregistrer sous un autre nom.",
           ]))

    D.page("Atelier › <b>Envoyer</b>", "Envoyer ta séance sur ta montre",
           "Deux chemins, selon que tu passes par le relais de Foulée Coach ou par un câble. Dans les deux cas, la séance "
           "arrive avec ses allures et ses répétitions, et ta montre te guide pendant l'effort.",
           two(box("Sans câble, à la date de ton choix",
                   f'<p>{fr("« Envoyer sur ma montre » dépose la séance dans ton calendrier Garmin Connect, au jour que tu "
                             "choisis. Ta montre la récupère à sa prochaine synchro, et elle apparaît aussi dans "
                             "« Aujourd’hui » le jour venu. Il faut pour cela un compte sur le relais : celui que ton coach "
                             "t’a donné, ou un compte « sans coach » (page suivante).")}</p>', "watch"),
               box("Par câble, avec un fichier .fit",
                   f'<p>{fr("« Télécharger le .fit » te donne un fichier à copier dans le dossier GARMIN\\NewFiles de ta "
                             "montre branchée en USB. Aucun compte, aucun relais : ça marche toujours, mais il faut le "
                             "câble.")}</p>', "download"))
           + howto([
               (1, "Choisis la date", fr("Foulée propose le prochain jour qui colle à tes habitudes (tes jours de renfo, "
                                         "pour une séance de renfo). Tu peux en choisir un autre.")),
               (2, "Envoie", fr("Un message confirme le dépôt dans ton calendrier Garmin, avec la date.")),
               (3, "Synchronise ta montre", fr("Ouvre l'appli Garmin Connect sur ton téléphone, ou attends la synchro "
                                               "automatique de la montre : la séance est là, dans les entraînements du jour.")),
           ], "compact"))

    D.page("Réglages › Club et coach › <b>Sans coach</b>", "Pas de coach ? Le compte « sans coach »",
           "Nouveau dans la 0.8.3. L'envoi sur la montre passe par le relais de Foulée Coach. Pour en profiter sans avoir "
           "de coach, tu peux y ouvrir un compte « sans coach » : il ne sert qu'à ça.",
           row(shot("n83-coach-solo", max_w=96, max_h=70, cap="Réglages › Club et coach › Mon coach"),
               ul([
                   "<b>Ce que c'est</b> : un compte à toi sur le relais, avec un identifiant et un mot de passe. Il te "
                   "permet de relier ta montre et d'envoyer tes séances, et rien d'autre.",
                   "<b>Ce qu'il ne fait pas</b> : pas de coach, pas de groupe, pas de partage, pas de messages. Personne "
                   "ne voit tes données.",
                   "<b>Relier ta montre</b> : une seule fois, en autorisant l'appli Garmin du relais. Tu peux délier quand "
                   "tu veux.",
                   "<b>Si tu trouves un coach plus tard</b> : « J'ai maintenant un coach », tu colles son code "
                   "d'invitation, et ton compte devient un compte d'élève — sans rien perdre.",
               ]), grow=1)
           + note("Tes séances passent par le relais pour être déposées chez Garmin, mais rien n'y est gardé : ni tes "
                  "mesures, ni ton historique."))


def part6(D):
    D.part("Tes vues et tes réglages", "Foulée se compose : autant de vues que tu veux, chacune avec ses tuiles, et des "
           "réglages rangés par thème avec une recherche.",
           ["Créer une vue, y ajouter et ranger des tuiles",
            "Les réglages par thème, et la recherche",
            "Les zones de FC, et les couleurs des zones",
            "La logothèque : le logo de ton club, partout dans Foulée",
            "Le site de ton club dans Foulée, l'aide intégrée et tes retours"],
           img="beta-reglages")

    steps = [
        (1, "Crée la vue", fr("« + Nouvelle vue » dans le volet de gauche : un nom, une icône.")),
        (2, "Ajoute des tuiles", fr("« Modifier la vue », puis « Ajouter une tuile » : 32 types au choix (chiffre clé, "
                                    "courbe ou barres, nuage de points, calendrier, zones, carte, liste des séances, note…).")),
        (3, "Arrange-les", fr("Glisse les tuiles pour les déplacer, choisis leur largeur et leur hauteur, règle-les avec la "
                               "roue dentée.")),
        (4, "C'est enregistré", fr("Tout s'enregistre au fur et à mesure. Et « Restaurer les vues d'origine » remet les vues "
                                    "de départ, sans toucher aux tiennes.")),
    ]
    D.page("Volet de gauche › <b>Tes vues</b>", "Tes vues à toi",
           "Les vues livrées avec Foulée sont faites avec les mêmes tuiles que les tiennes : rien ne t'empêche de les "
           "modifier, ou d'en créer d'autres.",
           shot("idees", [(1, 134, 182)], 176, 48)
           + legend(["Une tuile Note : tes idées, tes rappels."])
           + howto(steps))

    D.page("<b>Réglages</b>", "Des réglages rangés par thème",
           "Cinq thèmes, comme dans les réglages de Windows ou du Mac, et une recherche qui va droit à la bonne rubrique.",
           shot("beta-reglages", [(1, 520, 720), (2, 1080, 350), (3, 380, 1006)], 176, 98)
           + legend([
               "Cinq thèmes : Moi, Entraînement, Connexions, Club et coach, Application.",
               "Le thème choisi et ses rubriques (ici Connexions : Garmin, Withings, Strava, calendrier). Chaque changement "
               "s'enregistre tout seul.",
               "La colonne de gauche en trois parties, séparées par un trait : tes vues, l'application partenaire, ta page "
               "coach. Glisse une vue pour changer l'ordre (ou Alt + flèche).",
           ])
           + note("Sur le téléphone, la liste des thèmes d'abord, puis le détail. Une flèche, en bas à droite, remonte en "
                  "haut de la page."))

    D.page("Réglages › Entraînement › <b>Zones FC</b>", "Tes zones de FC, et leurs couleurs",
           "Nouveau dans la 0.8.3 : les zones prennent les couleurs de Garmin Connect, et tu peux en changer. Partout dans "
           "Foulée — tableaux du temps par zone, graphiques, barres — les mêmes couleurs veulent dire la même chose.",
           zbar()
           + row(shot("n83l-reglages-zones-light", max_w=94, max_h=64, cap="Réglages › Entraînement › Zones FC"),
                 ul([
                     "<b>Les bornes</b> : par pourcentage de ta FC max, ou de ta réserve cardiaque (FC max moins FC de "
                     "repos). Foulée dit à chaque fois quelle méthode il applique.",
                     "<b>Les couleurs</b> : celles de Garmin par défaut (gris, bleu, vert, orange, rouge), les anciens "
                     "bleus de Foulée, ou les tiennes.",
                     "<b>Clair et sombre</b> : chaque jeu a sa version pour le thème clair et pour le thème sombre, pour "
                     "rester lisible la nuit.",
                 ]), grow=1))

    D.page("Réglages › Club et coach › <b>Logothèque</b>", "La logothèque : le logo de ton club",
           "Nouveau dans la 0.8.3. Les logos vivent dans une logothèque : ceux livrés avec Foulée, et ceux que tu importes "
           "et nommes. Tu choisis ensuite lequel s'affiche dans « Mon club », dans le bandeau d'accueil et pour le site de "
           "ton club.",
           two(shot("n83l-club-import-1", max_w=84, max_h=52, cap="Le menu déroulant de la logothèque"),
               shot("n83l-home-light", max_w=84, max_h=52, cap="Le logo dans le bandeau d'accueil"))
           + ul([
               "<b>Importer</b> : un PNG à fond transparent, carré, 500 × 500 pixels de préférence. Foulée garde la "
               "transparence, retire les marges vides et le range sur ton PC.",
               "<b>Le nommer</b> : le nom que tu donnes apparaît dans le menu déroulant, et le logo reste disponible pour "
               "les autres emplacements.",
               "<b>Trois emplacements</b> : la vue « Mon club », le bandeau d'accueil, et l'entrée du site de ton club "
               "(« Club en ligne »). Chacun choisit son logo dans la même liste.",
               "<b>Sauvegarde et restauration</b> : les logos importés partent avec l'export de tes réglages, et revient "
               "avec lui.",
           ]))

    D.view("Volet de gauche › <b>Club en ligne</b>", "Le site de ton club, dans Foulée",
           "Réglages › Club et coach › Application partenaire. Une case, et le site de ton club s'ouvre dans Foulée, avec "
           "son entrée dans la colonne de gauche.",
           "b-partenaire", [(408, 1008), (1988, 177), (2120, 177), (2373, 177), (2628, 177), (1360, 952)], [
               "Son entrée, entre deux traits, sous « Nouvelle vue ».",
               "Précédent, suivant…",
               "… et recharger.",
               "« Ouvrir dans le navigateur », si un site refuse de s'afficher dans Foulée.",
               "Le nom et l'adresse : par défaut Club en ligne, mais tu peux viser une page précise (les entraînements, "
               "par exemple) ou un autre site.",
               "Le site : tu t'y connectes avec ton compte, comme d'habitude.",
           ], max_w=176, max_h=104, cols=True)

    D.page("Volet de gauche › <b>Aide et FAQ</b> · <b>Un bug, une idée ?</b>", "L'aide intégrée, et un bouton pour tes retours",
           "Foulée embarque son aide : 127 questions, rangées par thème, avec une recherche. Et un bouton pour dire ce qui "
           "coince.",
           two(shot("aide", [(1, 1200, 165), (2, 1152, 279)], 84, 46),
               shot("retours", [(3, 422, 168), (4, 242, 957)], 84, 90))
           + legend([
               "Une recherche dans toutes les questions de l'aide.",
               "Les questions rangées par thème : clé Garmin, synchro, calculs, téléphone, vie privée, coach et élèves…",
               "Avant d'écrire : un coup d'œil à l'aide et aux sujets déjà ouverts sur GitHub.",
               "Tu racontes : un bug, une idée ou une question. Foulée prépare le message avec sa version, ton système et "
               "l'état de la synchro (jamais ta clé ni tes mesures). Tu l'envoies sur GitHub, ou par e-mail.",
           ], cols=True))
