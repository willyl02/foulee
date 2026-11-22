# Historique des versions

Les versions « bêta » (par exemple 0.4.0b1) sont des avant-premières : elles arrivent d'abord
sur le canal bêta (Réglages → Application → Mises à jour → « Recevoir les versions bêta »), puis sortent en
version stable une fois éprouvées.

## 0.8.3b11 — 22 novembre 2026 (bêta)

- **Séances faites, dessin plus juste** : un effort sans allure visée dans la séance (« Allure rapide » d'un plan,
  comme les 7 × 30 s d'*Avis de tempête*) prend l'allure réellement courue sur les intervalles de l'activité, au
  lieu d'être dessiné au niveau d'un footing. Les séances faites déjà lues sont relues une fois.

## 0.8.3b10 — 22 novembre 2026 (bêta)

- **Les zones cardio de l'élève chez son coach.** Une nouvelle case dans « Ce que je partage » : *Tes zones cardio
  (réglages Garmin)*, non cochée par défaut. Cochée, la fiche de l'élève chez le coach montre ses réglages de
  Garmin Connect, profil par profil (course à pied, général…) : la méthode (seuil lactique, FC max ou FC de
  réserve), FC max, FC au repos (et si la montre la met à jour toute seule), FC au seuil, et les bornes des 5
  zones avec leur pourcentage. Avec ce qui saute aux yeux : pas de zones propres à la course, les mêmes partout, un
  écart de FC max avec Foulée. Décochée, le relais les efface aussitôt. Le relais doit être à jour.

## 0.8.3b9 — 22 novembre 2026 (bêta)

- **Les séances faites dessinées telles qu'elles ont été suivies.** Garmin ne donne pas le contenu des séances à
  venir à une clé API personnelle (chemins des séances : 404). Mais une séance structurée faite avec la montre
  laisse sa trace dans l'activité : Foulée lit ses étapes dans le fichier FIT (durées, allures ou zones visées,
  répétitions), ou à défaut le résumé des intervalles de l'activité (échauffement, 7 × 30 s, 7 × 3 min de récup,
  retour au calme), et dessine la séance faite ainsi dans le calendrier, sur Aujourd'hui et dans les pages coach
  et élève. Les séances à venir gardent leur profil deviné du nom ; celles du coach, créées dans Foulée, restent
  dessinées exactement.

## 0.8.3b8 — 22 novembre 2026 (bêta)

- **Séances prévues de Garmin, deuxième essai.** Chez William, Garmin a répondu « introuvable » au chemin des
  séances : le numéro du calendrier est sans doute celui de la séance *planifiée* (il change quand on la déplace).
  Foulée essaie donc la planification, puis la séance, retient le chemin qui répond, et pour les séances déjà faites
  passe par l'activité qui les a suivies (Garmin y rattache la séance). Le journal note le statut de chaque chemin.

## 0.8.3b7 — 22 novembre 2026 (bêta)

- **Les séances prévues du calendrier Garmin dessinées telles qu'elles sont.** Le calendrier de Garmin ne donne que
  leur nom ; Foulée demande maintenant leur contenu à Garmin pendant la synchro (échauffement, répétitions et
  récupérations, retour au calme, allures ou zones visées) et les dessine fidèlement, dans la vue Calendrier, sur
  « Aujourd'hui », dans les pages coach et élève (ton coach voit donc la vraie séance), au lieu d'un profil deviné du
  nom. Exemple : « Endurance de Force : Avis de tempête », 20 min d'échauffement, 7 × 30 s rapides et 3 min de
  récup. Leur vrai sport aussi : une séance de renfo n'est plus prise pour une course. Si la clé API de Garmin ne
  donne pas accès aux séances, Foulée le note dans son journal et garde le profil deviné (nouvel essai une semaine
  plus tard).
- Tests : la date d'une séance envoyée sur la montre se compare à la date du club (un test échouait entre minuit
  et 1 h, heure de Paris).

## 0.8.3b6 — 21 novembre 2026 (bêta)

- **La vue « Calendrier »** (colonne de gauche) prend le même sélecteur que le calendrier des pages coach et élève :
  **Semaine / Mois / Année** (retenu dans ce navigateur), avec les flèches pour passer d'une période à l'autre et
  « Aujourd'hui » pour revenir. Le détail du jour choisi reste à droite. À la semaine, de grandes cases (un jour par
  ligne sur téléphone) ; à l'année, douze petits mois avec une pastille par jour où il y a quelque chose : un clic
  sur un jour montre son détail, un clic sur un mois ouvre ce mois. Tout vient de ta machine : rien à mettre à jour
  sur le relais.

## 0.8.3b5 — 21 novembre 2026 (bêta)

- **Le calendrier des pages coach et élève**, plus léger : au choix **à la semaine**, **au mois** ou **à l'année**
  (retenu dans ce navigateur), avec des **flèches** de chaque côté de la période pour avancer ou reculer, et
  « Aujourd'hui » pour revenir. À la semaine, de grandes cases (un jour par ligne sur téléphone) ; au mois, le mois
  seul ; à l'année, douze petits mois avec une **pastille** par jour où il y a quelque chose (séance du coach, plan,
  faite, manquée, course) : un clic sur un jour ouvre sa semaine, sur un mois ouvre ce mois. Les séances faites ne
  sont partagées que sur quatre semaines : avant, seules les séances prévues s'affichent (c'est indiqué).
