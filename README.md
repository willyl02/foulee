# Foulée

Ton hub local de données sport et santé. Foulée récupère tes données Garmin grâce
à ta clé API personnelle, les range dans une base sur ton PC, et les met à
disposition de deux façons :

- une **interface** dans ton navigateur (http://127.0.0.1:8770), faite de vues et de
  tuiles que tu composes toi-même ;
- un **serveur MCP pour Claude Desktop**, pour poser tes questions à Claude directement.

Sur Windows, Foulée s'installe comme n'importe quel programme et tourne en
arrière-plan, avec son icône près de l'horloge. Installé sur un serveur à la maison,
il s'ouvre aussi **sur ton téléphone**, de partout, comme une appli (section 9).

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

## 1. Installer Foulée sur Windows

1. Télécharge **`Foulee-Setup-<version>.exe`** sur la page des versions :
   https://github.com/willyl02/foulee/releases (tant que le dépôt est privé, il faut
   être connecté à GitHub avec un compte qui y a accès).
2. Double-clique dessus. Pas besoin d'être administrateur : Foulée s'installe pour toi
   seul, dans `%LOCALAPPDATA%\Programs\Foulee`.
   Si Windows affiche « Windows a protégé votre ordinateur », clique sur
   « Informations complémentaires » puis « Exécuter quand même » (l'installateur
   n'est pas signé par un éditeur payant).
3. Deux cases te sont proposées : l'icône sur le Bureau, et le **lancement à
   l'ouverture de session** (conseillé : c'est ce qui permet la synchro automatique).
4. À la fin, Foulée s'ouvre dans ton navigateur sur sa **page d'accueil**, qui te
   guide en trois étapes :
   1. **ta clé API Garmin** (section 2) : colle-la, Foulée la fait vérifier par Garmin
      avant de l'enregistrer ;
   2. **le premier import** : choisis depuis quand (2 ans conseillé) ; compte quelques
      minutes, tu peux utiliser l'interface pendant ce temps ;
   3. **Claude Desktop** (facultatif) : un bouton relie Foulée à Claude (section 4).

Pas de clé sous la main ? Le bouton « Découvrir avec des données fictives » ouvre une
démo complète ; le bandeau « Quitter la démo » te ramène à tes vraies données.

Ensuite, Foulée tourne en arrière-plan avec son **icône près de l'horloge** (dans la
flèche « ^ » si Windows la range) : un clic ouvre l'interface, un clic droit propose
**Synchroniser maintenant**, **Lancer au démarrage de Windows** et **Quitter Foulée**.
Tant qu'il tourne, la synchro se fait toute seule **toutes les 3 heures** (au réveil
du PC si elle a été manquée). Relancer Foulée depuis le menu Démarrer rouvre simplement
l'interface.

### Tu avais installé Foulée avec l'archive (dossier `C:\Users\<toi>\Foulee`) ?

1. Dans ce dossier, double-clique sur **`Desinstaller-Foulee.cmd`** et réponds **N**
   à la question sur la clé : la nouvelle version la retrouve dans le Gestionnaire
   d'identification Windows. (Il retire la tâche planifiée, le raccourci et l'entrée
   de Claude Desktop ; tes données restent dans `data`.)
2. Installe `Foulee-Setup.exe` comme ci-dessus.
3. L'accueil te propose **« Reprendre ces données »** : ta base et tes fichiers FIT
   sont copiés depuis `C:\Users\<toi>\Foulee\data`, rien à réimporter de chez Garmin.
4. Relie Claude Desktop (étape 3 de l'accueil).
5. Une fois rassuré, supprime l'ancien dossier `C:\Users\<toi>\Foulee`.

## 2. Ta clé API Garmin

1. Ouvre la page **API personnelle** de Garmin Connect, sur le web et connecté :
   https://connect.garmin.com/app/settings/personalApiToken
   (ou Paramètres → API personnelle).
2. **Créer une clé**, accepte les conditions, choisis la durée (**1 an** conseillé),
   puis **Créer**.
3. **Copie la clé** avec le bouton « Copier » de Garmin, colle-la dans Foulée (accueil,
   ou **Réglages → Clé API Garmin**) puis **Tester et enregistrer**. Garmin ne
   l'affiche qu'une seule fois ; si tu la perds, régénère-la et recommence.

Foulée la range dans le **Gestionnaire d'identification Windows** (entrée « Foulee ») :
ni l'interface ni Claude ne la voient ensuite. Ne la colle jamais dans une conversation
ni dans un fichier, et ne fais pas de capture d'écran tant qu'elle est affichée.

**Clé perdue, expirée ou régénérée ?** Garmin t'envoie un e-mail environ une semaine
avant l'expiration. Si Garmin refuse ta clé, un bandeau rouge le signale et la synchro
se met en pause : crée une nouvelle clé, puis **Réglages → Clé API Garmin → Remplacer
la clé**. Pour l'effacer de ce PC : **Supprimer la clé sur ce PC**.

## 3. Utiliser l'interface

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
ou aucun), puis l'installation : clé Garmin, dossier des données, Claude Desktop,
démarrage avec Windows et mises à jour.

