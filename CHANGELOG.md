# Historique des versions

Les versions « bêta » (par exemple 0.4.0b1) sont des avant-premières : elles arrivent d'abord
sur le canal bêta (Réglages → Mises à jour → « Recevoir les versions bêta »), puis sortent en
version stable une fois éprouvées.

## 0.7.0b3 — 13 novembre 2026 (bêta)

- **Effet d'entraînement de chaque séance** : une nouvelle tuile de la vue Séance montre le Training Effect de Garmin en deux jauges de 0 à 5, aux couleurs de Garmin Connect : l'**effet aérobie** (ce que la séance apporte à ton endurance) et l'**effet anaérobie** (tes efforts brefs et très intenses), avec leur niveau (aucune amélioration, faible avantage, maintien, impact, fort impact, effort trop soutenu) et ce qu'il veut dire. L'**avantage principal** de la séance l'accompagne (base, tempo, seuil, VO2 max, capacité anaérobie, sprint…), ainsi que sa place parmi tes séances du même sport des 4 semaines précédentes : les petits traits autour des jauges, et « au-dessus de 9 de tes 14 séances de course et trail ». Le résumé de la séance affiche aussi l'effet anaérobie. La tuile s'efface pour les séances sans effet d'entraînement (Strava, montre sans cardio).
- **Équilibre avant / arrière du renfo** : chaque exercice est rangé selon son mouvement, chaîne antérieure (squats et fentes, poussée, abdos, biceps, releveurs) ou chaîne postérieure (soulevé de terre roumain, hip thrust, leg curl et swing, tirage, lombaires, triceps, mollets), et Foulée compare les séries : « 1 : 1,5 », c'est 1,5 série derrière pour 1 devant. La cible du coureur (de 1:1 à 1:2) est sur l'échelle ; le verdict, paire par paire (bas du corps genou / hanche, haut du corps poussée / tirage, tronc, bras, bas de jambe), signale celle qui penche vers l'avant et dit quoi ajouter.
- Une tuile **« Renfo : équilibre avant / arrière »** rejoint la vue Renfo, sous les muscles travaillés : le rapport de la période, les paires en ailes de papillon et l'équilibre semaine après semaine face à la bande de la cible. La tuile « Exercices de renfo » de la vue Séance donne celui de la séance, et chaque exercice porte une étiquette qui montre comment il est compté (« Arrière · dominante hanche », « Latéral et rotation »…). Les exercices « corps entier » comptent ½ de chaque côté ; le latéral et la rotation sont comptés à part. Les deux nouvelles tuiles s'ajoutent d'elles-mêmes à tes vues Séance et Renfo, une seule fois.
- **Claude Desktop** voit l'effet d'entraînement d'une séance (`detail_seance`) et l'équilibre avant / arrière d'une séance ou d'une période (`renfo`), avec le conseil.
- Le « bénéfice principal » des autres mesures d'une séance s'affiche en clair (« Base (aérobie faible) ») au lieu du code de Garmin.
- Aide : deux nouvelles questions (les jauges d'effet d'entraînement, l'équilibre avant / arrière). Mode démo : des effets d'entraînement réalistes selon la séance, et un renfo qui travaille aussi l'arrière.

## 0.7.0b2 — 12 novembre 2026 (bêta)

- **Calendrier d'entraînement** (Réglages → Calendrier) : colle le lien de ton calendrier Garmin Connect publié (calendrier → trois points → « Publier le calendrier »), ou celui d'un agenda Google ou du club, et tes séances prévues et tes courses arrivent dans Foulée, face à ce que tu as réellement fait.
- **Une vue « Calendrier »** s'ajoute juste après l'Accueil : ta prochaine course avec son compte à rebours et tes prochaines séances, puis le mois jour par jour. Un clic sur un jour donne le détail (consigne de la séance, heure et lieu d'une course, séance faite à ouvrir d'un clic) ; les flèches du clavier passent d'un jour à l'autre ; sur téléphone, des pastilles remplacent les titres. Elle s'en va si tu retires le lien.
- **« Ta semaine »** (Accueil) montre les séances prévues de chaque jour : cochées quand elles sont faites, barrées quand elles sont manquées, en pointillé quand elles sont à venir, et un drapeau rouge pour une course. Le bilan de la semaine s'y ajoute (« Prévues 4/6 faites »). Un clic mène au jour dans la vue Calendrier.
- **Fait ou manqué** : une séance du même sport le même jour rend une séance prévue « faite » ; un jour passé sans rien de tel la rend « manquée ». Le calendrier publié par Garmin ne contient que l'avenir : Foulée garde lui-même ce qu'il a lu, jour après jour.
- **Une pastille « Calendrier »** rejoint celles de Garmin, Withings et Strava : verte quand la dernière lecture a réussi, rouge sinon. Si la publication est annulée (le lien ne répond plus), la lecture se met en pause et la pastille t'envoie coller le nouveau lien ; les séances déjà lues restent. Le calendrier est relu avec la synchro automatique, à son propre rythme (3 heures par défaut), ou tout de suite avec « Actualiser ».
- **Le lien reste secret** : il donne ton calendrier à quiconque le connaît. Il va dans le coffre, comme la clé Garmin, ne se colle que depuis la machine elle-même ou par Tailscale, et ne s'affiche plus qu'abrégé ; ni la sauvegarde des réglages, ni le journal, ni les messages d'erreur, ni Claude ne le voient.
- **Claude Desktop** voit tes séances prévues et leur état : nouvel outil `calendrier`, et les séances prévues de chaque jour dans `semaine`.
- Aide : nouveau thème « Calendrier d'entraînement ». Mode démo : un plan de préparation au semi, avec un 10 km.

## 0.7.0b1 — 12 novembre 2026 (bêta)

- **Strava, en lecture seule** (Réglages → Strava) : les séances d'une montre Coros, Suunto, Polar ou Apple, d'un compteur de vélo, ou notées sur Strava, rejoignent les tiennes dans toutes les vues : listes, volumes, charge et forme, renfo. Foulée fonctionne aussi avec Strava seul, sans montre Garmin.
- **Pas de doublons** : une séance que Garmin a déjà donnée ne compte qu'une fois (Strava indique qu'elle vient de Garmin Connect, ou les deux se recouvrent dans le temps). La séance Garmin affiche ses kudos et sa description Strava, avec le lien « View on Strava ».
- **Renfo noté sur Strava** : l'API de Strava ne donne pas les exercices d'une séance de musculation ; Foulée lit ceux que la description énumère (Hevy, Strong, ou une note « Squat 4x10 @ 60 kg ») et garde leurs noms tels qu'écrits, souvent en anglais.
- **D'où viennent les chiffres** : chaque tuile le dit à côté de son titre (Garmin, Strava avec l'appareil d'origine, Withings), comme Garmin le demande.
- **Les règles de Strava, appliquées** : rien de Strava n'est gardé plus de 48 heures (relu à chaque synchro, oublié sinon) ; Claude Desktop ne voit aucune donnée Strava (pour cela, le connecteur Strava officiel de Claude) ; Strava demande un abonnement au compte qui crée l'appli Strava de Foulée. Une pastille « Strava » rejoint celles de Garmin et Withings, et son rythme de synchro se règle comme les autres.
- Téléphone : à partir de trois sources, les pastilles de connexion n'affichent que leur point (le nom est dans le détail).