- **Relais** : le calendrier d'un élève sur n'importe quelle période (une année au plus). Un relais pas encore à
  jour donne toujours les neuf semaines autour d'aujourd'hui ; Foulée le signale au-delà.

## 0.8.3b4 — 21 novembre 2026 (bêta)

- **Se déplacer dans un graphique zoomé** sans dézoomer : une fois zoomé en largeur, **la main** (glisser sur le
  graphique fait défiler la vue, au doigt aussi sur l'analyse) et une **barre de défilement** sous l'analyse fraction
  par fraction (posée sur le bas du tracé dans les tuiles) : fais glisser le curseur, clique dans la barre pour y
  aller, ou au clavier (flèches, Pg préc. / Pg suiv., Début, Fin). Pour choisir une autre plage en restant zoomé :
  la loupe, ou Maj + glisser.

## 0.8.3b3 — 21 novembre 2026 (bêta)

- **Zoom des graphiques** : en haut à droite de l'analyse fraction par fraction (vue détaillée d'une séance) et des
  graphiques des tuiles (courbes d'une séance, forme et fatigue, kilomètres par semaine, zones…), une petite boîte à
  outils qui apparaît au survol : zoomer ou dézoomer **en largeur** (↔) et **en hauteur** (↕), **zoomer sur une zone**
  (loupe, puis trace-la sur le graphique ; sur l'analyse, glisser suffit), et **revenir au zoom initial** (aussi au
  double-clic). Ctrl + molette zoome en largeur, Maj + molette déplace ; une fois zoomé, glisser déplace la vue. En
  largeur, la hauteur s'ajuste à ce qu'on voit. Sur téléphone, touche le graphique pour faire apparaître la boîte.
- **Club en ligne a son logo**, comme les sites externes : un PNG carré à gauche de son nom dans la colonne de gauche
  et en tête de sa page (Réglages → Club et coach → Club en ligne).
- **Ressenti envoyé au coach** : le message « Cannot set properties of null (setting 'innerHTML') » ne s'affiche plus
  après « Envoyer à mon coach » (le ressenti partait bien, c'est le bouton qui se perdait en route). Même correction
  pour le bouton d'essai des notifications (même message après un essai réussi) et trois autres boutons (premier
  lancement, fiche d'un élève, profil) qui, en cas d'échec, montraient ce message au lieu du vrai motif.

## 0.8.3b2 — 21 novembre 2026 (bêta)

- **Withings : la page de retour passe sur le relais Foulée** (`https://relais.foulee-coach.com/withings/`) au lieu
  de GitHub Pages. Foulée n'a plus besoin du site GitHub pour se connecter à Withings. Une appli Withings créée avant
  garde son ancienne adresse et sa connexion continue de marcher ; pour pouvoir la refaire, ajoute la nouvelle
  adresse dans « Registered URLs » (Réglages → Connexions → Withings l'explique, avec le bouton « Copier »).

## 0.8.3b1 — 21 novembre 2026 (bêta)

- **Sites externes** (Réglages → Club et coach → Sites externes), sur le modèle de Club en ligne, qui garde sa place
  à part : d'autres sites (la FFA, ta ligue, un site de course…), jusqu'à huit, chacun avec son entrée dans la colonne
  de gauche sous l'application partenaire, et la même page (précédent, suivant, recharger, ouvrir dans le
  navigateur). Chaque site peut avoir **son logo** à gauche de son nom : un PNG carré (ou presque) de 64 à 512 pixels,
  200 Ko au plus, gardé sur ta machine ; sans logo, le petit globe. Renommer, changer l'adresse, monter, retirer du
  menu ou supprimer, tout s'enregistre tout seul.

## 0.8.2 — 21 novembre 2026

La version stable qui réunit les bêtas 0.8.2 ; le détail de chacune est dans l'historique des versions (CHANGELOG.md sur GitHub).

- **« Ma séance du jour »** remplace « Aujourd'hui » : le verdict du jour (sommeil, FC de repos, body battery), la
  séance prévue avec ses étapes et tes allures, la météo heure par heure et **ton créneau** pour courir (hors de tes
  heures de travail si tu es posté), puis le débrief : la séance faite face à la prévue, ton **ressenti** de 1 à 10,
  à envoyer à ton coach.
- **Notifications** du relais du club, même Foulée fermé : sur le téléphone avec **ntfy** (gratuit, sans compte, un QR
  code) et **par e-mail** (adresse confirmée par un code). Séance reçue, modifiée, annulée, nouveau message ; heures
  calmes ; détail masqué au choix. Sur le relais, `sudo foulee relais email` branche le service d'envoi (Brevo…).
- **Coach** : **groupes de niveau** par VMA (avec la VMA du test au club), « Mes élèves » rangés par groupe et
  « Proposer au groupe », une **bibliothèque de séances**, les **répétitions libres** à la touche Lap, un **grand
  calendrier** de neuf semaines (coach et élève) et l'**analyse fraction par fraction** de chaque séance.
- **Réglages réorganisés** comme sur Windows et Mac (Moi, Entraînement, Connexions, Club et coach, Application), avec
  une recherche ; tout s'enregistre tout seul.
- **Club en ligne dans Foulée** (application partenaire), une colonne de gauche en trois parties dont on glisse les
  vues pour les réordonner, et un bouton pour revenir en haut.
- **Renfo** : tes propres séances, gardées et envoyées sur ta montre.
- **Corrigés** : la séance faite rattachée à la bonne séance prévue, plus de doublon de la séance du coach ni de la
  séance déplacée dans Garmin Connect, l'écran noir avec un bloqueur de pub, et plus d'objectif d'office à
  l'installation.
- **Relais** : message d'accueil à la connexion SSH avec les commandes usuelles, et `sudo foulee relais groupes`.

## 0.8.2b11 — 21 novembre 2026 (bêta)

- **Les notifications par e-mail** (Réglages → Club et coach → Notifications), en plus de ntfy : séance reçue,
  modifiée ou annulée, nouveau message, avec les mêmes cases et les mêmes heures calmes (l'e-mail attend leur fin
  sur le relais). L'adresse se confirme avec un code à six chiffres envoyé à cette adresse (30 minutes, cinq
  essais) : personne ne reçoit les e-mails du club sans les avoir demandés. « Envoyer un e-mail d'essai »,
  « Changer d'adresse », « Retirer ».
- **Relais : `sudo foulee relais email`** branche le service d'envoi (Brevo par défaut, ou tout SMTP) : la clé SMTP
  se tape sans s'afficher et reste dans le dossier des secrets du relais. `email tester ADRESSE` envoie un essai,
  `email retirer` coupe les e-mails. Rappelées dans le message d'accueil SSH.
- Confidentialité : Brevo ajouté aux services, avec l'adresse e-mail confirmée parmi ce que garde le relais.

## 0.8.2b10 — 20 novembre 2026

- **Corrigé : une séance déplacée dans Garmin Connect restait aussi à son ancien jour** (prévue aujourd'hui,
  remise à demain : elle s'affichait les deux jours). Elle ne reste plus qu'à son nouveau jour ; une séance faite
  aujourd'hui garde bien sa place.
- **Relais : message d'accueil à la connexion SSH** de sa machine : version, état du relais et du tunnel, et les
  commandes usuelles (comptes, groupes, coach, mot de passe, Garmin, mise à jour, journaux). Nouvelle commande
  `sudo foulee relais groupes` : chaque coach et ses élèves (montre reliée, notifications).
- Documentation : les guides et présentations portent la version de Foulée dans leur nom.

## 0.8.2b9 — 20 novembre 2026

- **« Aujourd'hui » devient « Ma séance du jour »** (au lieu de répéter la forme du jour de l'Accueil) :
  - le **verdict de la nuit en une phrase** (feu vert, vas-y sans forcer, journée facile), selon ta récupération
    et l'intensité prévue ;
  - la **séance du jour** (ton plan, celle du coach) avec son esquisse et tes allures, et l'envoi sur la montre ;
  - **quand courir** : la météo heure par heure (Open-Meteo, position arrondie à une dizaine de kilomètres) et
    **ton créneau**, hors de ton poste, le moins de pluie, de vent et de nuit possible ;
  - **après la séance** : prévu face au fait, l'analyse fraction par fraction, et ton **ressenti** de 1 à 10 avec
    un mot, à envoyer à ton coach en un clic.
- Une vue « Aujourd'hui » arrangée à ta façon n'est pas remplacée : ajoute-lui la tuile « Ma séance du jour ».

## 0.8.2b8 — 20 novembre 2026

- **Notifications sur le téléphone, avec ntfy** (appli gratuite, Android et iPhone, sans compte) : Réglages →
  Club et coach → Notifications. Élève : prévenu quand le coach envoie une séance, la modifie ou l'annule, et quand
  il écrit ; coach : quand un élève écrit. QR code pour s'abonner, notification d'essai, choix des événements,
  **heures calmes** (22 h – 7 h par défaut : la notification attend leur fin), détail masquable. C'est le relais
  qui envoie : Foulée n'a pas besoin d'être ouvert. Le relais du club doit être en 0.8.2b8.
- L'**e-mail** est préparé (réglages et interface) : il arrivera avec la clé d'un service d'envoi posée sur le relais.
- Page de confidentialité : ntfy ajouté aux prestataires (seulement si on active les notifications).

## 0.8.2b7 — 20 novembre 2026

- **Réglages réorganisés, comme ceux de Windows et du Mac** : cinq thèmes à gauche (Moi, Entraînement, Connexions,
  Club et coach, Application), leurs rubriques à droite, et une **recherche** qui fouille toutes les rubriques
  (« VMA », « Strava », « mise à jour »…). Sur téléphone : la liste des thèmes, puis le thème choisi.
- **Tout s'enregistre tout de suite** : plus de bouton « Enregistrer les réglages » ; « Enregistré » s'affiche en
  haut de la page après chaque changement.

## 0.8.2b6 — 20 novembre 2026

- **Application partenaire** (Réglages → Application partenaire) : le site du club, par défaut **Club en ligne**
  (`https://app.clubenligne.fr/`), s'ouvre dans Foulée, avec précédent, suivant, recharger et « Ouvrir dans le
  navigateur ». Nom et adresse modifiables, jusqu'à une page précise du site ; une coche l'ajoute dans la colonne.
- **Colonne de gauche** : trois parties séparées d'un trait (tes vues, l'application partenaire, le coach), et les
  vues se **réordonnent en les glissant** (ou Alt + ↑ / ↓), sans passer par « Modifier la vue ».