## 4. Utiliser Foulée avec Claude Desktop

1. **Réglages → Claude Desktop → Relier Foulée à Claude Desktop** (ou l'étape 3 de
   l'accueil). Claude Desktop doit être fermé pendant l'opération : si besoin, Foulée
   propose de le fermer pour toi. Une copie de sauvegarde de sa configuration est
   faite à côté.
2. Ouvre Claude Desktop. Au tout premier démarrage, compte une vingtaine de secondes :
   l'antivirus de Windows analyse les fichiers de Foulée une première fois.
3. Dans une conversation, bouton **+** → **Connecteurs** : « foulee » y figure.
4. Pose tes questions, par exemple :
   - « Compare mon sommeil et ma VFC entre semaines du matin et du soir depuis septembre. »
   - « Analyse ma séance de fractionné d'hier : tours, FC, découplage. »
   - « Où en est ma charge d'entraînement ? Suis-je frais pour samedi ? »
   - « Crée-moi une vue qui suit mes fractions longues et mon volume depuis octobre. »
   - « Ma VMA est maintenant de 16,5 km/h, mets à jour les réglages. »

Claude ne voit jamais ta clé : seuls les résultats des outils passent dans la
conversation. Claude n'a pas besoin que l'application Foulée soit ouverte : il lance
lui-même le serveur MCP de Foulée.

## 5. Où sont tes données

| Quoi | Où (installation par Foulee-Setup.exe) |
|---|---|
| Base de données | `%LOCALAPPDATA%\Foulee\donnees\foulee.db` (SQLite) |
| Fichiers FIT d'origine | `%LOCALAPPDATA%\Foulee\donnees\fit\` |
| Journaux | `%LOCALAPPDATA%\Foulee\donnees\logs\` (un par usage : app, mcp, sync…) |
| Réglages de l'installation | `%LOCALAPPDATA%\Foulee\config.json` |
| Clé API (et jeton GitHub éventuel) | Gestionnaire d'identification Windows, entrée « Foulee » |
| Jeton temporaire Garmin (24 h) | `%LOCALAPPDATA%\Foulee\garmin-jeton.json` |
| Programme | `%LOCALAPPDATA%\Programs\Foulee` (remplacé à chaque mise à jour) |

**Changer de dossier** : **Réglages → Dossier des données → Changer de dossier…**
(bouton « Parcourir… » ou chemin complet, par exemple `D:\Sport\Foulee`) :
- dossier vide ou nouveau : **Déplacer mes données ici** copie ta base et tes fichiers
  FIT, vérifie la copie, puis Foulée s'en sert ;
- dossier qui contient déjà des données Foulée (sauvegarde, disque externe, autre PC) :
  **Utiliser ce dossier** ; **Copier ces données ici** les reprend dans ton dossier actuel
  tant qu'il est encore vide.

L'ancien dossier n'est jamais effacé : supprime-le toi-même une fois rassuré. Évite un
dossier synchronisé par OneDrive (Documents, Bureau…) : tes données de santé
partiraient dans le cloud de Microsoft ; Foulée t'en avertit.

Sauvegarder Foulée = copier le dossier des données. Les réponses brutes de Garmin
y sont conservées : on peut tout recalculer sans rien redemander à Garmin.

## 6. Mises à jour, canal stable ou bêta

**Réglages → Mises à jour → Vérifier les mises à jour** : Foulée regarde sur GitHub
s'il existe une version plus récente et liste les nouveautés. **Mettre à jour
maintenant** télécharge l'installateur, vérifie son empreinte SHA-256, puis Foulée se
ferme, s'installe et se relance tout seul (une minute environ) ; la page se recharge
d'elle-même. Tes données, ta clé et tes vues ne bougent pas.

- **Recevoir les versions bêta** (case à cocher) : les avant-premières arrivent sur
  ton PC avant tout le monde, pour les essayer. Décoche pour revenir au canal stable ;
  Foulée ne redescend jamais de version : tu repasses en stable à la prochaine version
  stable plus récente que ta bêta.
- **Dépôt privé** : tant que le dépôt GitHub de Foulée est privé, GitHub demande un
  jeton pour montrer ses versions. Crée-le sur
  https://github.com/settings/personal-access-tokens/new : type « fine-grained »,
  accès au seul dépôt `foulee`, permission **Contents : Read-only**. Colle-le dans
  **Réglages → Mises à jour → Jeton GitHub**. Il est rangé dans le Gestionnaire
  d'identification Windows, comme ta clé Garmin.

Tu peux aussi télécharger une version plus récente de `Foulee-Setup.exe` et
l'installer par-dessus : c'est exactement ce que fait le bouton.

## 7. Désinstaller

Paramètres de Windows → **Applications** → **Foulée** → **Désinstaller**. Foulée se
ferme, se retire de Claude Desktop et du démarrage de Windows, puis te demande s'il
faut **effacer aussi tes données** (base, fichiers FIT, réglages, clé Garmin) :
réponds « Non » pour les garder, par exemple pour réinstaller plus tard. Si tu as rangé
tes données dans un dossier à toi, seuls les fichiers de Foulée y sont effacés.

## 8. Les commandes

Tout se fait depuis l'interface, mais chaque action existe aussi en ligne de commande.
Dans un terminal :

```
"%LOCALAPPDATA%\Programs\Foulee\python\python.exe" -m foulee <commande>
```

(installation à partir de l'archive : `.venv\Scripts\foulee <commande>` dans le dossier Foulee)

| Commande | Rôle |
|---|---|
| `app` | L'application : icône près de l'horloge, interface, synchro automatique ; `--quitter` pour la fermer |
| `sync` | Synchroniser (reprend là où la dernière s'est arrêtée) ; `--depuis 2023-01-01` pour remonter plus loin |
| `setup` | Enregistrer ou remplacer ta clé (lue dans le presse-papiers), la tester, lancer l'import |
| `status` | État : clé, base, dernière synchro |
| `dossier` | Voir le dossier des données ; `dossier D:\Sport\Foulee` pour y déplacer tes données, `--utiliser`, `--importer`, `--defaut` |
| `web` | Ouvrir l'interface sans l'application ; `--demo` pour la démo |
| `diagnostic` | Teste chaque flux Garmin et écrit un rapport **sans tes valeurs** (seulement les noms de champs) |
| `fit --jours 730` | Télécharger les fichiers FIT manquants sur une période |
| `reparse` | Reconstruire les tables depuis les réponses brutes (après une mise à jour de Foulée) |
| `claude-config` | Montrer où Claude Desktop range sa configuration et si Foulée y figure ; `--ecrire` pour l'ajouter, `--retirer` pour l'enlever |
| `acces-reseau` | Sur un serveur : choisir le mot de passe de l'accès par le réseau local |
| `reset-views` | Restaurer les vues d'origine |
| `forget-key` | Supprimer la clé de ce PC |

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
4. Il demande ta **clé Garmin** et lance le premier import. Tu peux aussi la
   remplacer plus tard dans **Réglages → Clé API Garmin**, ouverts par Tailscale.
5. **Sur le téléphone**, Tailscale connecté : ouvre l'adresse affichée
   (`https://foulee.<ton-réseau>.ts.net`), puis menu du navigateur → « Ajouter à
   l'écran d'accueil ». Foulée s'ouvre ensuite comme une appli.

### Depuis la maison, sans Tailscale

Le serveur répond aussi à son adresse sur le réseau local, par exemple
`http://192.168.0.19:8770`, mais cet accès reste **fermé** tant que tu n'as pas
choisi de mot de passe : ouvre Foulée par Tailscale, puis **Réglages → Accès depuis
le réseau local**. Les appareils de la maison verront alors une page de connexion
(la session dure 90 jours ; changer le mot de passe déconnecte tout le monde).

- Par Tailscale, aucun mot de passe n'est jamais demandé.
- Le mot de passe, la clé Garmin et le dossier des données se règlent seulement par
  Tailscale ou sur le serveur ; « Couper l'accès » referme le réseau local.
- Cette adresse n'est pas chiffrée : garde-la pour ta maison et n'ouvre jamais le
  port 8770 sur ta box Internet.

### Mettre à jour le serveur

**Réglages → Mises à jour → Vérifier les mises à jour**, puis **Mettre à jour
maintenant** : le serveur installe la dernière version de GitHub puis relance
l'interface (une minute environ). La case **Recevoir les versions bêta** fait suivre
la branche `beta` du dépôt au lieu de `main`. En coulisses, l'interface dépose une
demande que le service système `foulee-maj` traite ; il ne sait faire que deux choses :
vérifier, ou installer la dernière version du canal choisi.

Depuis une version antérieure à 0.3.0, qui n'a pas encore ce bouton, lance une seule
fois, en root dans la console du serveur :

```
cd /opt/foulee && git pull && bash scripts/mettre-a-jour-serveur.sh
```

Au quotidien (en root, dans la console du serveur) :

| Commande | Rôle |
|---|---|
| `foulee status` | État de la clé, de la base et de la dernière synchro |
| `foulee sync` | Synchroniser maintenant |
| `foulee acces-reseau` | Choisir le mot de passe du réseau local (`--desactiver` pour le couper) |
| `systemctl status foulee-web` | État de l'interface ; `journalctl -u foulee-web -n 50` pour son journal |
| `bash /opt/foulee/scripts/mettre-a-jour-serveur.sh` | Mettre à jour en ligne de commande (comme le bouton) ; `--canal beta` pour la dernière bêta |

Les données vivent dans `/var/lib/foulee`, la clé et l'empreinte du mot de passe dans
`/var/lib/foulee/secrets` (lisibles par le seul utilisateur `foulee`).

## 10. Installation manuelle (développeurs)

Sans l'installateur, à partir du code (archive `foulee-<version>.zip` ou `git clone`) :

1. **Débloque l'archive** : clic droit → Propriétés → coche « Débloquer » → OK.
2. **Décompresse-la dans `C:\Users\<toi>\Foulee`** (hors OneDrive).
3. Double-clique sur **`Installer-Foulee.cmd`** : il installe **uv** et les
   bibliothèques dans `.venv`, crée la base de démonstration, enregistre ta clé (lue
   dans le presse-papiers), ajoute Foulée à Claude Desktop, crée le raccourci et la
   tâche planifiée « Foulee - synchro ».

Dans ce mode, les données restent dans `Foulee\data`, la mise à jour se fait avec
`Mettre-a-jour-Foulee.cmd` (nouvelle archive dans Téléchargements), et
`.venv\Scripts\foulee app` lance l'application avec son icône.

Pour développer : `uv sync`, puis `uv run pytest` (tests) et `uv run foulee web --demo`.

## 11. Publier une version (canaux main et beta)

- **`main`** = canal stable, **`beta`** = canal bêta. Les serveurs suivent l'une ou
  l'autre branche ; les PC suivent les versions publiées sur GitHub (une bêta y est
  une « pré-version »).