## 0.6.0b7 — 12 novembre 2026 (bêta)

- **Rythme de la synchro automatique**, dans Réglages → Synchro et calculs : un délai pour Garmin et un pour Withings, de 30 minutes à 12 heures (3 heures par défaut). 3 heures est un bon compromis : séances, nuits et pesées arrivent dans la journée sans solliciter Garmin et Withings pour rien. En dessous, Foulée prévient qu'il redemanderait sans cesse des données qui n'ont pas bougé ; pour une donnée tout de suite, « Synchroniser » reste là. Claude Desktop peut aussi changer ce réglage.
- Chaque source suit son propre délai, compté depuis sa dernière synchro réussie : si Withings échoue alors que Garmin répond (ou l'inverse), la source en panne est réessayée au bout d'une demi-heure au lieu d'attendre le tour suivant.
- Serveur : la minuterie regarde toutes les 15 minutes ce qui est dû, et ne synchronise que les sources dont le délai est écoulé (la mise à jour du serveur l'installe d'elle-même).
- Mode édition d'une vue : le « + » d'« Ajouter une tuile » occupait tout le bouton. Il reprend sa taille, et le bouton prend toute la largeur sur téléphone.

## 0.6.0b6 — 12 novembre 2026 (bêta)

- Withings, activité : sans podomètre Withings, son appli envoie des journées à 0 pas. Foulée ne montre plus de carte « 0 pas » ni de courbe de pas à zéro : l'activité Withings (carte et tuiles de la vue) n'apparaît que si des pas ont été comptés ces 90 derniers jours. La vue Withings suit à la synchro suivante, tant que tu ne l'as pas modifiée toi-même.

## 0.6.0b5 — 12 novembre 2026 (bêta)

- **Pastilles de connexion** en haut à droite de chaque vue : une par source branchée sur ton profil (Garmin, Withings, et les prochaines). Verte : sa dernière synchro a abouti. Rouge : elle n'a pas abouti, ou la clé (l'accès) manque ou est refusée. Grise : pas encore de synchro. Un clic montre le message d'erreur, la dernière synchro réussie, « Réessayer » et le lien vers les Réglages de la source. Pendant une synchro, les pastilles clignotent ; elles se mettent à jour seules après les synchros automatiques. Sur téléphone, elles sont dans la barre du haut, toujours visible.
- Claude Desktop : l'outil `statut` donne aussi l'état de chaque source et le message de la dernière synchro qui n'a pas abouti.