- Corrigé : dans « Mon coach » et sur la fiche d'un élève, le grand calendrier (surtout replié) touchait les cartes
  du dessous.

## 0.8.2b5 — 20 novembre 2026

- **Renfo : mes séances, sur ma montre.** Dans la tuile « Renfo : exercices pour rééquilibrer », « En faire une
  séance pour ma montre » compose une séance avec les exercices conseillés (séries, répétitions ou durée, récup,
  échauffement et étirements) ; « Mes séances de renfo » les garde. « Envoyer sur ma montre » la dépose dans le
  calendrier Garmin Connect (avec un compte élève relié au relais du club), sinon « Fichier .fit ». Sur la montre,
  chaque série dit l'exercice et ses répétitions : Lap quand elle est finie, la récup suit.
- **Grand calendrier (coach et élève)** : plus lisible (couleurs plus franches, esquisses plus nettes, titres sur
  deux lignes au lieu d'être coupés net), et il se **replie** d'un clic sur son titre ; Foulée retient ton choix.
- **Revenir en haut** : un bouton rond en bas à droite dès qu'on a bien descendu dans une page (Réglages…).
- Le relais du club doit être en 0.8.2b5 pour l'envoi des séances de renfo (il se met à jour seul la nuit).

## 0.8.2b4 — 20 novembre 2026

- **Corrigé : Foulée restait sur « Chargement… »** (écran noir) depuis la 0.8.2b1 chez qui a un bloqueur de pub ou
  de pistage (extension, protection contre le suivi d'Edge) : le fichier de l'analyse fraction par fraction
  s'appelait « analyse.js », un nom que ces bloqueurs refusent, et toute l'interface s'arrêtait avec lui. Il est
  renommé, et un test vérifie désormais qu'aucun fichier de l'interface ne porte un nom de ce genre.

## 0.8.2b3 — 20 novembre 2026

- **Groupes de niveau** (coach) : une nouvelle page « Groupes et séances types » pour créer tes groupes (nom, VMA
  mini et maxi, couleur), ou en faire proposer trois d'après les VMA de tes élèves. Chaque élève va dans le groupe
  de sa VMA : celle de ton **test au club** (VAMEVAL, demi-Cooper…) si tu la notes sur cette page, sinon celle qu'il
  partage. Tu peux aussi placer un élève à la main. L'aperçu montre qui va où avant d'enregistrer.
- **« Mes élèves » rangés par groupe** (ou par VMA, ou par nom), avec « Proposer au groupe » ; dans « Proposer une
  séance », un clic sur un groupe coche tous ses élèves ; le groupe de l'élève s'affiche sur sa fiche.
- **Bibliothèque de séances** sur la même page : tes séances types avec leur esquisse et leur durée, à proposer en
  un clic, modifier, renommer, dupliquer ou supprimer ; « Nouvelle séance type » en compose une sans l'envoyer.
- Pour le coach, il faut que le relais du club soit en 0.8.2b3 : il se met à jour seul la nuit (ou tout de suite,
  sur la machine du relais : `sudo bash /opt/foulee/scripts/mettre-a-jour-serveur.sh`).

## 0.8.2b2 — 20 novembre 2026

- **Quelle séance faite pour quelle séance prévue** : quand plusieurs séances sont prévues le même jour (ton plan et
  celle du coach), chaque séance faite va à celle qui lui ressemble le plus : le nom que lui donne la montre (« Mézy-
  Moulins - 21KM-S3-2-Seuil 60 » répond à « 21KM-S3-2-Seuil 60 »), puis sa durée face à celle des blocs prévus. Avant,
  la première prévue du jour prenait la première faite : la séance de Jason passait « faite » alors que tu avais fait
  celle de ton plan. Même règle chez toi (calendrier, « Ta semaine ») et chez le coach (statut de ses séances, fiche,
  calendrier), et « Ce qui était proposé » n'apparaît plus sous une séance qui répondait à ton plan.
- **Plus de doublon** : la séance du coach envoyée sur ta montre revient aussi par ton calendrier Garmin ; elle ne
  s'affiche plus deux fois (« VMA courte » et « VMA courte (coach) »), ni chez toi ni chez le coach.

## 0.8.2b1 — 20 novembre 2026

- **Analyse fraction par fraction**, façon intervals.icu : sur chaque séance (vue « Séance », et dans les pages coach et
  élève), une colonne par tour, aussi large que sa durée, avec son temps, son allure, sa FC moyenne, la zone de cette FC
  et la part du tour passée dans cette zone, au-dessus des courbes d'allure et de FC. Le survol donne l'allure et la FC
  à chaque instant. L'élève partage pour cela, avec ses tours, une courbe allégée (allure et FC, jamais de position).
- **Calendrier** : chaque séance prévue a son esquisse (une barre par étape, aussi large que sa durée, aussi haute que
  son intensité, aux couleurs des allures VMA), lue dans la séance du coach ou dans le texte du calendrier Garmin
  (« 5 × 200 m à 100 % VMA ») ; à défaut, une séance type devinée du nom, en pâle. Le calendrier du mois grandit.
- **Coach et élève** : un grand calendrier de neuf semaines (quatre passées, celle-ci, quatre à venir) sur la fiche de
  l'élève et dans « Mon coach » : séances prévues avec leur esquisse, séances faites (un clic les ouvre), courses visées.
- **Répétitions libres** (demande de Jason) : dans l'éditeur de séance, « libre (Lap) » à la place d'une durée ou d'une
  distance, pour l'effort comme pour la récup ; la montre passe à la suite à la touche Lap (sur piste, de ligne à
  ligne). Sur la montre comme dans le fichier .fit.
- **Corrigé** : une nouvelle installation n'a plus d'objectif d'office (c'était le semi de Paris du développeur) ; un
  profil qu'on regarde sans le synchroniser est quand même mis à niveau (« Cap semi de Paris » restait sur des profils
  créés avant la 0.8.1) ; une séance de renfo prévue dans Garmin (« 5x10 Squat… + 5x10 Hip thrust… ») n'est plus
  rangée en course à pied, et la séance faite s'y rattache ; l'Accueil se remet à jour sans F5 (jour, « Bonjour /
  Bonsoir », « il y a… », nouvelles données après une synchro automatique).

