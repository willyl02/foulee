# Historique des versions

Les versions « bêta » (par exemple 0.4.0b1) sont des avant-premières : elles arrivent d'abord
sur le canal bêta (Réglages → Mises à jour → « Recevoir les versions bêta »), puis sortent en
version stable une fois éprouvées.

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