## 0.6.0b4 — 12 novembre 2026 (bêta)

- **Renfo** : seules les séances de musculation et de cardio / HIIT comptent. En yoga, Pilates ou mobilité, la montre « devine » des séries (un haussement d'épaules pendant 40 minutes de mobilité…) : elles ne s'ajoutent plus à tes séances de renfo, à tes muscles travaillés ni aux métriques de renfo. Si tu avais installé la 0.6.0b3, la mise à jour les retire toute seule.
- Un exercice que la montre n'a pas identifié (« Exercice non précisé ») passe en fin de liste, avec une explication : il compte dans les séries, pas dans les muscles.
- Si tu changes le type d'une séance dans Garmin Connect (de « Mobilité » à « Musculation », par exemple), Foulée suit à la synchro suivante.

## 0.6.0b3 — 12 novembre 2026 (bêta)

- **Renfo** : tes séances de musculation, exercice par exercice. Foulée lit le résumé que Garmin Connect garde pour chaque séance (séries, répétitions, durée, charge), corrections faites dans l'appli comprises, sans fichier FIT. Les séances déjà importées sont relues à la mise à jour, sans rien redemander à Garmin.
- Les exercices **en français** (« Élévation des mollets debout sur une jambe », « Chaise lestée »…) : près de 1 000 des 1 846 exercices de Garmin, dont les plus courants en course à pied. Les autres gardent leur famille en français suivie du nom de Garmin.
- **Muscles travaillés**, sur une carte du corps face et dos (16 groupes musculaires) : une série compte pour 1 sur un muscle principal, pour ½ sur un muscle secondaire, au plus ½ pour l'échauffement et les étirements. La liste dit aussi quels muscles la période a laissés de côté.
- Une vue **Renfo** s'ajoute après « Entraînement » dès ta première séance de renfo détaillée : muscles travaillés, séances par semaine face à ton objectif (2 par défaut, réglable), chaque exercice avec sa dernière séance et sa progression (charge, répétitions ou durée par série), temps, séries et tonnage par semaine, liste des séances. Ses tuiles suivent la période choisie en haut de la vue.
- Vue **Séance** : la tuile « Exercices de renfo » (séries, charge, tonnage, temps d'effort et carte du corps) s'ajoute sous le résumé ; elle s'efface pour les séances sans renfo. Sur téléphone, les exercices s'affichent en cartes.
- Quatre métriques dans toutes les tuiles (catégorie « Renfo ») : séries, répétitions, tonnage et temps d'effort.
- **Claude Desktop** voit ton renfo : nouvel outil `renfo` (séances, exercices et leur évolution, muscles travaillés ou négligés, régularité), et le détail des exercices dans `detail_seance`.
- Liste des séances : une colonne vide pour toutes les séances affichées (distance, allure, D+ pour du renfo) ne s'affiche plus ; une liste de séances de renfo montre leurs séries et leur tonnage.
- Courbes de durées courtes : graduations en minutes (« 20 min », « 1 h 20 ») au lieu de « 0,3 h ».
- Aide : nouveau thème « Renfo ». Mode démo : deux routines de renfo de coureur, avec des charges qui progressent.

## 0.6.0b2 — 12 novembre 2026 (bêta)

- **Withings** : avec plusieurs profils (ou un code de profil), la connexion n'aboutissait pas. Après « Autoriser », on revenait dans les Réglages sans synchro, sans vue « Withings » et sans message. Au retour de la page relais, le navigateur n'envoie pas le cookie du profil (il est réservé aux pages de Foulée elle-même) : Foulée retrouve maintenant le profil grâce au jeton de la demande de connexion. Après la mise à jour, relance simplement « Connecter mon compte Withings ».
- Un message de retour qui ne se rattache à aucun profil (demande expirée ou déjà servie) s'affiche quand même dans Réglages → Withings.

## 0.6.0b1 — 11 novembre 2026 (bêta)

- **Withings** : relie ton compte Withings (balance, tensiomètre, Sleep Analyzer, montre) dans **Réglages → Withings**. Un pas-à-pas en quatre étapes guide tout : créer ton appli Withings (gratuite, une seule fois, avec les mots à repérer sur le site de Withings, en anglais), donner son ClientID et son Secret à Foulée, puis autoriser l'accès (« Allow this app »). Tu reviens tout seul dans Foulée en passant un instant par une petite page relais du dépôt : Withings exige une adresse publique en https pour ce retour. Le premier import récupère ton historique, puis tes mesures arrivent avec la synchro, toutes les 3 heures.
- Une vue **Withings** s'ajoute juste après l'Accueil (ou après « Mon club ») : dernière pesée et composition corporelle face à celle d'il y a un mois, dernière tension avec les repères de la Société européenne d'hypertension, dernière nuit (phases, FC, respiration), activité, puis les courbes de chaque appareil présent. Elle s'en va si tu déconnectes Withings ; les mesures importées restent.
- 51 métriques Withings dans toutes les tuiles (catégorie « Withings ») et dans Claude Desktop : poids, masse grasse, musculaire, osseuse, eau, IMC (avec la taille saisie dans ton compte Withings), graisse viscérale, vitesse de l'onde de pouls, tension, pouls, SpO2, température, sommeil (phases, score, ronflements…), pas, distance, temps actif, calories.
- Le ClientID, le Secret et les jetons de Withings vont dans le Gestionnaire d'identification Windows (sur un serveur : un fichier que seul Foulée lit), ne se règlent que depuis la machine elle-même ou par Tailscale, et ne s'affichent jamais. Chaque profil relie son propre compte Withings.
- Si Withings retire l'accès (accès supprimé dans ton compte Withings, connexion expirée), un bandeau te propose de reconnecter ton compte, avec une notification près de l'horloge ; la synchro Garmin continue.
- Le message de fin de synchro parle de chaque source (« 2 nouvelle(s) séance(s)… ; mesures Withings à jour »).
- Réglages : la fin d'une synchro ne redessine plus toute la page (elle pouvait remonter en haut, et une saisie en cours se perdait).
- Aide : nouveau thème « Withings ». Mode démo : une balance, un tensiomètre et un Sleep Analyzer fictifs, avec leur vue.

## 0.5.1 — 11 novembre 2026

- **Mon club** : dans Réglages → Mon club, coche « Je fais partie d'un club » et saisis le numéro de club de ta licence (« N° Club », 6 chiffres). Une vue « Mon club » s'ajoute juste après l'Accueil : les coordonnées du club (président, siège avec un lien vers la carte, téléphone et e-mail cliquables, site), des boutons vers le **classement du club sur athle.fr** (saison en cours et précédente), sa page et son site, et ta licence, avec un rappel « Licence à renouveler » sur l'Accueil un mois avant la fin.
- Les coordonnées du club se remplissent **en un copier-coller** de sa fiche « Coordonnées et contacts » sur athle.fr. Foulée ne lit rien sur athle.fr (la FFA ne propose pas d'accès pour les applications) : le classement s'ouvre dans ton navigateur, chez la FFA, toujours à jour. Chaque profil a son club.
- **« Une nouvelle version est disponible ! »** en haut à droite de l'interface, dès qu'une version plus récente sort sur ton canal (stable ou bêta). Foulée regarde sur GitHub toutes les 3 heures, comme pour la synchro. Un clic montre la version et ses nouveautés, avec **Installer maintenant** (après ta confirmation, Foulée s'installe et se relance tout seul) ou **Voir dans les Réglages**.
- Une vue faite seulement de tuiles sans période (comme « Mon club ») n'affiche plus le sélecteur 7 j / 30 j / 90 j….
- Aide : nouveau thème « Mon club (FFA) » et nouvelle question sur les mises à jour. Claude Desktop voit ton club et les liens vers son classement (outil `reglages`).
- Une **présentation illustrée** de Foulée (PDF de 18 pages, avec le guide d'installation et la clé API Garmin) est disponible sur GitHub, dans le dossier `docs/presentation`.

## 0.5.0 — 11 novembre 2026

- **Plusieurs utilisateurs** : un profil par personne, avec ses données Garmin (sa propre clé API), ses vues, ses réglages, sa photo et sa synchro. Le prénom en haut à droite de l'Accueil, avec son chevron, pour passer d'un profil à l'autre ; code facultatif à 4 chiffres ; Réglages → Gestion des utilisateurs pour l'utilisateur principal, qui règle seul l'installation. Claude Desktop ne lit que les profils qui l'autorisent. Rien ne bouge pour une installation existante.
- **Page d'accueil** en tête des vues : bonjour (photo, poste du jour, objectif), forme du jour face à tes habitudes, ta semaine, records, Body Battery de la journée.
- **Allures selon ta VMA** : le tableau du club (55 à 120 % de VMA), les temps de passage sur piste, le test VAMEVAL. Mêmes chiffres que le classeur.
- **Horaires de travail** : bureau, 2x8, 3x8, 5x8 ou cycle personnalisé, heures des postes et congés ; les comparaisons, les fonds colorés des courbes et le nuage de points suivent tous les postes.
- **Zones FC et zones d'allure** au choix : celles de ta montre (avec ton seuil lactique), en pourcentage (FC max, FC de réserve, seuil, VMA…) ou bornes à la main comme sur Strava.
- **Toutes les données de Garmin dans les tuiles** : SpO2, respiration, dynamique de course, puissance… et toute autre valeur des réponses de Garmin. Nouvelles tuiles : Journée en détail (FC minute par minute, phases du sommeil, VFC de la nuit), Records, Séance : autres mesures.
- **Logo au choix ou photo de profil** (importée, ou reprise de Garmin Connect), jusque dans l'onglet du navigateur.
- **Aide et FAQ** en bas de la colonne de gauche (75 questions rangées par thème, avec une recherche) et **« Un bug, une idée ? Parles-en ! »** : un formulaire avec captures d'écran, envoyé sur GitHub ou par e-mail.
- **Export / import des réglages** (avec les vues et la photo) pour aligner le PC et le serveur.
- Le dépôt de Foulée est public : plus besoin de jeton GitHub pour les mises à jour, et un jeton expiré ne les bloque plus.
- Claude Desktop : nouveaux outils (allures, forme du jour, semaine, records, horaires, journée en détail, champs Garmin, profils).

## 0.4.1 — 10 novembre 2026

- Clé API Garmin supprimée ou régénérée dans Garmin Connect : Foulée la reconnaît (Garmin répond « clé inconnue », HTTP 404), arrête la synchro tout de suite et affiche le bandeau « remplace ta clé ». Avant, la synchro passait pour « partielle » et la date de dernière synchro avançait quand même.
- Une synchro où Garmin n'a rien pu fournir (panne, réseau) compte comme un échec : la synchro automatique réessaie dans la demi-heure, et la liste des séances reprend au bon endroit.
- Les messages d'erreur de Garmin ne gardent plus l'identifiant de la clé, y compris dans l'historique des synchros déjà enregistré.
- Les messages renvoient vers Réglages → Clé API Garmin, et non plus vers l'ancien script de l'installation manuelle.

## 0.4.0 — 10 novembre 2026

- Foulée s'installe avec un vrai programme Windows, `Foulee-Setup.exe` : pas de Python, pas de terminal, pas besoin d'être administrateur.
- L'application tourne en arrière-plan, avec son icône près de l'horloge : ouvrir, synchroniser, lancer avec Windows, quitter.
- Synchro automatique toutes les 3 heures tant que Foulée tourne (la mise en veille est prise en compte).
- Page d'accueil au premier lancement : la clé Garmin, le premier import, Claude Desktop, en trois étapes.
- La clé API Garmin se remplace depuis les Réglages ; si Garmin la refuse, un bandeau le signale et la synchro se met en pause.
- Dossier des données au choix : déplacer ses données ailleurs, utiliser un dossier existant ou reprendre celles d'une ancienne installation.
- Claude Desktop se relie d'un clic, avec le mode d'emploi.
- Mises à jour depuis les Réglages, canal stable ou bêta, sur le PC comme sur le serveur ; l'installateur téléchargé est vérifié par son empreinte SHA-256.
- Désinstallation propre, avec la possibilité d'effacer aussi ses données.

## 0.3.0

- Accès depuis le réseau local avec mot de passe (serveur).
- Bouton « Vérifier les mises à jour » dans les Réglages du serveur.

## 0.2.1

- Affichage sur téléphone corrigé (chiffres clés, tableau des postes, hauteurs des tuiles).

## 0.2.0

- Mode serveur (Debian) et appli pour le téléphone par Tailscale.

## 0.1.1

- Hub local pour les données Garmin : synchro, tableaux de bord configurables, serveur MCP pour Claude Desktop.