## 0.8.1 — 16 novembre 2026

La version stable qui réunit les bêtas 0.8.1 ; le détail de chacune est dans l'historique des versions (CHANGELOG.md sur GitHub).

- **Les séances du coach sur la montre, sans câble** : « Envoyer sur ma montre » sous chaque séance proposée. La première
  fois, Garmin Connect s'ouvre : on s'y connecte, chez Garmin, et on clique sur « Accepter » (Foulée ne voit jamais le mot
  de passe) ; ensuite, un clic suffit. La séance arrive dans le calendrier Garmin Connect à sa date, avec tes allures ;
  la montre la récupère à sa synchro. Le coach peut aussi l'envoyer lui-même aux élèves reliés. Le fichier .fit reste là.
- **Objectifs** : « Cap semi de Paris » devient la vue « Objectifs » : l'objectif principal et des objectifs secondaires
  (courses de préparation), avec l'équivalence de chaque temps visé sur la distance du principal. Sur l'Accueil, la
  tuile « Objectifs » montre le principal et les secondaires à venir.
- **Renfo** : des exercices pour rééquilibrer l'avant et l'arrière, famille par famille ; le coach voit cet équilibre
  sur « Mes élèves » et sur la fiche de chaque élève, avec un message tout prêt.
- **VO2max** lue dans les fichiers FIT de la montre (la tuile était vide) ; **nouvelles séances plus vite** : Foulée
  guette toutes les 20 minutes et synchronise dès qu'une séance arrive dans Garmin Connect ; **sélecteur de période**
  qui agit sur chaque vue, retenu vue par vue.
