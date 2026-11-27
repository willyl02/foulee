"""Partie 7 — Foulée sur ton téléphone, Partie 8 — Foulée Coach : le principe, Partie 9 — Côté élève."""
from kit import (HOST, box, cards, chip, code, fr, howto, icon, legend, linkcard, note, numbered, row, shot, table, two, ul)

DL = "https://tailscale.com/download"
DNS = "https://login.tailscale.com/admin/dns"


def part7(D):
    D.part("Foulée sur ton téléphone", "Ton Foulée dans la poche, de partout : Tailscale relie ton téléphone à ton PC par "
           "une liaison privée et chiffrée. Rien n'est publié sur Internet, et tes données restent sur ton PC.",
           ["Tailscale sur ton PC, et HTTPS activé une fois pour toutes",
            "Tailscale sur ton téléphone, avec le même compte",
            "Activer l'accès dans Foulée, puis scanner le QR code",
            "Installer Foulée comme une appli, et le dépannage"],
           img="telephone-accueil")

    D.page("Téléphone › <b>Étapes 1 et 2</b>", "Tailscale sur ton PC",
           "Tailscale crée un petit réseau privé entre tes appareils, et seulement eux. Il est gratuit pour un usage "
           "personnel, avec un compte Google, Microsoft ou Apple. Installe-le d'abord sur le PC où tourne Foulée.",
           linkcard("Télécharger Tailscale", DL, "tailscale.com/download", "Le même lien sert pour le téléphone (page suivante).")
           + howto([
               (1, "Télécharge Tailscale pour Windows", fr("Sur tailscale.com/download, « Download Tailscale for Windows ».")),
               (2, "Installe-le", fr("Double-clique sur le fichier téléchargé ; Windows demande une autorisation : « Oui ».")),
               (3, "Connecte-toi", fr("Clique sur l'icône de Tailscale près de l'horloge, puis « Log in » : ton navigateur "
                                      "s'ouvre. Choisis ton compte Google, Microsoft ou Apple, puis « Connect ». Retiens "
                                      "lequel : il faudra le même sur le téléphone.")),
               (4, "C'est fait", fr("L'icône de Tailscale indique « Connected ». Ton PC a maintenant un nom dans ton réseau, "
                                    "du genre mon-pc.tail1234.ts.net.")),
           ], "compact")
           + f'<h2 style="margin-top:2mm">{icon("lock")}{fr("Étape 2 · Activer HTTPS, une fois pour toutes")}</h2>'
           + linkcard("La console Tailscale, page DNS", DNS, "login.tailscale.com/admin/dns", "Connecte-toi avec le même compte.")
           + howto([
               (1, "Ouvre la page DNS de la console Tailscale", fr("Depuis le PC ou le téléphone, avec le même compte.")),
               (2, "MagicDNS : « Enable MagicDNS »", fr("S'il est déjà activé, rien à faire.")),
               (3, "Tout en bas, HTTPS Certificates : « Enable HTTPS »",
                fr("Puis confirme. C'est ce qui donne à ton PC une adresse sécurisée en https.")),
           ], "compact")
           + note("Avec HTTPS, le nom de ton PC apparaît dans le registre public des certificats. Seul ce nom est visible : "
                  "personne ne peut ouvrir l'adresse sans être dans ton réseau Tailscale."))

    D.page("Téléphone › <b>Étape 3</b>", "Tailscale sur ton téléphone",
           "Le même Tailscale, avec le même compte : ton téléphone rejoint ton réseau privé.",
           howto([
               (1, "Installe l'appli Tailscale", fr("Sur le Play Store (Android) ou l'App Store (iPhone) : cherche "
                                                    "« Tailscale ». Elle est gratuite.")),
               (2, "Connecte-toi avec le même compte que sur le PC", fr("C'est essentiel : un autre compte, c'est un autre "
                                                                        "réseau, et ton téléphone ne verrait pas ton PC.")),
               (3, "Accepte la connexion VPN", fr("Android : « Demande de connexion » › « OK ». iPhone : « Autoriser l'ajout "
                                                  "de configurations VPN » › « Autoriser », puis ton code. Tailscale ne fait "
                                                  "passer que ce qui va vers tes appareils.")),
               (4, "Vérifie qu'il est connecté", fr("L'interrupteur en haut de l'appli est activé, et ton PC apparaît dans la "
                                                    "liste des appareils. Tu peux le laisser connecté : il consomme très peu.")),
           ])
           + f'<h2>{icon("check")}{fr("Dans Foulée, les étapes se cochent toutes seules")}</h2>'
           + shot("etapes-p", max_w=182, max_h=80,
                  cap="Réglages › Application › Foulée sur ton téléphone, sur le PC : ici, il reste à activer HTTPS (étape 2).")
           + note("Sur Android, dans les réglages de l'appli Tailscale, « Use Tailscale DNS » doit être activé (c'est le cas "
                  "au départ) : sinon, le téléphone ne trouve pas l'adresse en .ts.net."))

    D.page("Téléphone › <b>Étape 4</b>", "Activer l'accès dans Foulée",
           "Sur le PC, dans Foulée : un bouton fait tout le travail. Depuis le profil principal, celui qui gère l'installation.",
           howto([
               (1, "Ouvre Réglages › Application", fr("La rubrique « Foulée sur ton téléphone ». Ou tape « téléphone » dans "
                                                      "la recherche des réglages.")),
               (2, "Les trois premières étapes sont cochées ?", fr("Tailscale installé, connecté, certificats HTTPS activés. "
                                                                   "Sinon, « Vérifier à nouveau » après avoir fait l'étape qui manque.")),
               (3, "« Activer l'accès depuis mon téléphone »", fr("Si Windows demande « Autoriser cette application à "
                                                                  "apporter des modifications ? », réponds « Oui » : c'est Tailscale.")),
           ], "compact")
           + shot("pret-p", [(3, 636, 680)], 166, 70, cap="Tout est prêt : il reste à activer.")
           + shot("actif-p", max_w=166, max_h=70,
                  cap="C'est activé : le QR code et l'adresse de ton Foulée (ici, une adresse d'exemple)."))

    D.page("Téléphone › <b>Étape 5</b>", "Ouvrir Foulée sur le téléphone",
           "Il ne reste qu'à scanner le QR code affiché par Foulée sur le PC, puis à épingler Foulée comme une appli.",
           row(howto([
               (1, "Tailscale connecté sur le téléphone", fr("L'interrupteur de l'appli est activé.")),
               (2, "Scanne le QR code", fr("Avec l'appareil photo du téléphone, face au QR code de Réglages › Application › "
                                           "Foulée sur ton téléphone. Ou tape l'adresse, en https, sans faute de frappe : "
                                           "c'est le piège le plus courant.")),
               (3, "Choisis ton profil", fr("Si plusieurs personnes utilisent Foulée sur ce PC, chacun choisit le sien ; un "
                                            "code à 4 chiffres peut le protéger.")),
               (4, "Installe-le comme une appli", fr("Android (Chrome) : menu ⋮ › « Installer l'application ». iPhone "
                                                     "(Safari) : bouton Partager › « Sur l'écran d'accueil ». Foulée s'ouvre "
                                                     "alors en plein écran, comme une vraie appli.")),
           ]) + box("Depuis le téléphone, tu as tout",
                    f'<p>{fr("Tes vues, ta forme du jour, tes séances, l’Atelier, ton coach et tes messages, la synchro… et "
                              "même les réglages : la liaison est chiffrée de bout en bout, alors Foulée te fait confiance "
                              "comme sur le PC.")}</p>', "check"),
               shot("telephone-accueil", max_w=62, max_h=140, cap="L'Accueil, sur un téléphone."), grow=0))

    D.page("Téléphone › <b>Dépannage</b>", "Bon à savoir, et si ça ne marche pas",
           "Les questions qui reviennent, et leur réponse.",
           two(box("Le PC doit rester allumé",
                   f'<p>{fr("PC éteint ou en veille, le téléphone affiche « Foulée est injoignable ». Pour éviter la veille : "
                             "Paramètres Windows › Système › Alimentation › Mise en veille › Jamais (sur secteur). L’écran, "
                             "lui, peut s’éteindre.")}</p>', "laptop"),
               box("Qui peut ouvrir l'adresse ?",
                   f'<p>{fr("Seulement les appareils connectés à ton compte Tailscale. Pas ton coach, pas le relais du "
                             "club, personne d’autre. Pour arrêter : « Couper l’accès », dans le même réglage.")}</p>', "lock"))
           + f'<h2>{icon("help")}{fr("Dépannage")}</h2>'
           + table(["Sur le téléphone", "Ce qu'il faut faire"], [
               (f"<b>{fr(a)}</b>", fr(b)) for a, b in [
                   ("La page ne s'ouvre pas du tout", "Vérifie l'adresse (scanne plutôt le QR code), puis que Tailscale est "
                    "connecté sur le téléphone, avec le même compte que le PC."),
                   ("« Foulée est injoignable »", "Le PC est éteint ou en veille, ou Foulée n'y tourne pas (son icône près "
                    "de l'horloge). Réveille le PC, puis « Réessayer »."),
                   ("« Hôte refusé »", "Le nom du PC a changé dans Tailscale : « Couper l'accès » puis « Activer » à nouveau."),
                   ("Erreur de certificat", "L'étape 2 (HTTPS) n'est pas faite, ou la toute première ouverture prend du "
                    "temps : attends une minute et recharge."),
                   ("Ça ne marche qu'à la maison", "Vérifie que l'appli Tailscale est bien connectée en 4G ou 5G."),
               ]])
           + note("Pour consulter Foulée sans laisser le PC allumé, Foulée peut aussi tourner sur un petit serveur à la "
                  "maison : c'est expliqué dans le README du projet, sur GitHub.", "settings"))


