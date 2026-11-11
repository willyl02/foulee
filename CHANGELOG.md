# Historique des versions

Les versions « bêta » (par exemple 0.4.0b1) sont des avant-premières : elles arrivent d'abord
sur le canal bêta (Réglages → Mises à jour → « Recevoir les versions bêta »), puis sortent en
version stable une fois éprouvées.

## 0.5.1b1 — 11 novembre 2026 (bêta)

- **Mon club** : dans Réglages → Mon club, coche « Je fais partie d'un club » et saisis le numéro de club de ta licence (« N° Club », 6 chiffres). Une vue « Mon club » s'ajoute juste après l'Accueil :
  - les coordonnées du club : président, siège (avec un lien vers la carte), téléphone et e-mail cliquables, site ;
  - des boutons vers le **classement du club sur athle.fr**, pour la saison en cours et la précédente, vers la page du club et vers son site ;
  - ta licence (numéro, type, date de fin), avec un rappel « Licence à renouveler » sur l'Accueil un mois avant la fin.
- Les coordonnées se remplissent **en un copier-coller** : la fiche « Coordonnées et contacts » de la page du club sur athle.fr, collée dans les réglages, suffit à Foulée pour reconnaître le président, l'adresse, le code postal, la ville, le téléphone, l'e-mail et le site.
- Foulée ne lit rien sur athle.fr : la FFA ne propose pas d'accès pour les applications. Le classement s'ouvre dans ton navigateur, directement chez la FFA, toujours à jour. Les saisons suivent celles de la FFA (du 1er septembre au 31 août).
- Décocher la case retire la vue et garde ce que tu as saisi. Chaque profil a son club.
- Une vue faite seulement de tuiles sans période (comme « Mon club ») n'affiche plus le sélecteur 7 j / 30 j / 90 j….
- Aide : nouveau thème « Mon club (FFA) ». Claude Desktop voit ton club et les liens vers son classement (outil `reglages`), et peut le régler.

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