- **Un logo fixe** (le F de la balise) partout, la rubrique active marquée d'un trait rouge, et **Foulée dans sa propre
  fenêtre**, sans barre d'adresse.
- **Foulée sur ton téléphone depuis ton PC** avec Tailscale, en un bouton et un QR code.
- **Foulée sur Mac** (bêta) : Apple Silicon et Intel, à glisser dans Applications.

## 0.8.1b7 — 16 novembre 2026 (bêta)

- **Les séances du coach sur la montre, sans câble** : « Envoyer sur ma montre » sous chaque séance proposée
  (page « Mon coach »). La première fois, Garmin Connect s'ouvre : on s'y connecte, chez Garmin (Foulée ne voit
  jamais le mot de passe), et on clique sur « Accepter » ; la séance part aussitôt, les suivantes en un clic.
  Elle arrive dans le calendrier Garmin Connect à sa date, bloc par bloc, avec ses allures (fourchette de ± 3 %
  autour du % de VMA) ou sa zone de FC ; la montre la récupère à sa synchro. « Renvoyer » la remplace.
- **Le coach peut l'envoyer lui-même** sur la montre des élèves reliés (une montre verte à côté de leur nom) :
  case « Envoyer aussi sur leur montre Garmin » en proposant une séance, bouton montre sur la fiche. Une séance
  modifiée est renvoyée toute seule ; supprimée, elle quitte le calendrier Garmin. L'élève choisit si son coach
  peut le faire (carte « Ta montre Garmin », oui par défaut) et peut délier son compte à tout moment.
- Comment : le relais est désormais l'appli « Foulée » du programme développeur de Garmin (Training API,
  OAuth 2.0 avec PKCE). Il ne lit rien de la montre, il y dépose seulement des séances ; les autorisations sont
  gardées chiffrées. À activer une fois sur la machine du relais : `sudo foulee relais garmin`. Le fichier .fit
  (câble USB) reste disponible.

## 0.8.1b6 — 15 novembre 2026 (bêta)