- **Publier, c'est changer le numéro de version** dans `pyproject.toml` et
  `foulee/__init__.py` : une bêta s'écrit `0.5.0b1`, `0.5.0b2`…, la version stable
  `0.5.0`. Ses nouveautés vont en tête de `CHANGELOG.md` : ce sont elles que Foulée
  affiche avant la mise à jour.
- Une bêta poussée sur `beta`, ou une version stable poussée sur `main` (en général en
  fusionnant `beta`), déclenche GitHub Actions (`.github/workflows/windows.yml`) : tests
  sous Windows, construction de `Foulee-Setup-<version>.exe` (`packaging/build.ps1`),
  essai de bout en bout sur un Windows propre (installation, relance, Claude, mise à
  jour par-dessus, désinstallation : `packaging/smoke-test.ps1`), puis publication de la
  version, avec son étiquette `v<version>` et ses empreintes SHA-256.
- Tant que la version est déjà publiée, un envoi ne déclenche qu'une petite
  vérification (pas de minutes Windows consommées). Lancé à la main (Actions →
  Windows → Run workflow), l'enchaînement construit et essaie l'installateur sans rien
  publier : il reste téléchargeable dans les artefacts de l'exécution.

## 12. Dépannage

- **Rien ne se passe quand je lance Foulée** : il tourne peut-être déjà ; regarde près
  de l'horloge (flèche « ^ »). Journal : `%LOCALAPPDATA%\Foulee\donnees\logs\app.log`.
