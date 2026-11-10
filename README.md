# Foulée

Ton hub local de données sport et santé. Foulée récupère tes données Garmin grâce
à ta clé API personnelle, les range dans une base sur ton PC, et les met à
disposition de deux façons :

- une **interface web locale** (http://127.0.0.1:8770), faite de vues et de tuiles
  que tu peux modifier ;
- un **serveur MCP pour Claude Desktop**, pour me poser tes questions directement.

Installé sur un serveur à la maison, Foulée s'ouvre aussi **sur ton téléphone**,
de partout, comme une appli (section 9).

Aucun service intermédiaire : ta machine parle directement à Garmin (client Python
officiel de Garmin), et tout est stocké chez toi.

```
Garmin (API personnelle)  ──►  connecteurs + synchro  ──►  base locale (SQLite + fichiers FIT)
                                                              │
                                                     moteur d'analyse
                                                     ┌────────┴────────┐
                                              serveur MCP         serveur web local
                                                   │                    │
                                            Claude Desktop        interface (navigateur)
```

---

## 1. Avant de commencer : ta clé API Garmin

1. Ouvre la page **API personnelle** de Garmin Connect, sur le web et connecté :
   https://connect.garmin.com/app/settings/personalApiToken
   (ou Paramètres → API personnelle).
2. **Créer une clé**, accepte les conditions, choisis la durée (**1 an** conseillé),
   puis **Créer**.
3. **Copie la clé** avec le bouton « Copier » de Garmin et **laisse la fenêtre
   ouverte** jusqu'à ce que Foulée confirme : il lit la clé dans le presse-papiers.
   Garmin ne l'affiche qu'une seule fois ; si tu la perds, crée-en simplement une autre.

Ne la colle jamais dans une conversation ni dans un fichier du projet, et ne fais
pas de capture d'écran tant qu'elle est affichée.

## 2. Installer (Windows 11, sans droits administrateur)

1. **Débloque l'archive** : clic droit sur l'archive (`foulee-<version>.zip`) → Propriétés → coche
   « Débloquer » → OK. Sans ça, Windows bloque les scripts.
2. **Décompresse-la dans `C:\Users\<toi>\Foulee`**. Évite Documents et Bureau
   s'ils sont synchronisés par OneDrive : tes données partiraient dans le cloud.
3. Double-clique sur **`Installer-Foulee.cmd`**. Le script demande ton accord à
   chaque étape :
   1. installe **uv** si besoin (l'outil qui installe Python et les bibliothèques
      dans le dossier `.venv` du projet, sans toucher au reste du PC) ;
   2. crée la **base de démonstration** (données fictives, à part) ;
   3. enregistre ta **clé API** : copie-la chez Garmin, puis appuie simplement sur
      **Entrée**. Foulée la lit dans le presse-papiers et te dit ce qu'il a lu
      (nombre de caractères, début « GCDC_ ») sans jamais l'afficher. Il la fait
      vérifier par Garmin, la range dans le Gestionnaire d'identification Windows,
      vide le presse-papiers, puis lance le **premier import** (2 ans par défaut ;
      compte quelques minutes, davantage pour les fichiers FIT) ;
   4. ajoute Foulée à **Claude Desktop** : il te demande de quitter Claude Desktop
      s'il est ouvert, puis complète sa configuration (sauvegardée avant) ;
   5. crée le raccourci **Foulée** sur le Bureau ;
   6. crée la tâche planifiée **« Foulee - synchro »** (chaque jour dès 5 h 17, puis toutes les
      3 heures, invisible ; si le PC était éteint, elle rattrape au réveil).

Si Windows affiche « Windows a protégé votre ordinateur », clique sur
« Informations complémentaires » puis « Exécuter quand même » : c'est le script
que tu viens de décompresser.

## 3. Utiliser l'interface

- Double-clique sur le raccourci **Foulée** : une petite fenêtre s'ouvre (réduite)
  et ton navigateur affiche l'interface. **Garde cette fenêtre ouverte** tant que
  tu utilises l'interface ; ferme-la pour arrêter.
- **`Ouvrir-Foulee-demo.cmd`** ouvre la version démo (port 8771), pour essayer sans
  risque.

Ce que tu y trouves :

| Vue | Contenu |
|---|---|
| Aujourd'hui | Nuit, VFC, FC de repos, Body Battery au réveil, stress, km sur 7 jours, fraîcheur, dernière séance |
| Entraînement | Km par semaine, forme et fatigue (charge chronique, aiguë, fraîcheur, ratio), zones FC et d'allure, liste des séances |
| Séance | Résumé, carte, courbes synchronisées (FC, allure, altitude, cadence…), tours ou découpage au km |
| Récup & postes | Semaines du matin contre semaines du soir, sommeil, VFC, FC de repos, nuage sommeil → VFC, calendrier |
| Cap semi de Paris | Compte à rebours, allure cible, fractions rapides face à l'allure cible, volume, charge, zones, VO2max |

**Tout se modifie** : bouton « Modifier la vue », puis glisse les tuiles, change
leur taille, règle-les (roue dentée) ou ajoute-en. « Nouvelle vue » dans le menu
crée une vue vide. Les vues s'exportent et s'importent en JSON.

Les **Réglages** contiennent ta VMA (zones d'allure, fractions), tes FC (laisse
vide pour utiliser tes zones Garmin), ton objectif course, tes postes (parité des
semaines, semaines de congés à exclure), le fond de carte (OpenStreetMap, Plan IGN
ou aucun).

## 4. Utiliser Foulée avec Claude Desktop

1. **Relance Claude Desktop** (clic droit sur son icône près de l'horloge →
   Quitter, puis rouvre-le).
2. Paramètres → **Développeur** : « foulee » apparaît comme actif. Au tout premier
   démarrage, compte une vingtaine de secondes : l'antivirus de Windows analyse les
   fichiers de Foulée une première fois.
3. Dans une conversation, bouton **+** → **Connecteurs** : « foulee » y figure.
4. Pose tes questions, par exemple :
   - « Compare mon sommeil et ma VFC entre semaines du matin et du soir depuis septembre. »
   - « Analyse ma séance de fractionné d'hier : tours, FC, découplage. »
   - « Où en est ma charge d'entraînement ? Suis-je frais pour samedi ? »
   - « Crée-moi une vue qui suit mes fractions longues et mon volume depuis octobre. »
   - « Ma VMA est maintenant de 16,5 km/h, mets à jour les réglages. »

Claude ne voit jamais ta clé : seuls les résultats des outils passent dans la
conversation.

## 5. Les commandes

Dans le dossier Foulee, ouvre un terminal (clic droit → « Ouvrir dans le
terminal ») et tape `.venv\Scripts\foulee <commande>` :

| Commande | Rôle |
|---|---|
| `setup` | Enregistrer ou remplacer ta clé (lue dans le presse-papiers), la tester, lancer l'import |
| `sync` | Synchroniser (reprend là où la dernière s'est arrêtée) ; `--depuis 2023-01-01` pour remonter plus loin |
| `web` | Ouvrir l'interface ; `--demo` pour la démo |
| `status` | État : clé, base, dernière synchro |
| `diagnostic` | Teste chaque flux Garmin et écrit un rapport **sans tes valeurs** (seulement les noms de champs) |
| `fit --jours 730` | Télécharger les fichiers FIT manquants sur une période |
| `reparse` | Reconstruire les tables depuis les réponses brutes (après une mise à jour de Foulée) |
| `claude-config` | Montrer où Claude Desktop range sa configuration et si Foulée y figure ; `--ecrire` pour l'ajouter, `--retirer` pour l'enlever |
| `reset-views` | Restaurer les vues d'origine |
| `forget-key` | Supprimer la clé de ce PC |

Raccourcis : `Synchroniser.cmd`, `Configurer-cle-Garmin.cmd`, `Mettre-a-jour-Foulee.cmd`,
`Desinstaller-Foulee.cmd`.

## 6. Où sont tes données

| Quoi | Où |
|---|---|
| Base de données | `Foulee\data\foulee.db` (SQLite) |
| Fichiers FIT d'origine | `Foulee\data\fit\` |
| Base démo | `Foulee\data\foulee-demo.db` |
| Journaux | `Foulee\data\logs\` (un par usage : web, mcp, sync…) |
| Clé API | Gestionnaire d'identification Windows, entrée « Foulee » |
| Jeton temporaire (24 h) | `%LOCALAPPDATA%\Foulee\garmin-jeton.json` |

Sauvegarder Foulee = copier le dossier `data`. Les réponses brutes de Garmin
y sont conservées : on peut tout recalculer sans rien redemander à Garmin.

## 7. Quand ta clé expire

Garmin t'envoie un e-mail environ une semaine avant. Crée une nouvelle clé dans
Garmin Connect et copie-la, puis double-clique sur `Configurer-cle-Garmin.cmd`,
réponds « o » pour remplacer l'ancienne et appuie sur Entrée.

## 8. Mettre à jour Foulée

1. Télécharge la nouvelle archive (`foulee-<version>.zip`) : elle arrive dans Téléchargements.
2. Double-clique sur **`Mettre-a-jour-Foulee.cmd`** dans ton dossier Foulee. Il prend
   l'archive la plus récente de Téléchargements (ou celle que tu glisses sur le
   fichier), affiche les deux versions, arrête Foulée s'il tourne (avec ton accord),
   remplace le programme et met à jour les bibliothèques.
3. Relance Claude Desktop et l'interface.

Tes données (`data`), ta clé et tes vues ne bougent pas : l'archive ne les contient pas.

Depuis la version 0.1.0, qui n'a pas encore ce script : débloque l'archive (section 2), ouvre-la, entre dans
son dossier `Foulee`, sélectionne tout (Ctrl+A), copie (Ctrl+C), puis colle (Ctrl+V)
dans ton dossier Foulee et choisis « Remplacer les fichiers dans la destination ».

## 9. Sur ton téléphone : Foulée sur un serveur

Pour consulter Foulée de partout, il tourne en permanence sur un petit serveur
Linux (par exemple un conteneur Debian sous Proxmox), et **Tailscale** le relie
à tes seuls appareils, en HTTPS. Rien n'est publié sur Internet.

```
Garmin  ──►  serveur : Foulée + synchro toutes les 3 h  ──►  Tailscale (tes appareils)  ──►  téléphone
```

Il te faut :
- un conteneur **Debian 12 ou 13** avec accès à Internet (1 cœur, 1 Go de mémoire,
  8 Go de disque) ;
- un compte **Tailscale** (gratuit pour un usage perso) et l'appli Tailscale sur
  ton téléphone ;
- un **jeton GitHub en lecture seule**, pour que le serveur récupère le code du
  dépôt privé : sur https://github.com/settings/personal-access-tokens/new, donne-lui
  un nom (« foulee-serveur »), limite-le au seul dépôt `foulee` et accorde
  uniquement « Contents : Read-only ».

Installation, dans la console du conteneur (en root) :

```
apt update && apt install -y git && git config --global credential.helper store && git clone https://github.com/<ton-compte>/foulee /opt/foulee && bash /opt/foulee/scripts/installer-serveur.sh
```

1. Git demande ton nom d'utilisateur GitHub puis un mot de passe : colle le jeton.
   Il est gardé pour les mises à jour.
2. Le script installe Python et les bibliothèques, puis les services : l'interface
   (`foulee-web`) et la synchro toutes les 3 heures (`foulee-sync.timer`).
3. Il affiche un lien Tailscale : ouvre-le et valide l'ajout du serveur. Si un
   second lien demande d'activer HTTPS (« Serve »), valide-le aussi.
4. Il demande ta **clé Garmin** et lance le premier import. Pour reprendre celle du
   PC sans l'afficher, tape dans PowerShell, depuis le dossier Foulee du PC :
   `.venv\Scripts\python.exe -c "from foulee import vault; print(vault.get_key(), end='')" | Set-Clipboard`
   puis colle-la dans la console du conteneur (clic droit → Coller, ou Ctrl+Maj+V).
5. **Sur le téléphone**, Tailscale connecté : ouvre l'adresse affichée
   (`https://foulee.<ton-réseau>.ts.net`), puis menu du navigateur → « Ajouter à
   l'écran d'accueil ». Foulée s'ouvre ensuite comme une appli.

Au quotidien (en root, dans la console du serveur) :

| Commande | Rôle |
|---|---|
| `foulee status` | État de la clé, de la base et de la dernière synchro |
| `foulee sync` | Synchroniser maintenant |
| `systemctl status foulee-web` | État de l'interface ; `journalctl -u foulee-web -n 50` pour son journal |
| `bash /opt/foulee/scripts/mettre-a-jour-serveur.sh` | Mettre Foulée à jour depuis GitHub |

Les données vivent dans `/var/lib/foulee`, la clé dans `/var/lib/foulee/secrets`
(lisible par le seul utilisateur `foulee`). Le serveur n'écoute que sur lui-même :
c'est Tailscale qui relaie l'interface.

## 10. Dépannage

- **Claude ne voit pas Foulée** : lance `.venv\Scripts\foulee claude-config`. Il
  liste les fichiers de configuration de Claude Desktop présents sur ton PC et dit
  lesquels contiennent Foulée. La version de Claude Desktop pour Windows installée
  comme « paquet » lit `%LOCALAPPDATA%\Claude-Data\claude_…\claude_desktop_config.json`
  (Paramètres → Développeur → Modifier la configuration ouvre le bon fichier). Pour
  réécrire l'entrée : `foulee claude-config --ecrire`, Claude Desktop fermé. Journal
  du serveur : `mcp-server-foulee.log`, dans `%LOCALAPPDATA%\Claude\logs\` (version
  paquet) ou `%APPDATA%\Claude\logs\`.
- **« Garmin a refusé cette clé (HTTP …) » pendant la configuration** : recopie la
  clé avec le bouton « Copier » et réessaie ; si elle vient d'être créée, clique sur
  « Terminé » chez Garmin (elle reste dans le presse-papiers), attends une minute et
  réessaie ; vérifie qu'elle figure, active, sur la page API personnelle. Le message
  cite la réponse de Garmin sans jamais montrer ta clé : tu peux le transmettre à Claude.
- **« Garmin a refusé la clé » pendant une synchro, alors que tout marchait** : elle a
  expiré ou été supprimée, crée-en une nouvelle (section 7).
- **Le téléphone affiche « Foulée est injoignable »** : l'appli Tailscale est
  déconnectée sur le téléphone, ou le serveur est arrêté (`systemctl status foulee-web`).
- **Une donnée semble manquer** : lance `foulee diagnostic` et transmets le rapport
  à Claude ; il ne contient que des noms de champs et des statuts.
- **Le port 8770 est déjà pris** : `foulee web --port 8780`.
- **La carte reste grise** : le fond de carte vient d'Internet (OpenStreetMap ou IGN).
  Le tracé s'affiche même sans fond.

## 11. Ce que l'API personnelle ne donne pas

- Elle est en **lecture seule** : impossible d'envoyer une séance ou un parcours
  sur la montre.
- Pas de flux « disponibilité d'entraînement » ni « statut d'entraînement » :
  Foulée calcule sa propre charge (charge Garmin de chaque séance, ou TRIMP).
- Garmin n'a pas précisé si les FIT obtenus par l'API personnelle contiennent
  tous les champs propriétaires : le diagnostic te le dira.

## 12. Faire évoluer Foulée

```
foulee/
  garmin/        connecteur Garmin : client (rythme, reprises), parseurs, synchro, diagnostic
  keyinput.py    lecture de la clé (presse-papiers, nettoyage) sans jamais l'afficher
  sync.py        chef d'orchestre des sources (ajouter Withings ou Strava = une entrée ici)
  db.py          schéma SQLite, réglages
  metrics.py     catalogue des métriques (libellés, unités, formats)
  analysis.py    tous les calculs (séries, charge, zones, postes, objectif…)
  views.py       types de tuiles et vues par défaut
  web.py         API locale + pages
  mcp_server.py  outils pour Claude Desktop
  demo.py        données fictives
  static/        interface (HTML/CSS/JS, ECharts et Leaflet embarqués), appli installable (manifest, sw.js)
scripts/         installation et mise à jour : Windows (.ps1) et serveur Linux (.sh)
tests/           tests, dont un faux serveur Garmin pour tester toute la chaîne
```

Pour une nouvelle source : un dossier à côté de `garmin/` qui écrit dans les mêmes
tables (`daily`, `activities`, `laps`, `streams`) avec sa propre valeur de `source`,
puis une entrée dans `sync.SOURCES`. Les vues, les calculs et Claude en profitent
sans autre changement.

Tests : `uv run --group dev pytest`.