- **Foulée sur Mac** (bêta) : `Foulee-<version>-mac-arm64.dmg` (Apple Silicon) et `-mac-intel.dmg` (Intel),
  à glisser dans Applications. Comme sur le PC : interface, synchro automatique et veille des nouvelles
  séances, Claude Desktop, mises à jour toutes seules (Foulée télécharge le .dmg de ton processeur, vérifie
  son empreinte, remplace l'application et se relance). Icône dans la barre des menus, lancement à
  l'ouverture de session, fenêtre à part avec Chrome ou Edge, clé API dans le Trousseau, données dans
  ~/Library/Application Support/Foulee. L'application n'est pas signée par Apple : au premier lancement,
  Réglages Système → Confidentialité et sécurité → « Ouvrir quand même » (une seule fois).

## 0.8.1b5 — 15 novembre 2026 (bêta)

- **VO2max** : la tuile « VO2max estimée par Garmin » était vide, l'API personnelle de Garmin ne la donnant
  pas. Foulée la lit désormais dans le fichier FIT de chaque séance, où la montre l'écrit ; les anciennes
  séances déjà téléchargées sont relues petit à petit (une soixantaine par synchro).
- **Nouvelles séances plus vite** : entre deux synchros complètes (3 h par défaut), Foulée guette toutes les
  20 minutes (un seul appel à Garmin) et lance la synchro Garmin dès qu'une nouvelle séance est arrivée dans
  Garmin Connect. Sur le PC comme sur un serveur. Les synchros automatiques se faisaient bien : le délai
  venait des 3 heures d'écart, et du moment où la montre envoie la séance à Garmin Connect.
- **Sélecteur de période** : il ne changeait rien sur plusieurs vues (Entraînement, Récup & postes,
  Objectifs, Withings, une partie de Renfo), dont les tuiles avaient chacune leur période fixe. Elles suivent
  désormais la période de la vue, et chaque vue a la sienne à l'ouverture (6 mois pour Entraînement, Récup
  et Objectifs, 90 jours pour Renfo), retenue vue par vue. Le sélecteur n'apparaît que là où il change
  quelque chose, et une tuile à période fixe porte un petit cadenas. Une période changée à la main est gardée.
- **Logo** : l'ancienne balise est remplacée partout par le F : la page « Foulée est injoignable » du
  téléphone (Tailscale coupé), les pages de connexion par le réseau local, la page de bienvenue, et le logo
  par défaut en haut du menu (les logos au choix passent sur fond sombre).

## 0.8.1b4 — 15 novembre 2026 (bêta)

- **Objectifs** : « Cap semi de Paris » devient la vue « Objectifs », le centre de tes objectifs. L'objectif
  principal (compte à rebours, temps visé, allure cible, part de ta VMA) et des **objectifs secondaires**
  (courses de préparation, un 10 km pour se tester, un trail) : ajouter, modifier, supprimer, et l'étoile pour
  en faire l'objectif principal. Sous chaque secondaire, l'équivalence de son temps visé sur la distance du
  principal (Riegel : « ≈ 1:24:57 au semi »). Les courses de ton calendrier qui ne sont pas encore des objectifs
  sont proposées. Une fois passés, les objectifs gardent ton temps, retrouvé dans les séances du jour, face au
  temps visé. Aussi dans Réglages → Objectifs.
- **Accueil** : la tuile « Objectifs » montre le principal, resserré, et dessous les secondaires à venir (la
  liste défile s'il y en a beaucoup), sans changer de taille.
- **Renfo : exercices pour rééquilibrer** (vue Renfo, sous l'équilibre avant / arrière) : combien de séries
  ajouter pour viser 1:1,5, par semaine et par séance, et lesquelles, famille par famille (la paire la plus en
  retard d'abord, le bas du corps en tête), avec le dosage, la consigne et le matériel (sans matériel d'abord).
- **Le coach voit l'équilibre avant / arrière du renfo** de ses élèves : sur « Mes élèves » (« Renfo 1 : 0,8 »,
  et son verdict) et sur la fiche (rapport, jauge, tendance semaine par semaine, paire par paire, ce qu'il peut
  lui dire, et « Lui en parler » avec un message tout prêt à relire). Il voit aussi ses objectifs secondaires,
  et la « Prochaine course » du groupe tient compte de tous les objectifs. Le relais se met à jour seul la nuit.
- Le coach voit enfin la chaîne de chaque exercice (« Avant », « Arrière ») dans le détail d'une séance de renfo.
- Claude Desktop : l'outil « objectif » donne aussi les objectifs secondaires et les passés.

## 0.8.1b3 — 15 novembre 2026 (bêta)

- **Un logo fixe pour Foulée** : un F tracé avec les deux traits de la balise, blanc en haut, rouge au milieu.
  Il est désormais l'icône de l'onglet, du titre de la fenêtre, de la barre des tâches, du programme et de ses
  raccourcis, de l'icône près de l'horloge et de l'appli sur le téléphone, quel que soit le profil. La photo ou
  le logo choisi dans Réglages → Profil et logo reste en haut de la colonne de gauche, à côté de « Foulée ».
- **La rubrique active**, dans la colonne de gauche, est marquée d'un trait rouge à gauche et de son icône en
  rouge, à la place du petit badge balise.

## 0.8.1b2 — 15 novembre 2026 (bêta)

- **Foulée dans sa propre fenêtre** : l'interface s'ouvre désormais dans une fenêtre à part, sans barre
  d'adresse, d'onglets ni de favoris, avec son icône dans la barre des tâches (le mode application de Microsoft
  Edge, Chrome à défaut). Pour retrouver l'onglet du navigateur : Réglages → Application → « Ouvrir Foulée » →
  « Dans mon navigateur ». Vaut pour l'icône près de l'horloge, celle du Bureau et le menu Démarrer.

## 0.8.1b1 — 15 novembre 2026 (bêta)

- **Foulée sur ton téléphone, depuis ton PC** (Réglages → Foulée sur ton téléphone) : avec Tailscale installé
  sur le PC et sur le téléphone (gratuit, même compte), un bouton « Activer l'accès depuis mon téléphone » fait
  ce qu'il fallait taper dans PowerShell : Tailscale relaie Foulée sur une adresse https privée, que Foulée
  accepte. Les étapes se cochent toutes seules (Tailscale installé, connecté, certificats HTTPS activés), et un
  **QR code** ouvre ton Foulée sur le téléphone. Si Tailscale demande les droits d'administrateur, Windows pose
  la question. « Couper l'accès » défait tout. Le PC doit rester allumé, avec Foulée lancé.
- FAQ : Foulée sur le téléphone depuis le PC, les certificats HTTPS de Tailscale, « Foulée est injoignable »
  (PC en veille).

## 0.8.0 — 14 novembre 2026

La version stable qui réunit les bêtas 0.8 ; le détail de chacune est dans l'historique des versions (CHANGELOG.md sur GitHub).

- **Foulée Coach** (Réglages → Coach et élèves) : un coach et ses élèves se relient par le relais du club, un petit serveur
  sur Internet ; chacun garde Foulée et tout son historique chez lui. L'élève rejoint son coach avec un code d'invitation
  et choisit, case par case, ce qu'il partage (ses 4 dernières semaines de séances en résumé, son objectif et sa VMA ; en
  option le tracé GPS, départ et arrivée masqués, son sommeil, sa VFC, son poids ; jamais Strava).
