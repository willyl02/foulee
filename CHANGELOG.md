# Historique des versions

Les versions « bêta » (par exemple 0.4.0b1) sont des avant-premières : elles arrivent d'abord
sur le canal bêta (Réglages → Mises à jour → « Recevoir les versions bêta »), puis sortent en
version stable une fois éprouvées.

## 0.5.0b3 — 11 novembre 2026 (bêta)

- Formulaire « Un bug, une idée ? » : **envoi par e-mail** pour qui n'a pas de compte GitHub. Le logiciel de messagerie s'ouvre avec un e-mail prêt (titre, message, informations techniques) ; les captures se téléchargent pour être jointes.
- Le dépôt de Foulée est désormais **public** : l'installateur se télécharge et les sujets se lisent sans compte GitHub, et les mises à jour n'ont plus besoin de jeton. Un jeton déjà enregistré qui expire ne bloque plus les mises à jour : Foulée réessaie sans.

## 0.5.0b2 — 11 novembre 2026 (bêta)

- **Aide et FAQ**, en bas de la colonne de gauche : 68 questions rangées en 11 thèmes (premiers pas, clé Garmin, synchro et données, tableaux de bord, entraînement et calculs, horaires de travail, Claude Desktop, téléphone et serveur, installation et mises à jour, vie privée, aide et retours). Un chevron déplie chaque réponse ; recherche sans accents (« cle refusee » trouve « clé refusée ») ; liens directs vers la bonne rubrique des réglages.
- **« Un bug, une idée ? Parles-en ! »** : un formulaire pour signaler un bug, proposer une idée ou poser une question, avec un titre, un message et des captures d'écran (glissées, collées avec Ctrl+V ou choisies, cinq au plus). Il propose d'abord les réponses de l'aide qui ressemblent au titre, explique ce qu'on trouve sur la page des sujets GitHub (ouverts, fermés, étiquettes, recherche, 👍 plutôt qu'un doublon), joint si tu le veux quelques informations techniques lisibles avant l'envoi (version, système, navigateur, page d'origine, état de la clé et de la synchro ; jamais la clé ni le chemin du dossier), puis ouvre GitHub avec le sujet déjà rempli. Chaque capture se copie ou se télécharge pour la coller sur GitHub. Le brouillon est gardé si tu vas voir l'aide entre-temps.
- Sur GitHub, l'étiquette (bug, enhancement, question) se pose toute seule d'après le début du titre des sujets préparés par Foulée.

## 0.5.0b1 — 10 novembre 2026 (bêta)

- **Page d'accueil** en tête des vues : bonjour (ta photo, ton poste du jour, ton objectif), forme du jour (FC de repos, VFC, sommeil, Body Battery, fraîcheur, SpO2, chacun face à tes habitudes, avec une phrase de synthèse), ta semaine (postes, séances, volume et charge face aux 4 semaines d'avant), records, Body Battery de la journée.
- **Allures selon ta VMA** : le tableau du club (55 à 120 % de VMA, allures et vitesses, bandes de couleur), les temps de passage sur piste (200 à 800 m), le test VAMEVAL (palier, VMA validée, VMA interpolée) et une autre VMA à comparer. Mêmes chiffres que le classeur.
- **Horaires de travail** : bureau, 2x8 matin / soir selon la parité des semaines, 3x8, 5x8 ou cycle personnalisé, heures de chaque poste, congés. Les comparaisons, les fonds colorés des courbes et le nuage de points suivent tous les postes ; l'ancien réglage matin / soir est repris tel quel.
- **Zones FC** au choix : celles de ta montre (lues chez Garmin, avec ton seuil lactique), % de la FC max, % de la FC de réserve, % de la FC au seuil, ou bornes à la main comme sur Strava. **Zones d'allure** : % de la VMA, % de la vitesse au seuil, ou allures à la main. Une barre à cinq couleurs dont on tire les séparations.
- **Toutes les données de Garmin dans les tuiles** : SpO2, respiration, minutes et objectifs, Body Battery de la nuit et des séances, phases du sommeil en %, dynamique de course (temps de contact au sol, oscillation et ratio vertical, foulée), puissance, transpiration… et toute autre valeur des réponses de Garmin, au choix dans une liste rangée par catégories, avec une recherche.
- Nouvelles tuiles : **Journée en détail** (FC minute par minute, Body Battery, phases du sommeil, VFC de la nuit), **Records** (1 km, 1 mile, 5 km, 10 km, semi…), **Séance : autres mesures**. Le choix des tuiles est rangé par catégories, avec une recherche.
- **Logo au choix** (sept dessins) ou **photo de profil** (importée et recadrée dans le navigateur, ou reprise de Garmin Connect), jusque dans l'onglet du navigateur.
- **Export / import des réglages** (avec les vues et la photo) pour aligner le PC et le serveur.
- Claude Desktop : nouveaux outils allures_vma, forme_du_jour, semaine, records, horaires, journee_detail et champs_garmin.

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
