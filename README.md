# Foulée

Ton hub local de données sport et santé. Foulée récupère tes données Garmin grâce
à ta clé API personnelle (et, si tu veux, tes mesures **Withings** : balance,
tensiomètre, Sleep Analyzer), les range dans une base sur ton PC, et les met à
disposition de deux façons :

- une **interface** dans ton navigateur (http://127.0.0.1:8770), faite de vues et de
  tuiles que tu composes toi-même ;
- un **serveur MCP pour Claude Desktop**, pour poser tes questions à Claude directement.

Sur Windows, Foulée s'installe comme n'importe quel programme et tourne en
arrière-plan, avec son icône près de l'horloge. Installé sur un serveur à la maison,
il s'ouvre aussi **sur ton téléphone**, de partout, comme une appli (section 9).

**Présentation illustrée** (18 pages, avec le téléchargement, l'installation pas à pas
et la clé API Garmin) : [le PDF](docs/presentation/Foulee-presentation-beta-testeurs.pdf),
ou [les mêmes pages en images JPG](docs/presentation/Foulee-presentation-pages-jpg.zip)
à partager.

Aucun service intermédiaire : ta machine parle directement à Garmin (client Python
officiel de Garmin) et à Withings, et tout est stocké chez toi.

```
Garmin (API personnelle) ─┐
                          ├─►  connecteurs + synchro  ──►  base locale (SQLite + fichiers FIT)
Withings (API publique) ──┘                                   │
                                                     moteur d'analyse
                                                     ┌────────┴────────┐
                                              serveur MCP         serveur web local
                                                   │                    │
                                            Claude Desktop        interface (navigateur)
```

---

## 1. Installer Foulée sur Windows

En images : pages 15 à 18 de la [présentation](docs/presentation/Foulee-presentation-beta-testeurs.pdf).

1. Télécharge **`Foulee-Setup-<version>.exe`** sur la page des versions :
   https://github.com/willyl02/foulee/releases (pas besoin de compte GitHub).
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
Tant qu'il tourne, la synchro se fait toute seule, **toutes les 3 heures** par défaut
(au réveil du PC si elle a été manquée ; rythme réglable, voir plus bas). Relancer
Foulée depuis le menu Démarrer rouvre simplement l'interface.

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

### Relier ton compte Withings (facultatif)

Balance, tensiomètre, Sleep Analyzer, montre Withings : Foulée récupère aussi tes
pesées (avec la composition corporelle), ta tension, tes nuits et tes pas. Une vue
**Withings** s'ajoute alors juste après l'Accueil, et les mesures Withings sont dans
toutes les tuiles (catégorie « Withings ») et dans Claude Desktop.

Withings ne donne pas une simple clé comme Garmin : chacun crée sa propre « appli »
(gratuite) sur le site de Withings pour développeurs. **Réglages → Withings** guide
pas à pas ; compte une dizaine de minutes, une seule fois, de préférence depuis le PC :

1. **Crée ton appli Withings** sur le
   [tableau de bord développeur de Withings](https://developer.withings.com/dashboard/),
   connecté avec ton compte Withings habituel : *Withings public cloud* → **Create an
   application** → **Public API integration**. Dans le formulaire : *Target
   environment* **Development**, un nom (« Foulée »), une description, et dans
   **Registered URLs** exactement cette adresse (bouton « Copier » dans Foulée) :
   `https://willyl02.github.io/foulee/withings/`
2. **Colle le ClientID et le Secret** affichés par Withings dans Foulée, puis
   **Enregistrer**. Comme la clé Garmin, ils vont dans le Gestionnaire d'identification
   Windows (sur un serveur : dans un fichier que seul Foulée lit) et ne se règlent que
   depuis la machine elle-même ou par Tailscale.
3. **Connecter mon compte Withings** : la page de Withings s'ouvre, clique sur **Allow
   this app**. Tu reviens tout seul dans les Réglages, et le premier import démarre.
   Ensuite, tes mesures arrivent avec la synchro, toutes les 3 heures par défaut.

**Pourquoi une page relais ?** Après « Allow », Withings renvoie ton navigateur vers
une adresse publique en https, enregistrée dans ton appli : il refuse l'adresse de ton
PC. Cette adresse est une petite page de ce dépôt (dossier `docs/withings`, publiée par
GitHub Pages), la même pour tout le monde : elle renvoie aussitôt ton navigateur vers
ton Foulée, et seulement vers une adresse de la maison (le PC, le réseau local,
Tailscale). Elle ne garde rien. Elle voit seulement passer un code à usage unique,
valable 30 secondes et inutilisable sans ton Secret, qui ne quitte jamais Foulée.

Bon à savoir : Withings demande un abonnement **Withings+** aux comptes créés après le
12 octobre 2026 pour partager leurs données avec une appli comme Foulée. Chaque profil
relie son propre compte Withings. Si Withings retire l'accès (supprimé dans ton compte
Withings, ou connexion expirée), un bandeau te propose de reconnecter le compte.
**Déconnecter Withings** arrête la synchro de tes mesures et retire la vue ; les
mesures déjà importées restent.

### Relier ton compte Strava (facultatif, en lecture seule)

Une montre Coros, Suunto, Polar ou Apple, un compteur de vélo, une séance de
musculation notée sur Strava : ces séances rejoignent les tiennes dans toutes les vues
(listes, volumes, charge, renfo). Avec une montre Garmin, Strava apporte aussi le titre,
la description et les kudos de tes séances, affichés sur la séance Garmin. Sans montre
Garmin, Foulée fonctionne avec Strava seul.

**Ce que Strava impose** (son accord et sa politique d'API du 1er juin 2026), et que
Foulée applique :

- **Lecture seule** : Foulée ne demande que les droits `read` et `activity:read_all`.
  Strava lui-même l'empêche alors de publier, modifier ou effacer quoi que ce soit. Les
  seuls envois servent à l'autorisation (obtenir, renouveler et retirer l'accès).
- **Un cache de 48 heures, pas une archive** : Strava interdit de garder ses données
  (7 jours au plus, et une séance effacée sur Strava doit disparaître sous 48 heures).
  Elles vont dans un fichier à part (`strava-cache.db`, dans le dossier du profil), relu
  à chaque synchro ; ce qui n'a pas été relu depuis 48 heures n'est plus montré, puis
  effacé. PC éteint deux jours : tes séances Strava reviennent avec la synchro suivante.
- **Pas pour l'IA** : Strava interdit de confier ses données à une IA. Claude Desktop ne
  voit donc aucune donnée Strava dans Foulée (le connecteur ne lit pas ce fichier, et ne
  lance jamais de synchro Strava). Pour parler de tes séances Strava avec Claude, branche
  le connecteur Strava officiel dans Claude.
- **Un abonnement Strava pour créer l'appli** : depuis juin 2026, l'API de Strava est
  réservée à ses abonnés. Le profil principal crée une appli pour toute l'installation ;
  les autres profils s'y connectent sans abonnement, une fois l'appli passée à
  10 athlètes dans les réglages API de Strava.

**Réglages → Strava** guide pas à pas :

1. **Crée l'appli Strava de Foulée** dans les
   [réglages API de Strava](https://www.strava.com/settings/api) : un nom **sans le mot
   « Strava »** (Strava le refuse), la catégorie *Visualizer*, et dans **Authorization
   Callback Domain** l'adresse de ton Foulée sans le port (`127.0.0.1` sur le PC, le nom
   Tailscale du serveur ; bouton « Copier » dans Foulée). Strava demande ensuite une
   image : prends l'icône de Foulée, jamais le logo de Strava.
2. **Colle le Client ID et le Client Secret** dans Foulée : ils vont dans le coffre,
   comme la clé Garmin, depuis la machine elle-même ou par Tailscale seulement.
3. **Connecter mon compte Strava**, puis **Autoriser** chez Strava : tu reviens dans les
   Réglages et le premier import démarre.

**Doublons** : une séance que Garmin a déjà donnée ne compte qu'une fois. Foulée
reconnaît la copie Strava (Strava indique qu'elle vient de Garmin Connect, ou les deux
se recouvrent au moins de moitié dans le temps) et garde la séance Garmin, plus riche.

**Renfo noté sur Strava** : l'API de Strava ne donne pas les exercices d'une séance de
musculation (elle sait seulement les recevoir). Foulée lit ceux que la description
énumère, comme le font Hevy ou Strong, ou une note à la main (« Squat 4x10 @ 60 kg ») ;
leurs noms restent tels qu'écrits, souvent en anglais, comme on les dit à la salle.

**Sources** : chaque tuile dit d'où viennent ses chiffres, à côté de son titre
(« Garmin · Strava (Wahoo ELEMNT BOLT) », « Withings »), comme Garmin le demande ; une
séance Strava propose le lien **View on Strava**. Quotas : Strava limite les appels
(100 par quart d'heure, 1 000 par jour pour une appli à un athlète) ; Foulée garde de la
marge et complète le détail des séances au fil des synchros.

### Relier ton calendrier d'entraînement (facultatif)

Tes séances prévues (plan Garmin Coach, entraînements programmés) et tes courses, depuis
ton calendrier Garmin Connect, face à ce que tu as réellement fait :

1. Sur [connect.garmin.com](https://connect.garmin.com/modern/calendar), depuis un
   ordinateur : ouvre le **calendrier**, clique sur les **trois points** en haut à droite,
   puis **Publier le calendrier**, et copie le lien proposé. Un agenda Google (« Adresse
   secrète au format iCal ») ou celui du club (lien `.ics` ou `webcal://`) marche aussi.
2. Colle-le dans **Réglages → Calendrier** : Foulée le lit une première fois, puis ajoute
   la vue **Calendrier** juste après l'Accueil.

Ce que tu obtiens :

- **La vue Calendrier** : la prochaine course avec son compte à rebours et les prochaines
  séances, puis le mois jour par jour (séances prévues, courses, séances faites). Un clic
  sur un jour donne le détail : la consigne de la séance, l'heure et le lieu d'une course,
  la séance faite (un clic l'ouvre). Sur téléphone, des pastilles remplacent les titres.
- **Dans « Ta semaine »** (Accueil) : les séances prévues de chaque jour, cochées quand
  elles sont faites, barrées quand elles sont manquées, et le bilan de la semaine
  (« Prévues 4/6 faites »).
- **Fait ou manqué** : une séance du même sport le même jour rend une séance prévue
  « faite » (une course à pied ou un trail pour un footing, du renfo pour le renfo) ; un
  jour passé sans rien de tel la rend « manquée ». Le calendrier publié par Garmin ne
  contient que l'avenir : Foulée garde lui-même ce qu'il a lu, jour après jour.
- **Une pastille « Calendrier »** : verte quand la dernière lecture a réussi (le calendrier
  est relu avec la synchro automatique, toutes les 3 heures par défaut), rouge sinon. Si
  la publication est annulée (le lien ne répond plus), la lecture se met en pause et la
  pastille t'envoie coller le nouveau lien ; les séances déjà lues restent.
- **Claude Desktop** voit tes séances prévues et leur état (outil `calendrier`, et `semaine`).

**Le lien est un secret** : il donne ton calendrier à quiconque le connaît. Foulée le
range dans le coffre, comme la clé Garmin, depuis la machine elle-même ou par Tailscale
seulement ; il ne s'affiche plus qu'abrégé (`connect.garmin.com/…a1b2`), ne figure ni
dans la sauvegarde des réglages, ni dans le journal, ni dans les messages d'erreur, et
n'est jamais transmis à Claude. Pour le rendre inutilisable : annule la publication dans
Garmin Connect (une nouvelle publication donne un nouveau lien).

## 3. Utiliser l'interface

| Vue | Contenu |
|---|---|
| Accueil | Bonjour (photo, poste du jour, objectif), forme du jour face à tes habitudes, ta semaine (avec les séances prévues si ton calendrier est relié), tes allures selon ta VMA (tableau du club, piste, test VAMEVAL), Body Battery de la journée, records |
| Calendrier | Si tu as relié ton calendrier d'entraînement : ta prochaine course (compte à rebours) et tes prochaines séances, puis le mois jour par jour, séances prévues face aux séances faites |
| Aujourd'hui | Nuit, VFC, FC de repos, Body Battery au réveil, stress, km sur 7 jours, fraîcheur, dernière séance |
| Entraînement | Km par semaine, forme et fatigue (charge chronique, aiguë, fraîcheur, ratio), zones FC et d'allure, liste des séances |
| Renfo | Dès ta première séance de renfo détaillée : muscles travaillés (carte du corps face et dos, séries par muscle), régularité face à ton objectif, chaque exercice et sa progression, temps, séries et tonnage par semaine, séances |
| Séance | Résumé, exercices de renfo (avec la carte du corps), carte, courbes synchronisées (FC, allure, altitude, cadence…), autres mesures (dynamique de course, puissance, respiration…), tours ou découpage au km |
| Récup & postes | Comparaison d'un poste de travail à l'autre, sommeil, VFC, FC de repos, nuage sommeil → VFC, calendrier |
| Cap semi de Paris | Compte à rebours, allure cible, fractions rapides face à l'allure cible, volume, charge, zones, VO2max |
| Mon club | Si tu l'as coché dans les Réglages : ton club FFA (coordonnées, site, carte), ta licence, et son classement sur athle.fr en un clic |
| Withings | Si tu as relié ton compte : dernière pesée et composition corporelle, dernière tension (avec les repères de la Société européenne d'hypertension), dernière nuit, activité, puis les courbes de chaque appareil |

**Tout se modifie** : bouton « Modifier la vue », puis glisse les tuiles, change
leur taille, règle-les (roue dentée) ou ajoute-en. Les tuiles sont rangées par
catégories, avec une recherche. Partout où une tuile demande une métrique, tu peux
choisir parmi celles de Foulée **ou n'importe quelle valeur que Garmin renvoie**
(« données brutes » : SpO2, respiration, dynamique de course, minutes d'intensité…).
« Nouvelle vue » dans le menu crée une vue vide. Les vues s'exportent et s'importent
en JSON.

La tuile **Journée en détail** montre heure par heure la FC, la Body Battery, les
phases du sommeil ou la VFC de la nuit. Ces courbes sont demandées à Garmin quand
la tuile les affiche (un appel par jour), puis gardées dans ta base.

**Rythme de la synchro automatique** (Réglages → Synchro et calculs) : un délai par
source, Garmin et Withings, de 30 minutes à 12 heures (3 heures par défaut). 3 heures est
un bon compromis : séances, nuits et pesées arrivent dans la journée sans solliciter
Garmin et Withings pour rien ; plus rapproché, Foulée redemande sans cesse des données qui
n'ont pas bougé. Pour une donnée tout de suite, le bouton **Synchroniser** suffit.

**Pastilles de connexion** : en haut à droite de chaque vue (dans la barre du haut
sur téléphone), une pastille par source branchée sur le profil (Garmin, Withings, Strava,
calendrier) :
verte quand sa dernière synchro a abouti, rouge quand elle n'a pas abouti ou que la
clé (l'accès) manque ou est refusée, grise avant la première synchro. Un clic montre
le message d'erreur, la dernière synchro réussie, « Réessayer » et le lien vers les
Réglages de la source. Claude les voit aussi (outil `statut`).

**Renfo** : pour chaque séance de musculation, Garmin Connect garde le détail
exercice par exercice (séries, répétitions, durée, charge), corrections faites dans
l'appli comprises. Foulée le lit à la synchro (sans fichier FIT), traduit les
exercices en français et en déduit les muscles travaillés : une série compte pour 1
sur un muscle principal, pour ½ sur un muscle secondaire (au plus ½ pour
l'échauffement et les étirements). La vue **Renfo** arrive après « Entraînement »
avec ta première séance de renfo détaillée : carte du corps (face et dos), séries
par muscle et muscles laissés de côté, séances par semaine face à ton objectif
(2 par défaut), chaque exercice avec sa dernière séance et sa progression (charge,
répétitions ou durée par série). Dans la vue **Séance**, la tuile « Exercices de
renfo » s'affiche pour les séances de renfo et s'efface pour les autres. Quatre
métriques rejoignent les tuiles (catégorie « Renfo ») : séries, répétitions, tonnage
et temps d'effort. Sur la montre, lance l'activité « Musculation » et choisis
l'exercice à chaque série (ou suis un entraînement de renfo préparé dans Garmin
Connect) ; une séance enregistrée sans le détail se complète après coup dans l'appli
Garmin Connect. Seules comptent les séances de musculation et de cardio / HIIT : en
yoga, Pilates ou mobilité, la montre « devine » des séries qui n'en sont pas.

Les **Réglages** contiennent :

- **Profil et logo** : ton prénom, ta photo (JPEG, PNG ou WebP, recadrée en carré
  dans le navigateur et réduite à 256 × 256 pixels, sans métadonnées) ou celle de
  Garmin Connect, et le logo de l'application (sept dessins, ou ta photo) ;
- **Mon club** : coche « Je fais partie d'un club » et saisis le numéro de club de
  ta licence (« N° Club », 6 chiffres) ; colle la fiche « Coordonnées et contacts »
  de la page du club sur athle.fr pour que Foulée en tire le président, l'adresse, le
  téléphone, l'e-mail et le site ; ajoute ta licence si tu veux un rappel un mois avant
  sa fin ;
- **Profil de coureur** et **Objectif course** ;
- **Horaires de travail** : bureau, 2x8 matin / soir (selon la parité des
  semaines), 3x8, 5x8 (cycle en jours) ou cycle personnalisé, avec les heures de
  chaque poste et tes congés ;
- **Zones FC** : celles de ta montre (lues chez Garmin), en % de la FC max, en %
  de la FC de réserve, en % de la FC au seuil, ou bornes à la main comme sur Strava ;
  tire les séparations de la barre pour les ajuster ;
- **Zones d'allure** : en % de la VMA, en % de la vitesse au seuil, ou allures à la
  main ;
- la synchro, le fond de carte (OpenStreetMap, Plan IGN ou aucun), puis
  l'installation : clé Garmin, **Withings** (le pas-à-pas pour relier ton compte, puis
  l'état de la connexion), dossier des données, Claude Desktop, démarrage avec Windows
  et mises à jour.

**Aide et retours**, en bas de la colonne de gauche (menu ☰ sur téléphone) :

- **Aide et FAQ** : les questions les plus courantes, rangées par thème (premiers
  pas, profils, clé Garmin, synchro, tableaux de bord, calculs, renfo, mon club, Withings, horaires,
  Claude Desktop, téléphone, installation, vie privée), avec une recherche et des liens directs vers
  la bonne rubrique des réglages ;
- **Un bug, une idée ? Parles-en !** : un formulaire (titre, message, captures
  d'écran glissées, collées ou choisies). Il propose d'abord les réponses de l'aide
  qui ressemblent à ton titre, explique ce qu'on trouve sur la page des sujets GitHub
  du projet, joint si tu le veux quelques informations techniques (version, système,
  navigateur, état de la clé et de la synchro : jamais ta clé, tes mesures ni le
  chemin de ton dossier), puis ouvre GitHub avec le sujet déjà rempli : il reste à
  y coller tes captures et à valider. Rien ne part sans ton clic.

**Plusieurs utilisateurs** : un profil par personne qui a une montre Garmin,
comme les profils d'un service de streaming. Chacun a ses données (avec sa propre
clé API), ses vues, ses réglages, sa photo et sa synchro.

- **Changer de profil** : le prénom, en haut à droite de l'Accueil ; le chevron
  déplie la liste. Le choix est retenu sur chaque appareil ; sur un nouvel appareil,
  Foulée demande d'abord « Qui utilise Foulée ? ».
- **Code facultatif** : 4 chiffres pour protéger un profil (Réglages → Profil et
  logo). Seule son empreinte est gardée ; un code oublié s'efface depuis le profil
  principal.
- **L'utilisateur principal** (celui qui a installé Foulée) gère les profils dans
  **Réglages → Gestion des utilisateurs** (ajouter, renommer, effacer un code,
  supprimer) et règle seul l'installation : mises à jour, dossier des données,
  Claude Desktop, démarrage avec Windows, accès par le réseau local.
- **Claude Desktop** ne lit que les profils qui l'autorisent (case « Claude Desktop
  peut lire mes données », cochée d'office pour le principal seulement).
- La synchro automatique passe sur chaque profil qui a une clé ; `foulee sync`
  aussi (`--profil <prénom>` pour un seul).

Rangement : le profil principal garde sa base à la racine du dossier des données,
comme avant ; les autres ont chacun leur sous-dossier `profils/<id>`, et la liste des
profils est dans `utilisateurs.json`. Déplacer le dossier des données les emmène tous.

**Mon club** : la vue s'ajoute juste après l'Accueil quand tu coches « Je fais
partie d'un club » (Réglages → Mon club), et s'en va quand tu décoches (ce que tu as
saisi est gardé). Elle montre les coordonnées du club, ta licence (avec un rappel sur
l'Accueil à l'approche de sa fin) et des boutons vers le classement du club sur
athle.fr, pour la saison en cours et la précédente. La FFA ne propose pas d'accès pour
les applications et son site n'autorise pas la lecture automatique : Foulée ne lit
donc rien sur athle.fr, il prépare les liens que ton navigateur ouvre. Les saisons
suivent celles de la FFA (du 1er septembre au 31 août). Chaque profil a son club.

**Sauvegarde des réglages** : chaque installation (le PC, le serveur) garde ses
propres réglages. « Exporter mes réglages » les met dans un fichier (avec tes vues et
ta photo) ; « Importer des réglages… » les reprend sur l'autre installation. La clé
Garmin, les mots de passe et le jeton GitHub n'y figurent jamais.

## 4. Utiliser Foulée avec Claude Desktop

1. **Réglages → Claude Desktop → Relier Foulée à Claude Desktop** (ou l'étape 3 de
   l'accueil). Claude Desktop doit être fermé pendant l'opération : si besoin, Foulée
   propose de le fermer pour toi. Une copie de sauvegarde de sa configuration est
   faite à côté.
2. Ouvre Claude Desktop. Au tout premier démarrage, compte une vingtaine de secondes :
   l'antivirus de Windows analyse les fichiers de Foulée une première fois.
3. Dans une conversation, bouton **+** → **Connecteurs** : « foulee » y figure.
4. Pose tes questions, par exemple :
   - « Compare mon sommeil et ma VFC d'un poste à l'autre depuis septembre. »
   - « Quelles allures pour 6 × 800 m à 100 % de VMA ? Et sur piste, au 400 m ? »
   - « Comment est ma forme ce matin ? »
   - « Analyse ma séance de fractionné d'hier : tours, FC, découplage. »
   - « Quels muscles ai-je travaillés en renfo ce mois-ci ? Qu'est-ce que je néglige ? »
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
| Appli et accès Withings (ClientID, Secret, jetons) | Gestionnaire d'identification Windows, à côté de la clé API |
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

Inutile d'y penser : Foulée regarde sur GitHub toutes les 3 heures et, dès qu'une
version plus récente sort sur ton canal, **« Une nouvelle version est disponible ! »**
s'affiche en haut à droite de l'interface. Un clic montre les nouveautés ; **Installer
maintenant** lance la mise à jour après confirmation (depuis le profil principal), ou
**Voir dans les Réglages** mène à cette section.

- **Recevoir les versions bêta** (case à cocher) : les avant-premières arrivent sur
  ton PC avant tout le monde, pour les essayer. Décoche pour revenir au canal stable ;
  Foulée ne redescend jamais de version : tu repasses en stable à la prochaine version
  stable plus récente que ta bêta.
- **Jeton GitHub** : inutile, le dépôt de Foulée est public. Si un jour il redevenait
  privé, GitHub en demanderait un pour montrer ses versions : à créer sur
  https://github.com/settings/personal-access-tokens/new (type « fine-grained »,
  accès au seul dépôt `foulee`, permission **Contents : Read-only**), puis à coller
  dans **Réglages → Mises à jour → Jeton GitHub**. Un jeton déjà enregistré qui
  expire ne bloque pas les mises à jour : Foulée réessaie sans.

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
- c'est tout : le dépôt est public, le serveur récupère le code sans jeton GitHub.

Installation, dans la console du conteneur (en root) :

```
apt update && apt install -y git && git clone https://github.com/willyl02/foulee /opt/foulee && bash /opt/foulee/scripts/installer-serveur.sh
```

1. Git récupère le code (s'il demande un nom d'utilisateur, c'est que l'adresse du
   dépôt est mal tapée).
2. Le script installe Python et les bibliothèques, puis les services : l'interface
   (`foulee-web`) et la synchro automatique (`foulee-sync.timer`, vérifiée toutes les
   15 minutes, chaque source à son rythme).
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

Pour faire passer tout de suite un serveur en 0.3.0 sur la bêta (la case « Recevoir les
versions bêta » n'existe qu'à partir de la 0.4), une seule fois, en root :

```
cd /opt/foulee && git fetch origin beta && git checkout -B beta origin/beta && bash scripts/mettre-a-jour-serveur.sh --canal beta
```

Une bêta installée continue ensuite de suivre les bêtas, jusqu'à ce que tu décoches la case.

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
   tâche planifiée « Foulee - synchro » (elle regarde toutes les 15 minutes si une synchro
   est due, au rythme choisi dans les Réglages).

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

Commence par **Aide et FAQ**, dans la colonne de gauche de l'interface ; pour
signaler un problème, **Un bug, une idée ? Parles-en !** prépare le sujet GitHub
avec les informations utiles.

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
- **Bandeau « Garmin refuse ta clé »** ou **« Garmin ne connaît plus ta clé »** alors
  que tout marchait : elle a expiré, ou été supprimée ou régénérée dans Garmin Connect
  (par exemple en créant une clé pour un autre appareil) ; remplace-la (section 2).
- **Le serveur et le PC n'ont pas les mêmes réglages** : c'est normal, chaque
  installation a sa base. Exporte-les d'un côté et importe-les de l'autre
  (Réglages → Sauvegarde des réglages).
- **La mise à jour indique « ajoute un jeton GitHub »** : le dépôt serait redevenu
  privé (section 6).
- **Le téléphone affiche « Foulée est injoignable »** : l'appli Tailscale est
  déconnectée sur le téléphone, ou le serveur est arrêté (`systemctl status foulee-web`).
- **La mise à jour du serveur ne répond pas** : `systemctl status foulee-maj.path`
  sur le serveur ; le détail de la dernière tentative est dans `/var/lib/foulee/maj/etat.json`.
  Le dépôt étant public, `git pull` (en root, dans `/opt/foulee`) n'a besoin d'aucun jeton.
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
  withings/        connecteur Withings : appli et jetons (OAuth par la page relais), lecture des mesures, synchro, vue
  desktop.py       application Windows : icône près de l'horloge, synchro auto, une seule copie
  web.py           API locale + pages, accès réseau, clé, dossier, Claude, mises à jour
  updates.py       mises à jour (versions GitHub du PC, canaux stable et bêta)
  retours.py       aide et retours : adresses des sujets GitHub, dépôt public ou privé
  utilisateurs.py  profils : liste, profil courant (cookie signé), codes, accès de Claude
  datadir.py       dossier des données : déplacer, utiliser, importer
  claude_desktop.py  configuration de Claude Desktop (toutes ses variantes)
  vault.py         secrets : clé Garmin, accès Withings, jeton GitHub (Gestionnaire d'identification Windows)
  keyinput.py      lecture de la clé (presse-papiers, nettoyage) sans jamais l'afficher
  sync.py          chef d'orchestre des sources : Garmin, Withings (ajouter Strava = une entrée ici)
  db.py            schéma SQLite (et sa mise à niveau), réglages
  metrics.py       catalogue des métriques (libellés, unités, formats) et données brutes de Garmin
  analysis.py      tous les calculs (séries, charge, zones, postes, objectif, allures VMA, forme du jour…)
  renfo.py         renfo : exercices du résumé de Garmin Connect, noms en français, muscles travaillés
  schedule.py      horaires de travail : bureau, 2x8, 3x8, 5x8, cycle personnalisé, congés
  zones.py         méthodes des zones FC et d'allure
  reglages.py      contrôle des réglages, export et import
  profile.py       prénom, logo, photo de profil
  club.py          mon club FFA : numéro, saisons, fiche collée depuis athle.fr, licence, liens
  views.py         types de tuiles et vues par défaut
  access.py        mot de passe du réseau local (empreinte, cookie signé, anti-acharnement)
  mcp_server.py    outils pour Claude Desktop
  uninstall.py     ménage avant désinstallation
  demo.py          données fictives
  static/          interface (HTML/CSS/JS, ECharts et Leaflet embarqués), appli installable (manifest, sw.js)
packaging/         installateur Windows (Inno Setup), construction et essai de bout en bout
docs/              page relais de Withings (publiée par GitHub Pages), présentation illustrée
scripts/           installation et mise à jour : archive Windows (.ps1), serveur Linux (.sh, maj_serveur.py)
tests/             tests, dont un faux serveur Garmin et un faux Withings pour tester toute la chaîne
```

Pour une nouvelle source : un dossier à côté de `garmin/` qui écrit dans les mêmes
tables (`daily`, `activities`, `laps`, `streams`) avec sa propre valeur de `source`,
puis une entrée dans `sync.SOURCES`. Les vues, les calculs et Claude en profitent
sans autre changement.

Tests : `uv run pytest`.