- **Mes élèves**, côté coach : le tableau de bord du groupe, la fiche de chaque élève, chaque séance en détail, et
  **proposer une séance** en blocs (% de VMA ou zone de FC), que chaque élève reçoit avec ses allures, dans « Mon coach »,
  dans sa vue « Calendrier », et en **fichier .fit pour sa montre**. **Messages** : une conversation par élève, le fil du
  groupe, un fil sous chaque séance.
- **La forme du jour en petites courbes** sur l'Accueil : FC de repos face à ta moyenne, VFC dans ta zone habituelle,
  sommeil face à ton besoin, Body Battery, fraîcheur, SpO2.
- **« Fier de ton club ? »** (Réglages → Mon club) : le logo du club, dans « Mon club » et, si ton coach fait partie du
  club, sur sa carte.
- La FAQ précise pourquoi la séance passe par le câble USB : Garmin Connect n'importe pas les fichiers d'entraînement.

## 0.8.0b4 — 14 novembre 2026 (bêta)

- **La séance du coach sur la montre** : chaque séance proposée se télécharge en fichier **.fit** (« Pour ma
  montre », dans « Mon coach » et dans le détail du jour de la vue « Calendrier ») : chaque bloc devient une
  étape, les répétitions une boucle, les % de VMA une fourchette d'allure calculée avec la VMA de l'élève, la
  zone de FC une cible de FC. Montre branchée en USB, il se copie dans `GARMIN\NewFiles`. « Comment ? » rappelle
  la marche à suivre. Le coach télécharge le même fichier, avec les allures de l'élève, depuis sa fiche. (L'API
  officielle de Garmin ne fait que lire : rien n'est envoyé à Garmin Connect.)
- **La vue « Calendrier » arrive avec le relais** : se relier comme élève ou comme coach l'ajoute (comme le
  calendrier Garmin) ; elle repart à la déconnexion seulement si aucun calendrier Garmin n'est relié. Un
  profil déjà relié la reçoit en ouvrant « Mon coach » ou « Mes élèves ».
- **La forme du jour en petites courbes** : sur l'Accueil, la tuile s'élargit et grandit d'une rangée (l'objectif
  cède un cran de largeur) ; chaque signal a sa courbe : la FC de repos sur 30 jours face à ta moyenne, la
  VFC sur 30 nuits dans ta zone habituelle (fond vert), le sommeil face à ton besoin, le score de sommeil et la
  Body Battery face à leurs repères, la fraîcheur avec la zone de charge productive, la SpO2. Le dernier point
  prend la couleur de l'état ; survoler un point donne sa date et sa valeur. Un Accueil que tu as arrangé
  autrement n'est pas touché.
- **« Fier de ton club ? »** (Réglages → Mon club) : importe le logo du club (PNG à fond transparent de
  préférence, 500 × 500 pixels conseillés) ; il s'affiche en tête de « Mon club » et, si tu réponds « Oui » à
  « Ton coach fait-il partie de ton club ? » (Réglages → Coach et élèves), sur la carte de ton coach. La
  transparence est gardée, les marges transparentes retirées ; sur fond sombre, une plaque claire le garde
  lisible. Il voyage avec l'export des réglages.
- Le relais nomme « Échauffement » et « Retour au calme » les blocs laissés sans nom.
- Réglages sur téléphone : le bloc « Profil et logo » ne déborde plus de l'écran.

## 0.8.0b3 — 14 novembre 2026 (bêta)

- Foulée Coach : un fil encore vide (sous une séance, ou la conversation avec un nouvel élève) restait sur
  « Chargement… » ; il affiche maintenant qu'il n'y a pas encore de message, et la zone pour écrire le premier.