def part8(D):
    D.part("Foulée Coach : le principe", "Le coach et ses élèves, reliés. Chacun garde son Foulée et ses données chez "
           "lui ; un petit relais sur Internet, gratuit et sécurisé, fait passer ce que l'élève choisit de partager.",
           ["Foulée Coach en bref",
            "Le relais : comment les Foulée se parlent",
            "Ce qui circule, et ce qui reste chez soi"],
           img="mon-coach")

    D.page("Foulée Coach › <b>En bref</b>", "Foulée Coach en bref",
           "Le principe : chaque coureur garde Foulée chez lui, et seul ce qu'il choisit de partager passe par le relais du club.",
           cards([
               ("Chacun chez soi", "L'élève garde Foulée et tout son historique sur son PC. Il choisit ce qu'il partage, "
                "case par case, et peut tout reprendre.", "lock"),
               ("Un relais léger", "Un petit serveur, en HTTPS, ne garde que l'extrait partagé : 4 semaines de séances en "
                "résumé. Jamais Strava, jamais la clé Garmin.", "sync"),
               ("Le suivi du coach", "Ses élèves d'un coup d'œil : dernière séance, semaine jour par jour, charge, objectif, "
                "alertes.", "user"),
               ("Les échanges", "Une conversation par élève, un fil sous chaque séance, et le fil du groupe pour les "
                "annonces.", "chat"),
               ("Les séances proposées", "Le coach compose une séance en % de VMA ; chaque élève la reçoit avec ses allures, "
                "dans son calendrier, et jusque sur sa montre.", "watch"),
               ("Une inscription simple", "Le coach crée un code d'invitation, l'élève le colle dans Foulée, choisit son mot "
                "de passe et donne son accord.", "check"),
           ], cls="three")
           + two(box("Deux modes, selon le compte",
                     f'<p>{fr("Mode coach (« Mes élèves ») ou mode élève (« Mon coach ») : les pages apparaissent selon le "
                               "compte, profil par profil. Un même PC peut avoir un coach et un élève. Et depuis la 0.8.3, un "
                               "troisième : le compte « sans coach », pour envoyer ses propres séances sur sa montre (partie 5).")}</p>',
                     "user"),
                 box("Pour s'y mettre",
                     ul([f"Foulée {D.version} ou plus récent.",
                         f"L'adresse du relais du club : {HOST}.",
                         "Élève : un code d'invitation de son coach (valable 7 jours).",
                         "Coach : un compte créé par l'administrateur du relais."]), "list")))

    D.page("Foulée Coach › <b>Le relais</b>", "Un relais entre les Foulée",
           "Trois acteurs : les élèves et le coach, chacun avec son Foulée, et le relais du club sur Internet.",
           cards([
               ("Chez chaque élève", "Sa montre Garmin enregistre les séances ; son Foulée les lit chez Garmin avec sa propre "
                "clé API et garde tout son historique. « Mon coach » montre les séances proposées, et son accord décide de "
                "ce qui part.", "user"),
               ("Le relais du club", f"{HOST} : les comptes, les invitations, les extraits partagés, les séances proposées "
                "et les messages. Il est en HTTPS derrière Cloudflare, sans aucun port ouvert, et hébergé en France.", "globe"),
               ("Chez le coach", "Son Foulée, avec ses propres séances comme avant, et en plus : ses élèves et leur fiche, les "
                "messages, les séances à proposer, les objectifs, les codes d'invitation.", "club"),
           ], cls="three")
           + cards([
               ("Chez soi, comme avant", "Chaque Foulée lit Garmin avec la clé de son propriétaire. Rien ne change pour qui "
                "n'a pas de coach.", "laptop"),
               ("Toujours par le relais", "Élève et coach ne se parlent jamais directement : chacun dépose et relit sur le "
                "relais. Ça marche même quand l'autre PC est éteint.", "sync"),
               ("Rien d'ouvert", "Le relais n'est joignable que par son adresse en HTTPS, au travers d'un tunnel chiffré. "
                "Aucun PC n'a besoin d'ouvrir quoi que ce soit.", "lock"),
               ("À jour tout seul", "Chaque nuit, le relais prend la dernière version publiée. Les PC se mettent à jour comme "
                "d'habitude.", "download"),
           ], cls="two")
           + note("Le relais est un petit serveur gratuit : seul le nom de domaine coûte une dizaine d'euros par an. Foulée "
                  "reste gratuit, pour le coach comme pour les élèves."))

    rows = [("Séances des 4 dernières semaines, en résumé", "oui, avec accord"),
            ("Objectif de course et VMA", "oui, avec accord"),
            ("Tracé GPS des séances, simplifié", "en option"),
            ("… avec le départ et l'arrivée masqués (500 m)", "en option"),
            ("Sommeil, VFC et FC au repos", "en option"),
            ("Poids (balance Withings)", "en option"),
            ("Séances venues de Strava", "jamais (règles de Strava)"),
            ("Clé API Garmin, jetons", "jamais"),
            ("Historique complet, autres profils", "jamais")]
    D.page("Foulée Coach › <b>Données et sécurité</b>", "Ce qui circule, ce qui reste chez soi",
           "L'élève décide, case par case, à l'inscription puis à tout moment. Une case décochée efface aussitôt la donnée "
           "chez le relais.",
           table(["Donnée de l'élève", "Vers le coach"], [(fr(a), f"<b>{fr(b)}</b>") for a, b in rows])
           + cards([
               ("Mots de passe", "10 caractères au moins, gardés seulement sous forme d'empreinte : même le relais ne les "
                "connaît pas.", "lock"),
               ("Jeton de connexion", "Dans Foulée, rangé dans le coffre de Windows, comme la clé Garmin ; jamais montré, "
                "jamais envoyé à Claude.", "lock"),
               ("Essais limités", "5 mots de passe faux, puis 15 minutes d'attente ; changer de mot de passe ferme les autres "
                "sessions.", "reset"),
               ("Durée limitée", "4 semaines de séances, remplacées à chaque envoi ; un élève qui quitte le groupe est "
                "effacé aussitôt.", "calendar"),
               ("Chiffré sur tout le trajet", "HTTPS entre les PC et le relais, tunnel chiffré jusqu'à lui. Données hébergées "
                "en France.", "globe"),
               ("Sur la montre", "Pour envoyer une séance, le relais peut seulement déposer des entraînements dans le "
                "calendrier Garmin. Il ne lit rien de la montre.", "watch"),
           ], cls="three"))