- **Claude ne voit pas Foulée** : **Réglages → Claude Desktop** indique si Foulée est
  relié, et à quelle installation ; « Relier » réécrit l'entrée (Claude fermé). La
  version « paquet » de Claude Desktop lit
  `%LOCALAPPDATA%\Claude-Data\claude_…\claude_desktop_config.json` (Paramètres →
  Développeur → Modifier la configuration ouvre le bon fichier). Journal du serveur :
  `mcp-server-foulee.log`, dans `%LOCALAPPDATA%\Claude\logs\` ou `%APPDATA%\Claude\logs\`.
- **« Garmin refuse cette clé (HTTP …) »** en l'enregistrant : recopie la clé avec le
  bouton « Copier » et réessaie ; si elle vient d'être créée, attends une minute ;
  vérifie qu'elle figure, active, sur la page API personnelle. Le message cite la
  réponse de Garmin sans jamais montrer ta clé : tu peux le transmettre à Claude.
- **Bandeau « Garmin refuse ta clé »** alors que tout marchait : elle a expiré ou été
  régénérée, remplace-la (section 2).
- **La mise à jour indique « ajoute un jeton GitHub »** : le dépôt est privé
  (section 6).
- **Le téléphone affiche « Foulée est injoignable »** : l'appli Tailscale est
  déconnectée sur le téléphone, ou le serveur est arrêté (`systemctl status foulee-web`).
- **La mise à jour du serveur ne répond pas** : `systemctl status foulee-maj.path`
  sur le serveur ; le détail de la dernière tentative est dans `/var/lib/foulee/maj/etat.json`.
  Si GitHub refuse l'accès, le jeton du serveur a expiré : crée-en un nouveau et colle-le
  au prochain `git pull` (en root, dans `/opt/foulee`).
- **Une donnée semble manquer** : lance `foulee diagnostic` et transmets le rapport
  à Claude ; il ne contient que des noms de champs et des statuts.
- **Le port 8770 est déjà pris** : l'application prend le suivant libre (8771…) et
  ouvre la bonne adresse ; en ligne de commande, `foulee web --port 8780`.
- **La carte reste grise** : le fond de carte vient d'Internet (OpenStreetMap ou IGN).
  Le tracé s'affiche même sans fond.

## 13. Ce que l'API personnelle ne donne pas

- Elle est en **lecture seule** : impossible d'envoyer une séance ou un parcours
  sur la montre.
- Pas de flux « disponibilité d'entraînement » ni « statut d'entraînement » :
  Foulée calcule sa propre charge (charge Garmin de chaque séance, ou TRIMP).
- Garmin n'a pas précisé si les FIT obtenus par l'API personnelle contiennent
  tous les champs propriétaires : le diagnostic te le dira.

## 14. Faire évoluer Foulée

```
foulee/
  garmin/          connecteur Garmin : client (rythme, reprises), parseurs, synchro, diagnostic
  desktop.py       application Windows : icône près de l'horloge, synchro auto, une seule copie
  web.py           API locale + pages, accès réseau, clé, dossier, Claude, mises à jour
  updates.py       mises à jour (versions GitHub du PC, canaux stable et bêta)
  datadir.py       dossier des données : déplacer, utiliser, importer
  claude_desktop.py  configuration de Claude Desktop (toutes ses variantes)
  vault.py         secrets : clé Garmin, jeton GitHub (Gestionnaire d'identification Windows)
  keyinput.py      lecture de la clé (presse-papiers, nettoyage) sans jamais l'afficher
  sync.py          chef d'orchestre des sources (ajouter Withings ou Strava = une entrée ici)
  db.py            schéma SQLite, réglages
  metrics.py       catalogue des métriques (libellés, unités, formats)
  analysis.py      tous les calculs (séries, charge, zones, postes, objectif…)
  views.py         types de tuiles et vues par défaut
  access.py        mot de passe du réseau local (empreinte, cookie signé, anti-acharnement)
  mcp_server.py    outils pour Claude Desktop
  uninstall.py     ménage avant désinstallation
  demo.py          données fictives
  static/          interface (HTML/CSS/JS, ECharts et Leaflet embarqués), appli installable (manifest, sw.js)
packaging/         installateur Windows (Inno Setup), construction et essai de bout en bout
scripts/           installation et mise à jour : archive Windows (.ps1), serveur Linux (.sh, maj_serveur.py)
tests/             tests, dont un faux serveur Garmin pour tester toute la chaîne
```

Pour une nouvelle source : un dossier à côté de `garmin/` qui écrit dans les mêmes
tables (`daily`, `activities`, `laps`, `streams`) avec sa propre valeur de `source`,
puis une entrée dans `sync.SOURCES`. Les vues, les calculs et Claude en profitent
sans autre changement.

Tests : `uv run pytest`.