## 0.8.0b2 — 14 novembre 2026 (bêta)

**Foulée Coach**, étapes 2 à 5 : le partage, le suivi, les messages et les séances proposées.

- **Le partage, avec l'accord de l'élève** : juste après l'inscription, l'élève choisit case par case ce que
  voit son coach (ses séances des 4 dernières semaines en résumé, son objectif et sa VMA ; en option le tracé
  GPS, départ et arrivée masqués, son sommeil, sa VFC et sa FC au repos, son poids). Jamais Strava. Rien ne
  part avant. L'extrait part après chaque synchro (ou « Envoyer maintenant ») et remplace le précédent ; une
  case décochée efface aussitôt la donnée chez le relais.
- **Mes élèves** : le tableau de bord du groupe (dernière séance, semaine jour par jour, charge 7 jours, VMA,
  objectif et compte à rebours, messages non lus, alerte « N jours sans séance »), la **fiche** de chaque
  élève (sa semaine face à son plan, ses séances, son objectif et son allure, sa forme) et chaque **séance**
  en détail : tours, renfo, tracé simplifié sans fond de carte, ce qui était proposé.
- **Messages** : une conversation entre le coach et chaque élève, le fil du groupe (le coach y épingle ses
  annonces) et un fil sous chaque séance. Foulée relève les nouveautés toutes les minutes : badge dans la
  colonne et petit message à l'écran.
- **Séances proposées** : le coach compose un déroulé en blocs (échauffement, corps de séance, retour au
  calme ; durée ou distance, répétitions, % de VMA ou zone de FC, récupération), part d'un exemple ou de ses
  modèles, et l'envoie à un ou plusieurs élèves ; chacun le reçoit avec ses allures, dans « Mon coach » et en
  pointillé bleu dans sa vue « Calendrier ». Elle se marque « faite » comme les séances du plan Garmin.
- **Essayer avec un élève fictif** : le mode démo peut rejoindre le groupe avec un code d'invitation et
  partager ses séances fictives ; il a sa propre place dans le coffre, sans toucher au compte coach.
- Le relais date ses messages à l'heure de Paris, même sur un serveur réglé en UTC (`FOULEE_RELAIS_TZ` pour
  un autre fuseau).

## 0.8.0b1 — 14 novembre 2026 (bêta)

Première étape de **Foulée Coach** : relier un coach et ses élèves par le relais du club.

- **Le relais** : Foulée en « mode relais » (`foulee relais serveur`), sur une petite machine sur Internet,
  derrière un tunnel Cloudflare en HTTPS. Installation en une commande (`scripts/installer-relais.sh`, Ubuntu ou
  Debian, AMD ou ARM), mise à jour automatique chaque nuit. Il ne garde que les comptes et les invitations.
- **Les comptes** : un administrateur (qui crée les comptes coach sur la machine du relais), des coachs, des
  élèves. Un élève rejoint son coach avec un code d'invitation (une seule fois, 7 jours), et peut quitter le
  groupe à tout moment : son compte est effacé du relais.
- **Dans Foulée** : Réglages → Coach et élèves pour se relier (le jeton de connexion va dans le coffre, comme
  la clé Garmin), puis une page « Mes élèves » (le groupe, les codes d'invitation) ou « Mon coach ».
- Rien des données d'un élève ne part encore : le partage des séances, avec son accord case par case, arrive
  dans la prochaine bêta, puis la messagerie et les séances proposées.

## 0.7.0 — 13 novembre 2026

La version stable qui réunit les bêtas 0.6 et 0.7 ; le détail de chacune est dans l'historique des versions (CHANGELOG.md sur GitHub).

- **Withings** (Réglages → Withings) : ta balance, ton tensiomètre, ton Sleep Analyzer ou ta montre Withings rejoignent Foulée, avec leur vue et 51 métriques dans toutes les tuiles.
- **Strava, en lecture seule** (Réglages → Strava) : les séances d'une autre montre, d'un compteur de vélo ou notées sur Strava rejoignent les tiennes, sans doublon ; une séance Garmin affiche ses kudos et sa description Strava.
- **Calendrier d'entraînement** (Réglages → Calendrier) : le lien de ton calendrier Garmin Connect publié amène tes séances prévues et tes courses, face à ce que tu as fait. Une vue « Calendrier » s'ajoute après l'Accueil, et « Ta semaine » montre les séances prévues et le bilan (« Prévues 2/5 faites »). Le lien reste secret.
- **Renfo** : tes séances de musculation exercice par exercice, en français, les muscles travaillés sur une carte du corps, ta progression, et l'**équilibre avant / arrière** (chaîne antérieure face à la chaîne postérieure, cible du coureur de 1:1 à 1:2) avec le conseil qui va avec.
- **Effet d'entraînement** de chaque séance, en deux jauges aux couleurs de Garmin Connect (aérobie et anaérobie), avec l'avantage principal et sa place parmi tes séances des 4 semaines précédentes.
- **Pastilles de connexion** en haut de chaque vue (Garmin, Withings, Strava, Calendrier) et **rythme de la synchro** réglable source par source (3 heures par défaut).
- Claude Desktop voit ton renfo, son équilibre, l'effet d'entraînement de tes séances et ton calendrier (pas les données Strava). L'aide compte maintenant 115 questions.

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