def part9(D):
    D.part("Côté élève", "Rejoindre ton coach, choisir ce que tu partages, et retrouver ses séances dans ton calendrier et "
           "jusque sur ta montre.",
           ["Rejoindre ton coach avec son code d'invitation",
            "Choisir ce que tu partages, et changer d'avis",
            "Ta page « Mon coach » et ton calendrier",
            "La séance sur ta montre, sans câble (ou avec)",
            "Ta séance du jour, ton ressenti, les notifications et les messages"],
           img="partage")

    D.page("Côté élève › <b>Étape 1</b>", "Rejoindre ton coach",
           "Foulée installé et ta clé Garmin en place (partie 2) ? Il te faut l'adresse du relais du club et le code "
           "d'invitation que ton coach t'a donné. Pas d'adresse e-mail, pas de formulaire en ligne : tout se passe dans "
           "Foulée, sur ton PC.",
           shot("inscription-eleve", [(3, 499, 476), (4, 1019, 476), (5, 1534, 476), (6, 499, 629), (7, 1019, 629),
                                      (7, 1534, 629), (8, 430, 740)], 156, 70,
                cap="Réglages › Club et coach › Coach et élèves : le formulaire, rempli avec un exemple.")
           + howto([
               (1, "Ouvre Réglages › Club et coach", fr("La rubrique « Coach et élèves ». Depuis le PC où Foulée est "
                                                        "installé : un mot de passe ne doit pas circuler sur le réseau.")),
               (2, "Choisis « J'ai un code d'invitation »", ""),
               (3, "L'adresse du relais", fr(f"{HOST}, telle que ton coach te l'a donnée (elle est déjà proposée).")),
               (4, "Le code d'invitation", fr("Par exemple K7MP-Q3XR : il sert une seule fois, et vaut 7 jours. Expiré ? "
                                              "Demande-en un autre à ton coach.")),
               (5, "Ton identifiant, à choisir", fr("Par exemple prenom.nom, en minuscules. Garde-le : il sert à te "
                                                    "reconnecter (nouveau PC, réinstallation).")),
               (6, "Le nom que verra ton coach", fr("Ton prénom et l'initiale de ton nom, par exemple.")),
               (7, "Ton mot de passe, deux fois", fr("10 caractères au moins. Range-le dans ton gestionnaire de mots de passe.")),
               (8, "« Rejoindre mon coach »", fr("C'est fait : « Mon coach » s'ajoute à ta colonne, avec la vue "
                                                 "« Calendrier ». Foulée t'emmène aussitôt choisir ce que tu partages.")),
           ], "compact")
           + note("Tu avais déjà un compte « sans coach » ? Pas besoin d'en créer un autre : « J'ai maintenant un coach », "
                  "puis colle son code d'invitation. Ta montre reste reliée."))

    D.page("Côté élève › <b>Étape 2</b>", "Choisir ce que tu partages",
           "Rien ne part vers le relais avant ton accord. Coche ce que ton coach peut voir : tu pourras changer d'avis à tout "
           "moment, avec « Changer mes choix ».",
           shot("partage", numbered([(330, 282), (330, 412), (330, 490), (395, 567), (330, 712), (955, 229), (958, 664)]),
                182, 116, cap="Mon coach › Mon partage : ici, tout est coché.")
           + legend(["Tes séances des 4 dernières semaines, en résumé : distance, durée, allure, FC, charge, tours, renfo, ta "
                     "description.",
                     "Ton objectif et ta VMA : ton coach en tire tes allures.",
                     "Le tracé GPS, simplifié, sans fond de carte…",
                     "… avec le départ et l'arrivée masqués sur 500 m : ta maison n'apparaît pas.",
                     "Sommeil, VFC, FC au repos, poids : en option, décochés au départ.",
                     "Jamais : Strava, ta clé et tes mots de passe, l'historique au-delà de 4 semaines, les autres profils.",
                     "« Enregistrer et envoyer » : l'extrait part aussitôt. Une case décochée l'efface chez le relais."], cols=True)
           + note("Ensuite, Foulée envoie ton extrait après chaque synchro : il remplace le précédent, le relais n'a jamais "
                  "plus de 4 semaines.", "sync"))

    D.page("Côté élève › <b>Étape 3</b>", "Ta page « Mon coach »",
           "Dans la colonne de gauche : les séances que ton coach te propose, avec tes allures, votre conversation, et ce "
           "que tu partages.",
           shot("mon-coach", numbered([(440, 197), (482, 332), (878, 398), (283, 583), (1278, 195), (1342, 441), (1280, 652),
                                       (1236, 906)]), 182, 112, cap="« Mon coach », chez une élève.")
           + legend(["Ton coach, et le fil du groupe en un clic. Le logo de ton club s'affiche ici si ton coach en fait partie.",
                     "La séance proposée, bloc par bloc ; elle est aussi dans ta vue « Calendrier ».",
                     "Tes allures à toi, calculées avec ta VMA (Réglages › Moi › Profil de coureur).",
                     "« Envoyer sur ma montre » : la séance part dans ton calendrier Garmin. « Fichier .fit » : la même, par "
                     "câble USB.",
                     "Ta montre Garmin : la relier une fois, puis tes réglages.",
                     "Ta conversation avec ton coach, sur place.",
                     "Ce que tu partages, d'un coup d'œil.",
                     "« Envoyer maintenant », ou « Changer mes choix »."], cols=True)
           + note("Plus bas, « Ton calendrier » : quatre semaines passées, celle-ci et quatre à venir, avec ton plan, les "
                  "séances de ton coach et ce que tu as fait. Il se replie d'un clic sur son titre.", "calendar"))

    D.page("Côté élève › <b>Étape 4</b>", "La séance dans ton calendrier",
           "La vue « Calendrier » arrive avec ton coach : ses séances y sont en pointillé bleu, à côté de ton plan Garmin "
           "s'il est relié, face à ce que tu fais vraiment.",
           shot("calendrier", numbered([(556, 192), (1062, 597), (1190, 424), (1188, 627), (1188, 683)]), 182, 100,
                cap="La vue « Calendrier » d'une élève.")
           + legend(["« Prochaines séances » : la séance de ton coach.",
                     "Dans le mois, le jour prévu.",
                     "Un clic sur le jour : « Proposée par ton coach », les blocs et la consigne.",
                     "Le lien vers « Mon coach », pour tes allures…",
                     "… et le fichier .fit pour ta montre (par câble), directement depuis le calendrier."])
           + note("Une course faite le même jour la marque « faite » ; un jour passé sans séance du même sport : « manquée ». "
                  "Ton coach le voit dans ta fiche, et sur l'Accueil, « Ta semaine » la compte dans tes séances prévues.",
                  "check"))

    D.page("Côté élève › <b>Étape 5</b>", "La séance sur ta montre",
           "Un clic, sans câble : la séance de ton coach part dans ton calendrier Garmin Connect, avec tes allures. La "
           "première fois, tu relies ton compte Garmin.",
           row(shot("montre-bouton", [(1, 22, 578)], 92, 62),
               howto([
                   (1, "« Envoyer sur ma montre »", fr("Sous la séance, dans « Mon coach ».")),
                   (2, "La première fois : Garmin Connect s'ouvre", fr("Dans une autre fenêtre. Connecte-toi chez Garmin, "
                                                                       "sur le site de Garmin : Foulée ne voit jamais ton mot "
                                                                       "de passe.")),
                   (3, "« Accepter »", fr("Garmin demande si Foulée peut ajouter des entraînements à ton compte : laisse "
                                          "l'autorisation cochée, puis « Accepter ».")),
                   (4, "C'est parti", fr("« Compte Garmin relié » : la séance est déjà dans ton calendrier Garmin, à sa date.")),
                   (5, "Synchronise ta montre", fr("Appli Garmin Connect ouverte sur le téléphone : la montre trouve la "
                                                   "séance dans son calendrier et dans Entraînement › Entraînements.")),
               ], "compact"), grow=1)
           + row(shot("montre-retour", max_w=70, max_h=40, cap="Après « Accepter » : la page de retour."),
                 shot("montre-envoyee", [(1, 994, 66), (2, 22, 578)], 100, 46, cap="Ensuite, dans « Mon coach »."))
           + legend(["« sur ta montre » : la séance est dans ton calendrier Garmin (survole pour la date).",
                     "Les fois suivantes, un clic suffit. « Renvoyer » la remplace, sans doublon."])
           + note("Ton coach modifie la séance ? Elle est renvoyée toute seule. Il la supprime ? Elle quitte aussi ton "
                  "calendrier Garmin.", "sync"))

    fit = [("1. Échauffement", "20 min", "7:28 – 7:56 /km", "65 % VMA"), ("2. Seuil", "10 min", "5:31 – 5:51 /km", "88 % VMA"),
           ("3. Récup", "2 min", "libre", "« trot »"), ("4. Répéter 3 fois", "étapes 2 et 3", "", ""),
           ("5. Retour au calme", "10 min", "8:05 – 8:35 /km", "60 % VMA")]
    D.page("Côté élève › <b>Ta montre</b>", "Ta montre Garmin : réglages, câble",
           "Ce qui arrive sur la montre, ce que Foulée peut faire avec ton compte Garmin, et le câble pour ceux qui préfèrent.",
           row(shot("montre-carte-reliee", [(1, 860, 214), (2, 462, 284)], 92, 44),
               legend(["« … peut envoyer ses séances directement sur ma montre » : coché, ton coach envoie lui-même ses "
                       "séances sur ta montre. Décoche pour le faire toi-même.",
                       "Délier : Foulée n'a plus le droit d'ajouter des séances (l'autorisation est retirée chez Garmin "
                       "aussi). Les séances déjà envoyées restent dans ton calendrier Garmin."]), grow=1)
           + f'<h2>{icon("list")}{fr("Ce qui arrive sur la montre, pour une élève à VMA 12 km/h")}</h2>'
           + table(["Étape", "Durée", "Cible sur la montre"],
                   [(f"<b>{fr(a)}</b>", fr(b), f'{fr(c)} <span class="sub">{fr(d)}</span>') for a, b, c, d in fit])
           + note("Les % de VMA deviennent une fourchette d'allure (± 3 %) : ta montre te prévient si tu sors de la fourchette. "
                  "Une zone de FC devient une cible de fréquence cardiaque. La consigne de ton coach est dans la description "
                  "de la séance.")
           + two(box("Ce que Foulée peut faire",
                     f'<p>{fr("Seulement déposer des séances dans ton calendrier Garmin Connect. Il ne lit rien de ta montre "
                               ": ni séances, ni santé. Ton autorisation est gardée chiffrée sur le relais du club ; tu peux "
                               "aussi la retirer dans Garmin Connect (applications connectées).")}</p>', "lock"),
                 box("Avec un câble, si tu préfères",
                     f'<p>{fr("« Fichier .fit » sous la séance : montre branchée au PC en USB, copie le fichier dans son "
                               "dossier GARMIN\\NewFiles, puis débranche : la séance est dans Entraînement › Entraînements.")}</p>',
                     "download")))

    D.page("Côté élève › <b>Aujourd'hui</b>", "Ta séance du jour et ton ressenti",
           "Avec un coach, la vue « Aujourd'hui » montre sa séance. Après la séance, ton coach a ton ressenti.",
           shot("e-jour", numbered([(52, 136), (52, 364), (1100, 600), (1110, 354), (52, 950)]), 182, 92,
                cap="« Ma séance du jour », avec une séance du coach (profil de démonstration).")
           + legend(["Le verdict du jour, d'après ta nuit, ta FC de repos et ta Body Battery.",
                     "Ce qui est prévu : la séance de ton coach (« de ton coach »), avec son esquisse, chaque étape et ton allure.",
                     "La météo heure par heure, près de ta dernière sortie. Tes heures de travail sont grisées si tu es posté.",
                     "Ton créneau : le meilleur moment pour courir, entre la pluie, le vent, le froid et la nuit.",
                     "« Envoyer sur ma montre », ou le fichier .fit, directement d'ici."], cols=True)
           + row(shot("e-ressenti", [(6, 1000, 293), (7, 1330, 400), (8, 560, 673)], 104, 46,
                      cap="Après la séance : ton ressenti, pour ton coach."),
                 legend(["Ton ressenti, de 1 (très facile) à 10 (maximal) : un clic, il est gardé.",
                         "Un mot si tu veux : jambes lourdes, bonnes sensations, douleur au mollet…",
                         "« Envoyer à mon coach » : la séance, tes chiffres, ton ressenti et ton mot arrivent dans votre "
                         "conversation."], start=6), grow=1))

    D.page("Côté élève › <b>Notifications</b>", "Les notifications sur ton téléphone",
           "Le relais te prévient quand ton coach t'envoie une séance, la modifie ou l'annule, et quand il t'écrit, même "
           "quand Foulée est fermé. Avec ntfy, une appli gratuite, sans compte ni publicité.",
           row(shot("e-notif", max_w=88, max_h=112),
               howto([
                   (1, "Ouvre Réglages › Club et coach › Notifications", fr("La rubrique apparaît dès que tu es relié à ton coach.")),
                   (2, "Installe ntfy sur ton téléphone", fr("Les liens sont dans la rubrique : Google Play ou F-Droid sur "
                                                             "Android, App Store sur iPhone.")),
                   (3, "Abonne-toi à ton sujet", fr("Dans ntfy, scanne le QR code, ou touche « + » et colle le sujet. Garde-le "
                                                    "pour toi : qui le connaît lit tes notifications. « Changer de sujet » "
                                                    "en crée un autre.")),
                   (4, "Coche « Activées », puis essaie", fr("« Envoyer une notification d'essai » : elle arrive en quelques "
                                                             "secondes.")),
                   (5, "Choisis quand être prévenu", fr("Séance reçue, modifiée, annulée, nouveau message ; « Afficher le "
                                                        "détail » montre le titre ou le début du message sur l'écran verrouillé.")),
               ], "compact"), grow=1)
           + box("Les heures calmes",
                 f'<p>{fr("« Ne pas me déranger » de 22 h à 7 h, par exemple : pendant ces heures, la notification attend "
                           "leur fin. Pratique en horaires postés : règle-les sur tes heures de sommeil.")}</p>', "moon"))

    D.page("Côté élève › <b>Au quotidien</b>", "Messages, logo du club et au quotidien",
           "Tes échanges avec ton coach et le groupe, un petit plus pour les licenciés, et ce qu'il faut savoir ensuite.",
           row(shot("messages-eleve-main", numbered([(355, 248), (355, 365), (1110, 345)]), 100, 78),
               legend(["Le fil du groupe : annonces, rendez-vous, encouragements.",
                       "Ta conversation avec ton coach.",
                       "Tes messages en bleu, à droite. Plus bas, les fils sous tes séances partagées : ton coach les commente."])
               + note("Foulée relève les messages toutes les minutes : un badge rouge dans la colonne compte les non-lus.",
                      "chat"), grow=1)
           + box("Le logo de ton club, sur la carte de ton coach",
                 f'<p>{fr("Choisis le logo de ton club dans la logothèque (partie 6), puis, rubrique Coach et élèves, réponds "
                           "« Oui » à « Ton coach fait-il partie de ton club ? » : le logo s’affiche aussi sur la carte de ton "
                           "coach.")}</p>' + '<div style="margin-top:2.6mm">' + shot("carte-coach", max_w=120, max_h=17) + "</div>",
                 "club")
           + two(box("Au quotidien", ul([
                 "Rien à faire : ton extrait part après chaque synchro, et les séances de ton coach arrivent toutes seules.",
                 "Changer d'avis : « Changer mes choix », dans « Mon coach », à tout moment.",
                 "Nouveau PC ou réinstallation : Réglages › Club et coach › Coach et élèves › « J'ai déjà un compte ».",
             ]), "sync"),
                 box("En cas de souci", ul([
                     "Mot de passe : « Changer le mot de passe », au même endroit. Oublié ? Ton coach le fait réinitialiser "
                     "par l'administrateur du relais.",
                     "Quitter le groupe : même endroit, avec ton mot de passe ; tout ce que tu as partagé est effacé du relais.",
                     "Une question ? Aide et FAQ, rubrique « Coach et élèves ».",
                 ]), "help")))
