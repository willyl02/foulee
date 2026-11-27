"""Partie 10 — Côté coach. (L'administration du relais en SSH n'est volontairement pas dans ce manuel.)"""
from kit import HOST, box, fr, howto, icon, legend, note, numbered, row, shot, table, two, ul


def part10(D):
    D.part("Côté coach", "Te relier au relais du club, inviter tes élèves, suivre les séances qu'ils partagent, leur écrire "
           "et leur proposer les prochaines, jusque sur leur montre.",
           ["Te connecter au relais, et inviter tes élèves",
            "« Mes élèves », tes groupes de niveau et ta bibliothèque de séances",
            "La fiche d'un élève : son calendrier, ses fractions",
            "Proposer une séance, et l'envoyer sur la montre de tes élèves",
            "Les messages, les ressentis, les notifications, et la gestion du groupe"],
           img="c-groupes")

    D.page("Côté coach › <b>Étape 1</b>", "Te connecter au relais",
           "Foulée installé comme n'importe quel coureur (partie 2) ; ta clé Garmin est facultative, elle ne sert qu'à tes "
           "propres séances. Avec le compte coach que l'administrateur du relais t'a créé, une seule fois : ensuite, Foulée "
           "reste relié.",
           shot("connexion-coach", [(3, 499, 476), (4, 1019, 476), (5, 1534, 476), (6, 339, 587)], 160, 70,
                cap="Réglages › Club et coach › Coach et élèves › « J'ai déjà un compte », rempli avec un exemple.")
           + howto([
               (1, "Ouvre Réglages › Club et coach", fr("La rubrique « Coach et élèves ». Depuis le PC où Foulée est installé "
                                                        "(ou par Tailscale) : un mot de passe ne doit pas circuler sur le "
                                                        "réseau de la maison.")),
               (2, "Choisis « J'ai déjà un compte »", ""),
               (3, "L'adresse du relais", fr(f"{HOST}.")),
               (4, "Ton identifiant", fr("Celui que l'administrateur t'a donné, par exemple prenom.nom.")),
               (5, "Ton mot de passe provisoire", ""),
               (6, "« Me connecter »", fr("« Mes élèves » s'ajoute à ta colonne, avec la vue « Calendrier ».")),
               (7, "Change tout de suite ton mot de passe", fr("Même rubrique, « Changer le mot de passe » : 10 caractères "
                                                               "au moins, rangé dans ton gestionnaire de mots de passe.")),
           ], "compact")
           + shot("reglages-coach", max_w=122, max_h=32, cap="Une fois relié : « Mes élèves », changer le mot de passe, se déconnecter."))

    tags = [("Séances des 4 dernières semaines, en résumé", "oui, avec son accord", "ok"),
            ("Objectif de course et VMA", "oui, avec son accord", "ok"),
            ("Tracé GPS simplifié (départ et arrivée masqués)", "en option", "opt"),
            ("Sommeil, VFC, FC au repos ; poids", "en option", "opt"),
            ("Séances venues de Strava, clé Garmin, reste de l'historique", "jamais", "no")]
    D.page("Côté coach › <b>Étape 2</b>", "Inviter tes élèves",
           "Un code d'invitation par élève, donné de la main à la main : pas d'adresse e-mail, pas de formulaire en ligne.",
           shot("invitation", [(1, 300, 166)], 182, 34, cap="« Mes élèves » › « Inviter un élève ».")
           + howto([
               (1, "« Inviter un élève » › « Créer un code d'invitation »", fr("Un code comme K7MP-Q3XR : il sert une seule "
                                                                               "fois, et vaut 7 jours. Les codes en cours "
                                                                               "restent listés ; un code inutile s'annule "
                                                                               "d'un clic.")),
               (2, "« Copier », et envoie-le", fr(f"Le bouton copie un message tout prêt : « Relais : {HOST} · Code "
                                                  "d'invitation : … ». Colle-le dans un SMS ou un e-mail, ou donne-le à "
                                                  "l'entraînement, avec ce manuel.")),
               (3, "Ton élève rejoint le groupe", fr("Dans son Foulée : « J'ai un code d'invitation » (partie 9). Il choisit "
                                                     "son identifiant, son mot de passe, puis ce qu'il partage avec toi.")),
               (4, "Il apparaît dans « Mes élèves »", fr("Ses séances arrivent après sa prochaine synchro, ou dès qu'il "
                                                         "clique « Envoyer maintenant ».")),
           ])
           + f'<h2>{icon("lock")}{fr("Ce que tu vois de tes élèves : ce qu’ils cochent")}</h2>'
           + table(["Donnée de l'élève", "Pour toi"], [(fr(a), f'<span class="tag {c}">{fr(b)}</span>') for a, b, c in tags])
           + note("Sans son objectif et sa VMA, Foulée ne peut pas calculer ses allures : ses séances proposées s'affichent "
                  "alors en % de VMA."))

    D.page("Côté coach › <b>Mes élèves</b>", "Mes élèves : tout le groupe",
           "Ta page d'accueil de coach, rangée par groupe de niveau. Elle se met à jour toute seule quand un élève synchronise.",
           shot("c-groupes", numbered([(40, 390), (40, 576), (900, 670), (840, 900), (1200, 992), (1310, 1090), (1000, 1156),
                                       (1300, 1248), (1590, 134)]), 182, 116,
                cap="« Mes élèves », rangée par groupe (profils de démonstration).")
           + legend(["Les chiffres de la semaine : séances faites, messages non lus, prochaine course, élèves à surveiller.",
                     "Ranger par groupe, par VMA ou par nom. « Groupes de niveau », à droite, mène à leurs réglages.",
                     "Un groupe : sa plage de VMA et ses élèves. « Proposer au groupe » prépare une séance pour tous.",
                     "Pour chaque élève : sa dernière séance, et quand ses données sont arrivées.",
                     "Sa semaine jour par jour : fait (vert), manqué (rouge), prévu (cadre) ; en bleu, ta séance.",
                     "Ses chiffres : la semaine, les séances prévues faites, la charge sur 7 jours, sa VMA (« test » : celle "
                     "de ton test au club).",
                     "Son objectif et le compte à rebours.",
                     "Sa fiche, un message, ou lui proposer une séance.",
                     "Le fil du groupe et « Inviter un élève »."], cols=True)
           + note("Un élève qui partage ses séances mais n'en a pas fait depuis 5 jours ou plus est signalé : « 5 jours sans "
                  "séance ».", "warning"))

    D.page("Côté coach › <b>Groupes de niveau</b>", "Tes groupes de niveau",
           "Mes élèves › Groupes et séances types : range tes élèves par VMA, pour leur proposer la bonne séance d'un seul geste.",
           shot("c-niveaux", numbered([(60, 60), (1420, 60), (2020, 60), (240, 200), (60, 600)]), 182, 92,
                cap="Les groupes de niveau (profils de démonstration).")
           + legend(["Tes groupes : un nom, une VMA mini et maxi, une couleur. Un élève va dans le premier groupe dont les "
                     "bornes contiennent sa VMA.",
                     "« Proposer des groupes » : Foulée en propose trois d'après les VMA de tes élèves.",
                     "« Enregistrer » : l'aperçu montre qui va où avant.",
                     "VMA mini comprise, maxi non comprise ; une case vide ne limite pas.",
                     "L'aperçu : chaque groupe, ses élèves et leur VMA."], cols=True)
           + row(shot("c-vma", [(6, 640, 70), (7, 1680, 70)], 106, 72),
                 legend(["La VMA de ton test au club (VAMEVAL, demi-Cooper…) passe avant celle que l'élève partage : c'est "
                         "elle qui le range, et elle sert à ses allures s'il n'a pas de VMA dans Foulée.",
                         "Tu peux aussi placer un élève à la main dans un groupe (retour de blessure…)."], start=6), grow=1))

    D.page("Côté coach › <b>Bibliothèque</b>", "Ta bibliothèque de séances",
           "Au même endroit : toutes tes séances types, avec leur esquisse. Pour reproposer une séance qui a marché, ou en "
           "faire une variante.",
           shot("c-biblio", numbered([(60, 60), (1690, 60), (980, 230), (1380, 230), (1700, 230), (1900, 230)]), 182, 104,
                cap="La bibliothèque de séances (profils de démonstration).")
           + legend(["Tes séances types : le titre, le déroulé, la durée, et l'esquisse (une barre par étape, aussi haute "
                     "que son intensité, aux couleurs des allures).",
                     "« Nouvelle séance type » : la composer sans l'envoyer.",
                     "« Proposer » : l'éditeur s'ouvre avec la séance, à envoyer à un élève ou à un groupe.",
                     "« Modifier » la séance type.",
                     "« Renommer » sur place.",
                     "« Dupliquer » pour faire une variante ; la corbeille la retire."], cols=True)
           + note("Une séance te plaît dans l'éditeur ? « Enregistrer comme modèle » la range ici. Tes séances types sont sur "
                  "le relais : tu les retrouves sur un autre PC. (L'éditeur est le même que celui de l'Atelier, partie 5.)",
                  "layers"))

    D.page("Côté coach › <b>La fiche d'un élève</b>", "La fiche d'un élève",
           "Un clic sur un élève : sa semaine face à ce que tu as prévu, ses séances, son objectif, et ce qu'il a choisi de "
           "partager.",
           shot("fiche", numbered([(1262, 135), (918, 362), (575, 585), (1215, 375), (1328, 658), (1545, 870), (1462, 968),
                                   (690, 186)]), 182, 120, cap="La fiche d'une élève, chez son coach.")
           + legend(["Ce qu'il partage, et quand ses données sont arrivées.",
                     "Sa semaine : fait, manqué, et tes séances proposées en pointillé bleu. Les flèches changent de semaine.",
                     "Ses séances des 4 dernières semaines : un clic ouvre le détail (tours, renfo, tracé) et un fil pour en parler.",
                     "Son objectif : course, date, temps visé, allure et % de VMA.",
                     "Le bilan des 4 dernières semaines.",
                     "Tes séances proposées : modifier, supprimer ; plus bas, sa forme, s'il la partage.",
                     "Le fichier .fit de la séance, avec ses allures à lui.",
                     "Lui écrire, ou lui proposer une séance."], cols=True))

    D.page("Côté coach › <b>La fiche d'un élève</b>", "Son calendrier, ses fractions",
           "Sur la fiche de chaque élève, deux outils pour suivre son plan et lire ses séances.",
           row(shot("c-calendrier", max_w=88, max_h=120),
               ul(["« Son calendrier » : quatre semaines passées, celle-ci et quatre à venir. Son plan Garmin et tes séances, "
                   "avec leur esquisse ; ce qu'il a fait (un clic ouvre la séance) ; ses courses visées.",
                   "Deux séances prévues le même jour (son plan et la tienne) ? Chaque séance faite va à celle qui lui "
                   "ressemble : ta séance n'est plus marquée « faite » par erreur.",
                   "Ta séance envoyée sur sa montre revient aussi par son calendrier Garmin : elle ne s'affiche qu'une fois.",
                   "Il se replie d'un clic sur son titre. L'élève a le même dans « Mon coach »."]), grow=1)
           + shot("e-analyse", max_w=182, max_h=62, cap="Une séance en détail : l'analyse fraction par fraction.")
           + note("Une colonne par fraction, aussi large que sa durée, avec son temps, son allure, sa FC moyenne, sa zone et la "
                  "part passée dans cette zone, au-dessus des courbes d'allure et de FC.", "activity"))

    D.page("Côté coach › <b>Proposer une séance</b>", "Proposer une séance",
           "Décris-la une fois en % de VMA ou en zone de FC : chaque élève la reçoit avec ses allures à lui, dans « Mon "
           "coach », dans son calendrier et jusque sur sa montre.",
           row(shot("c-proposer", numbered([(190, 378), (40, 440), (230, 974), (1030, 1458), (740, 1902), (1566, 378),
                                            (1550, 806), (1540, 1584), (2020, 134)]), 100, 150,
                    cap="« Proposer une séance » (profils de démonstration)."),
               legend(["Pour qui : un ou plusieurs élèves, avec leur VMA et leur groupe.",
                       "Un clic sur un groupe coche tous ses élèves.",
                       "La date, le sport, le titre, puis le déroulé en blocs : échauffement, corps de séance, retour au "
                       "calme ; durée ou distance, répétitions, % de VMA ou zone de FC, récupération. Et ta consigne.",
                       "« libre (Lap) » : sur la montre, l'étape dure jusqu'à ce que l'élève appuie sur Lap.",
                       "La durée totale et la distance estimées.",
                       "Les allures de chacun, calculées avec sa VMA.",
                       "Ce que l'élève verra.",
                       "Partir d'une séance de ta bibliothèque ou d'un exemple.",
                       "« Envoyer à … » : elle arrive chez chaque élève à sa prochaine synchro, ou dès qu'il ouvre « Mon "
                       "coach ». Modifiée plus tard, elle se met à jour chez lui, et sur sa montre."]), grow=1))

    D.page("Côté coach › <b>Sur la montre</b>", "Sur la montre de tes élèves",
           "Les élèves qui ont relié leur compte Garmin reçoivent tes séances directement sur leur montre, dans leur "
           "calendrier Garmin, avec leurs allures à eux.",
           shot("coach-montre-proposer", [(1, 270, 130), (2, 975, 224)], 182, 40, cap="« Proposer une séance », rubrique « Pour qui ».")
           + legend(["La petite montre verte : l'élève a relié sa montre Garmin et te laisse y envoyer tes séances.",
                     "« Envoyer aussi sur leur montre Garmin » : cochée d'office."], cols=True)
           + row(shot("coach-montre-fiche", [(3, 781, 104), (4, 837, 314)], 100, 52, cap="Sur la fiche d'une élève."),
                 legend(["En vert : la séance est déjà sur sa montre (survole pour savoir quand, et qui l'a envoyée).",
                         "Le bouton montre : l'envoyer, ou la renvoyer, sur sa montre."], start=3), grow=1)
           + note("Une séance modifiée est renvoyée toute seule sur sa montre ; supprimée, elle quitte aussi son calendrier "
                  "Garmin. Le message de confirmation te dit pour qui c'est parti, et qui n'a pas relié sa montre.", "sync")
           + two(box("L'élève garde la main",
                     f'<p>{fr("C’est lui qui relie son compte Garmin, depuis « Mon coach ». Il choisit si tu peux envoyer "
                               "pour lui (oui par défaut), et peut délier son compte à tout moment.")}</p>', "lock"),
                 box("Pas encore relié ?",
                     f'<p>{fr("Rien ne change pour lui : la séance est dans « Mon coach » et dans son calendrier, et le "
                               "fichier .fit reste là (câble USB). Tu peux le télécharger pour lui depuis sa fiche.")}</p>',
                     "download")))

    D.page("Côté coach › <b>Messages</b>", "Les messages",
           "Une conversation avec chaque élève, le fil du groupe, et un fil sous chaque séance partagée. Foulée relève le "
           "relais toutes les minutes.",
           shot("messages-main", numbered([(355, 248), (355, 365), (1110, 455)]), 136, 94, cap="Les messages, chez le coach.")
           + legend(["Le fil du groupe, toujours en tête : annonces, rendez-vous. Épingle un message : il reste en haut pour "
                     "tout le monde.",
                     "Une conversation par élève ; plus bas, les fils sous les séances.",
                     "La conversation ouverte : tes messages à droite, ceux de l'élève à gauche."])
           + shot("groupe", max_w=112, max_h=52, cap="Le fil du groupe : le message du coach est marqué « coach ».")
           + note("Un badge rouge dans la colonne compte les messages non lus. Chacun efface ses propres messages ; tu peux "
                  "effacer ceux de ton groupe.", "chat"))

    D.page("Côté coach › <b>Ressentis et notifications</b>", "Son ressenti, tes notifications",
           "Après sa séance, ton élève note son ressenti et te l'envoie ; et ton téléphone te prévient quand un élève "
           "t'écrit, même quand Foulée est fermé.",
           row(shot("c-messages", max_w=108, max_h=84, cap="Le ressenti d'une élève, dans votre conversation."),
               ul(["Dans « Ma séance du jour », l'élève met en face la séance faite et la séance prévue, note son ressenti de "
                   "1 à 10 et ajoute un mot.",
                   "« Envoyer à mon coach » : tu le reçois dans votre conversation, avec la séance et ses chiffres.",
                   "Tu lui réponds directement, sur place."]), grow=1)
           + row(shot("c-notif", max_w=72, max_h=84),
                 howto([
                     (1, "Réglages › Club et coach › Notifications", fr("La rubrique apparaît dès que tu es relié au relais.")),
                     (2, "Installe ntfy sur ton téléphone", fr("Une appli gratuite, sans compte ni publicité.")),
                     (3, "Scanne le QR code, puis l'essai", fr("Ton sujet est à toi : qui le connaît lit tes notifications.")),
                     (4, "Les heures calmes", fr("Rien la nuit : la notification attend la fin de la plage.")),
                 ], "compact"), grow=1))

    D.page("Côté coach › <b>Au quotidien</b>", "Gérer le groupe, au quotidien",
           "Les gestes à connaître une fois que le groupe tourne.",
           two(box("Retirer un élève",
                   f'<p>{fr("« Mes élèves » › « Gérer les comptes du groupe » › « Retirer » : son compte, ce qu’il a partagé "
                             "et vos messages sont effacés du relais. Ses données restent dans son Foulée ; pour revenir, il "
                             "lui faudra un nouveau code.")}</p>', "trash")
               + box("Un élève a oublié son mot de passe",
                     f'<p>{fr("Préviens l’administrateur du relais : il le réinitialise et lui donne un mot de passe "
                               "provisoire. L’élève se reconnecte (« J’ai déjà un compte »), puis le change.")}</p>', "key"),
               box("Nouveau PC, réinstallation",
                   f'<p>{fr("« J’ai déjà un compte », avec ton identifiant et ton mot de passe : tu retrouves ton groupe, tes "
                             "messages et tes modèles, qui sont sur le relais.")}</p>', "laptop")
               + box("Ton mot de passe",
                     f'<p>{fr("« Changer le mot de passe » : les autres sessions se ferment. 5 mots de passe faux de suite, "
                               "et le compte attend 15 minutes.")}</p>', "lock"))
           + box("Les bons réflexes", ul([
               "Tu vois ce que l'élève a choisi de partager, rien de plus : s'il décoche une case, la donnée disparaît aussi "
               "chez toi.",
               "Ses allures viennent de sa VMA : demande-lui de la tenir à jour et de partager son objectif. Ou note la VMA "
               "de ton test au club.",
               "Une séance proposée arrive à la prochaine synchro de l'élève : pour une séance du lendemain, envoie-la la veille.",
               "Le relais garde 4 semaines de séances : c'est un outil de suivi, pas une archive.",
           ]), "check"))
