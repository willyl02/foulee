// Page « Aide » : les questions fréquentes, rangées par thème, avec une recherche.
// Chaque réponse est un petit bout de HTML écrit ici (aucune donnée extérieure) ;
// les liens « réglages(…) » mènent droit à la bonne rubrique.
import * as F from "./format.js";
import { icon } from "./icons.js";

const KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken";
const reglages = (section, label) => `<a href="#/reglages?section=${section}">${label}</a>`;
const ext = (url, label) => `<a href="${url}" target="_blank" rel="noopener">${label}${icon("external")}</a>`;

/** Questions fréquentes : { id, titre, icone, questions: [{ id, q, r(boot) }] }. */
export const FAQ = [
  {
    id: "debut", titre: "Pour commencer", icone: "home",
    questions: [
      { id: "quoi", q: "Qu'est-ce que Foulée ?", r: () => `<p>Foulée récupère tes données Garmin (séances, sommeil, VFC, FC de repos, Body Battery…) grâce à ta clé API personnelle, les range dans une base <b>sur ta machine</b> et te les montre dans des tableaux de bord que tu composes. Il les met aussi à disposition de Claude Desktop pour les analyser avec toi.</p>` },
      { id: "abonnement", q: "Faut-il un abonnement ou un compte Foulée ?", r: () => `<p>Non. Il te faut seulement un compte Garmin Connect et ta clé API personnelle, gratuite. Pas de compte Foulée, pas de serveur chez quelqu'un d'autre : tout tourne chez toi.</p>` },
      { id: "montres", q: "Quelles montres fonctionnent ?", r: () => `<p>Toute montre Garmin qui se synchronise avec Garmin Connect. Certaines mesures dépendent du modèle et de ses réglages : VFC la nuit, SpO2 (oxymètre à activer la nuit), dynamique de course (montre ou ceinture compatible), puissance en course. Quand une mesure manque, Foulée laisse simplement la case vide.</p>` },
      { id: "demo", q: "Puis-je essayer Foulée sans ma clé ?", r: () => `<p>Oui : sur la page de bienvenue, « Découvrir avec des données fictives » ouvre une démo complète (un coureur inventé, plus d'un an d'historique). Le bandeau en haut de page permet de la quitter ; tes vraies données ne sont jamais mélangées à la démo.</p>` },
      { id: "par-ou", q: "Par où commencer ?", r: () => `<p>L'<a href="#/vue/accueil">Accueil</a> résume ta journée. Passe ensuite par les ${reglages("coureur", "Réglages")} : ta VMA, ton objectif, tes horaires de travail et tes zones. Puis compose tes vues : « Modifier la vue », puis « Ajouter une tuile ».</p>` },
    ],
  },
  {
    id: "profils", titre: "Plusieurs utilisateurs", icone: "user",
    questions: [
      { id: "ajouter", q: "Comment ajouter un profil pour quelqu'un de ma famille ?", r: () => `<p>L'utilisateur principal (celui qui a installé Foulée) ouvre ${reglages("utilisateurs", "Réglages → Gestion des utilisateurs")} → « Ajouter un utilisateur » : un prénom, et un code s'il le souhaite. Ensuite, on passe sur ce profil (le prénom, en haut à droite de l'Accueil) pour y enregistrer sa clé Garmin et lancer son premier import.</p>` },
      { id: "changer", q: "Comment passer d'un profil à l'autre ?", r: () => `<p>Clique sur le prénom affiché en haut à droite de l'<a href="#/vue/accueil">Accueil</a> : le chevron déplie la liste des profils. Le choix est retenu sur l'appareil ; sur un nouvel appareil, Foulée demande d'abord « Qui utilise Foulée ? ».</p>` },
      { id: "separe", q: "Qu'est-ce qui est propre à chaque profil ?", r: () => `<ul><li>À chacun : ses données Garmin (avec sa propre clé API), ses vues, ses réglages (VMA, zones, horaires, objectif…), son club, son prénom, sa photo et sa synchro.</li><li>Commun : l'installation (mises à jour, dossier des données, Claude Desktop, accès par le réseau local), réglée depuis le profil de l'utilisateur principal.</li></ul>` },
      { id: "code", q: "À quoi sert le code d'un profil ? Et si je l'oublie ?", r: () => `<p>Un code à 4 chiffres protège un profil : il est demandé pour y entrer depuis un autre profil ou un nouvel appareil. Chacun le pose, le change ou le retire dans ${reglages("profil", "Réglages → Profil et logo")}. Oublié ? L'utilisateur principal l'efface dans ${reglages("utilisateurs", "Gestion des utilisateurs")}, sans avoir à le connaître.</p>` },
      { id: "claude", q: "Claude Desktop voit-il les données de tout le monde ?", r: () => `<p>Non : chaque profil décide. La case « Claude Desktop peut lire mes données » (${reglages("profil", "Réglages → Profil et logo")}) est cochée d'office pour l'utilisateur principal, décochée pour les autres. Pour qu'il regarde un autre profil qui l'autorise, dis-le-lui : « Regarde le profil de Léa ».</p>` },
      { id: "synchro", q: "La synchro concerne-t-elle tous les profils ?", r: () => `<p>Oui : chaque profil qui a une clé est synchronisé toutes les 3 heures (sur le PC tant que Foulée tourne, sur un serveur jour et nuit). Le bouton « Synchroniser » de la colonne synchronise le profil affiché ; « Synchroniser maintenant », dans le menu de l'icône près de l'horloge, les synchronise tous.</p>` },
      { id: "supprimer", q: "Comment supprimer un profil ?", r: () => `<p>L'utilisateur principal ouvre ${reglages("utilisateurs", "Gestion des utilisateurs")} et clique sur la corbeille du profil. Ses séances, ses mesures, ses vues, ses réglages et sa clé sont effacés de l'installation ; ses données restent chez Garmin. Le profil principal, lui, ne se supprime pas.</p>` },
    ],
  },
  {
    id: "cle", titre: "Clé API Garmin", icone: "key",
    questions: [
      { id: "trouver", q: "Où trouver ma clé API personnelle ?", r: () => `<p>Dans Garmin Connect, sur le web : page ${ext(KEY_PAGE, "API personnelle")}. Crée une clé, copie-la avec le bouton « Copier », puis colle-la dans ${reglages("cle", "Réglages → Clé API Garmin")}. Foulée la fait vérifier par Garmin avant de l'enregistrer.</p>` },
      { id: "securite", q: "Où ma clé est-elle rangée ? Qui peut la voir ?", r: () => `<p>Sur le PC, dans le Gestionnaire d'identification de Windows ; sur un serveur, dans un fichier que seul Foulée peut lire. Ni l'interface, ni Claude, ni les messages d'erreur ne la montrent jamais.</p>` },
      { id: "refusee", q: "« Garmin refuse ta clé » ou « ne connaît plus ta clé » : que faire ?", r: () => `<p>La clé a expiré, ou elle a été supprimée ou régénérée dans Garmin Connect (par exemple en créant une clé pour un autre appareil). La synchro se met en pause : reprends ta clé actuelle sur la page ${ext(KEY_PAGE, "API personnelle")}, puis remplace-la dans ${reglages("cle", "Réglages → Clé API Garmin")}.</p>` },
      { id: "deux", q: "Puis-je utiliser la même clé sur le PC et sur le serveur ?", r: () => `<p>Oui. Si tu crées une nouvelle clé, mets-la à jour sur les deux installations : l'ancienne peut cesser de fonctionner.</p>` },
      { id: "telephone", q: "Pourquoi ne puis-je pas changer la clé depuis mon téléphone ?", r: () => `<p>Par sécurité, la clé Garmin (comme le mot de passe du réseau local et le jeton GitHub) ne se change que depuis la machine elle-même ou par Tailscale, jamais par le réseau local de la maison.</p>` },
    ],
  },
  {
    id: "synchro", titre: "Synchro et données", icone: "sync",
    questions: [
      { id: "quand", q: "Quand Foulée récupère-t-il mes nouvelles données ?", r: () => `<p>Sur le PC, toutes les 3 heures tant que Foulée tourne (son icône près de l'horloge), et dès que tu cliques sur « Synchroniser » dans la colonne de gauche. Sur un serveur, toutes les 3 heures, jour et nuit.</p>` },
      { id: "pastilles", q: "Que veulent dire les pastilles « Garmin » et « Withings » en haut à droite ?", r: () => `<p>Une pastille par source branchée sur ton profil. <b>Verte</b> : sa dernière synchro a abouti. <b>Rouge</b> : elle n'a pas abouti (Internet coupé, service en panne…), ou la clé ou l'accès manque ou a été refusé. <b>Grise</b> : pas encore de synchro. Un clic montre le détail : le message d'erreur, la dernière synchro réussie, « Réessayer » et le lien vers les Réglages de la source. Sur téléphone, elles sont dans la barre du haut.</p><p>Une synchro qui a récupéré l'essentiel avec une alerte dans le journal (une donnée de la journée indisponible chez Garmin, par exemple) reste verte ; le détail le signale.</p>` },
      { id: "seance-absente", q: "Ma séance de ce matin n'apparaît pas.", r: () => `<p>Foulée lit Garmin Connect : il faut d'abord que ta montre se soit synchronisée avec l'appli Garmin Connect de ton téléphone. Clique ensuite sur « Synchroniser ».</p>` },
      { id: "historique", q: "Jusqu'à quand remonte mon historique ? Puis-je aller plus loin ?", r: () => `<p>Jusqu'à la date choisie au premier import (2 ans conseillé). Pour remonter plus loin, demande à Claude : « Synchronise depuis le 1er janvier 2023 », ou lance la commande <code>foulee sync --depuis 2023-01-01</code>. Les données déjà présentes ne sont pas dupliquées.</p>` },
      { id: "nuit", q: "Pourquoi une nuit de sommeil compte-t-elle pour le lendemain ?", r: () => `<p>Une nuit est rattachée au jour du réveil, comme dans Garmin Connect : la nuit du lundi au mardi compte pour mardi.</p>` },
      { id: "fit", q: "Que sont les fichiers FIT ?", r: () => `<p>Le fichier d'origine de chaque séance, seconde par seconde : FC, allure, GPS, cadence, tours… Foulée télécharge d'office ceux des derniers mois (${reglages("synchro", "Réglages → Synchro et calculs")}) ; les plus anciens arrivent quand tu ouvres la séance.</p>` },
      { id: "manque", q: "Pourquoi certaines valeurs manquent-elles (VFC, SpO2, Body Battery…) ?", r: () => `<p>Elles dépendent de ta montre, de ses réglages (oxymètre la nuit…) et du port de la montre : sans montre la nuit, pas de VFC ni de sommeil. Les jours sans mesure restent vides dans les courbes.</p>` },
      { id: "ecarts", q: "Mes chiffres diffèrent un peu de ceux de Garmin Connect.", r: () => `<p>Foulée reprend les valeurs de Garmin telles quelles ; les écarts viennent des moyennes (Foulée fait la moyenne des jours de la période, Garmin parfois sur 7 jours glissants), des arrondis ou d'une synchro qui date. La charge, la forme et la fraîcheur sont calculées par Foulée (voir « Entraînement et calculs »).</p>` },
      { id: "journee", q: "D'où viennent les courbes de la « Journée en détail » ?", r: () => `<p>FC minute par minute, phases du sommeil et VFC de la nuit sont demandées à Garmin quand la tuile les affiche (un appel par jour), puis gardées dans ta base. Le jour même est redemandé au plus toutes les 15 minutes. La Body Battery de la journée vient de la synchro.</p>` },
      { id: "dossier", q: "Où sont mes données ? Comment les sauvegarder ?", r: (b) => `<p>Dans le dossier ${b.dossier_donnees ? `<code>${F.escape(b.dossier_donnees)}</code>` : "des données"} : la base (SQLite) et les fichiers FIT. Sauvegarder Foulée, c'est copier ce dossier. Tu peux aussi le déplacer, sur un autre disque par exemple : ${reglages("dossier", "Réglages → Dossier des données")}.</p>` },
      { id: "brut", q: "Foulée garde-t-il les réponses de Garmin ?", r: () => `<p>Oui, telles quelles : tout peut être recalculé sans rien redemander à Garmin, et chaque valeur qu'elles contiennent peut servir dans une tuile (les « données brutes »).</p>` },
    ],
  },
  {
    id: "vues", titre: "Tableaux de bord", icone: "chart",
    questions: [
      { id: "modifier", q: "Comment modifier une vue ?", r: () => `<p>« Modifier la vue » en haut à droite : déplace les tuiles (glisser, ou flèches), change leur largeur et leur hauteur, règle-les avec la roue dentée, retire-les ou ajoute-en. Tout s'enregistre au fur et à mesure ; « Terminer » quand c'est fini.</p>` },
      { id: "creer", q: "Comment créer une vue ou changer leur ordre ?", r: () => `<p>« Nouvelle vue » dans la colonne de gauche : un nom, une icône, puis tes tuiles. En mode modification, glisse les vues dans la colonne pour les réordonner.</p>` },
      { id: "donnee-absente", q: "Je cherche une donnée Garmin qui n'est pas dans la liste.", r: () => `<p>Dans le choix d'une métrique, tape quelques mots dans la recherche : en plus des métriques de Foulée, la liste propose toutes les valeurs des réponses de Garmin (« Données brutes »), avec un exemple de valeur pour t'aider à choisir.</p>` },
      { id: "periode", q: "À quoi sert le sélecteur 7 j, 30 j, 90 j… ?", r: () => `<p>Il règle la période des tuiles qui suivent celle de la vue. Une tuile peut avoir sa propre période : roue dentée, puis « Période ».</p>` },
      { id: "restaurer", q: "J'ai trop modifié mes vues : comment revenir en arrière ?", r: () => `<p>${reglages("vues", "Réglages → Vues")} → « Restaurer les vues d'origine » : les six vues fournies avec Foulée reprennent leur contenu de départ ; tes vues personnelles ne bougent pas.</p>` },
      { id: "partager", q: "Comment partager une vue ?", r: () => `<p>En mode modification, « Exporter » crée un fichier ; « Importer une vue » le reprend, ici ou chez quelqu'un d'autre. Pour tout transférer d'un coup (réglages, vues, photo) : ${reglages("sauvegarde", "Réglages → Sauvegarde des réglages")}.</p>` },
      { id: "vide", q: "Une tuile affiche « Pas de données sur cette période ».", r: () => `<p>Élargis la période (sélecteur en haut de la vue), vérifie que ta montre mesure bien cette donnée et que la dernière synchro est récente.</p>` },
      { id: "carte", q: "La carte de ma séance reste grise.", r: () => `<p>Le fond de carte vient d'Internet (OpenStreetMap ou Plan IGN) : sans connexion, seul le tracé s'affiche. Tu peux aussi n'afficher que le tracé, sans rien demander à Internet : ${reglages("synchro", "Réglages → Synchro et calculs")} → Fond de carte → Aucun.</p>` },
      { id: "logo", q: "Comment changer le logo ou mettre ma photo ?", r: () => `<p>${reglages("profil", "Réglages → Profil et logo")} : choisis un des logos, ou importe ta photo (recadrée en carré, réduite, sans métadonnées) ; elle peut aussi venir de Garmin Connect.</p>` },
      { id: "theme", q: "Comment passer en thème sombre ?", r: () => `<p>Le petit bouton à droite de « Réglages », en bas de la colonne de gauche : chaque clic passe d'automatique (comme ton système) à clair, puis à sombre.</p>` },
    ],
  },
  {
    id: "entrainement", titre: "Entraînement et calculs", icone: "run",
    questions: [
      { id: "charge", q: "Comment sont calculées la charge, la forme et la fraîcheur ?", r: () => `<p>Chaque séance a une charge : celle de Garmin, ou un TRIMP calculé sur ta FC (${reglages("synchro", "Réglages → Synchro et calculs")}). La charge chronique est une moyenne pondérée sur environ 42 jours (ta forme de fond), la charge aiguë sur environ 7 jours (ta fatigue récente) ; la fraîcheur, c'est la chronique moins l'aiguë de la veille.</p>` },
      { id: "lire-charge", q: "Fraîcheur négative, ratio aiguë / chronique : comment les lire ?", r: () => `<ul><li>Fraîcheur entre −10 et −30 : tu encaisses une charge productive ; sous −30, la fatigue s'accumule ; au-dessus de +5, tu es frais (idéal avant une course).</li><li>Ratio aiguë / chronique entre 0,8 et 1,3 : progression maîtrisée ; au-delà de 1,5 : hausse brutale de la charge.</li></ul>` },
      { id: "zones-fc", q: "Mes zones FC ne correspondent pas à celles de Garmin ou de Strava.", r: () => `<p>${reglages("zones-fc", "Réglages → Zones de fréquence cardiaque")} : choisis la méthode (zones de ta montre, % FC max, % FC de réserve, % du seuil), ou « Bornes à la main » pour recopier celles de Strava. Les séances sont recalculées aussitôt.</p>` },
      { id: "fc-max", q: "Pourquoi la FC max ou la FC de repos affichées ne sont-elles pas les miennes ?", r: () => `<p>Sans réglage, Foulée prend la FC max de tes zones Garmin (à défaut, la plus haute relevée en séance sur deux ans) et la médiane de ta FC de repos sur 30 jours. Saisis tes valeurs dans ${reglages("coureur", "Réglages → Profil de coureur")} pour les imposer.</p>` },
      { id: "tableau", q: "Comment est construit le tableau d'allures ?", r: () => `<p>Comme le classeur du club : allure = 60 ÷ (VMA × %) minutes par kilomètre, temps de passage = distance ÷ (VMA × %), secondes tronquées. Survole une bande de couleur pour savoir à quoi elle sert (footing, seuil, fractions…).</p>` },
      { id: "vma", q: "Comment estimer ma VMA ?", r: () => `<p>Avec un test VAMEVAL : tuile « Allures selon ta VMA » → onglet « Test VAMEVAL », saisis ton temps puis « Lire le barème » : Foulée donne le palier, la VMA du palier validé et la VMA interpolée, et peut la prendre comme VMA. Tu peux aussi la saisir dans ${reglages("coureur", "Réglages → Profil de coureur")}.</p>` },
      { id: "fractions", q: "Que sont les « fractions rapides » ?", r: () => `<p>Les tours de tes séances de course plus rapides qu'un pourcentage de ta VMA (85 % par défaut, réglable dans ${reglages("zones", "Réglages → Zones d'allure et fractions")}). La tuile compare leur allure moyenne à ton allure cible.</p>` },
      { id: "forme", q: "La « forme du jour » est-elle un avis médical ?", r: () => `<p>Non : elle compare tes mesures du jour (FC de repos, VFC, sommeil, Body Battery, fraîcheur, SpO2) à tes propres habitudes. Au moindre doute sur ta santé, parles-en à un médecin.</p>` },
      { id: "allure-pente", q: "Allure réelle ou ajustée à la pente ?", r: () => `<p>Les allures affichées sont réelles. L'allure ajustée à la pente, calculée par Garmin, existe aussi comme métrique : « Allure ajustée à la pente ».</p>` },
      { id: "records", q: "D'où viennent mes records ?", r: () => `<p>Garmin calcule, pour chaque sortie, ton meilleur temps sur 1 km, 1 mile, 5 km, 10 km, semi… La tuile « Records » compare le meilleur de la période à celui de tout ton historique ; un clic ouvre la séance.</p>` },
    ],
  },
  {
    id: "renfo", titre: "Renfo", icone: "dumbbell",
    questions: [
      { id: "exercices", q: "Comment Foulée connaît-il les exercices de mes séances de renfo ?", r: () => `<p>Pour chaque séance de musculation, Garmin Connect garde un résumé exercice par exercice : séries, répétitions, durée et charge. Foulée le lit à la synchro (pas besoin des fichiers FIT), traduit les exercices en français et en déduit les muscles travaillés. Pour que ce détail existe, lance l'activité « Musculation » sur ta montre et choisis l'exercice à chaque série, ou suis un entraînement de renfo préparé dans Garmin Connect. Seules comptent les séances de musculation et de cardio / HIIT : en yoga, Pilates ou mobilité, la montre « devine » des séries qui n'en sont pas.</p>` },
      { id: "sans-detail", q: "Ma séance de renfo n'a pas de détail d'exercices.", r: () => `<p>La montre n'a enregistré que la durée et la fréquence cardiaque : l'exercice n'a pas été choisi à chaque série, ou la séance a été lancée avec une autre activité que « Musculation ». Tu peux la compléter après coup dans l'appli Garmin Connect (ouvre la séance, puis ses séries) : la synchro suivante reprend le détail.</p>` },
      { id: "corrections", q: "J'ai corrigé une séance dans Garmin Connect : Foulée suit-il ?", r: () => `<p>Oui : c'est la version de Garmin Connect qui fait foi (exercice changé, répétitions ou poids ajustés). Chaque synchro relit les séances des 7 derniers jours. Pour une séance plus ancienne, demande à Claude « Synchronise depuis le 1er octobre », ou lance la commande <code>foulee sync --depuis 2026-10-01</code>.</p>` },
      { id: "muscles", q: "Comment sont comptés les muscles travaillés ?", r: () => `<p>Chaque exercice a ses muscles principaux et secondaires : une série compte pour 1 sur un muscle principal, pour ½ sur un muscle secondaire ; l'échauffement, les étirements et la mobilité comptent au plus pour ½. Sur la carte du corps, la couleur la plus foncée va au muscle le plus travaillé de la période, et les autres se placent par rapport à lui ; un muscle gris n'a pas travaillé. C'est un repère pour équilibrer tes séances, pas une mesure de l'effort de chaque muscle.</p>` },
      { id: "progression", q: "Comment suivre ma progression et ma régularité ?", r: () => `<p>La tuile « Renfo : exercices et progression » liste chaque exercice de la période avec sa dernière séance et une petite courbe : la charge si tu en portes une, sinon les répétitions ou la durée par série. Un clic ouvre la dernière séance avec cet exercice. La tuile « Renfo : muscles travaillés » montre tes séances semaine par semaine face à ton objectif : 2 par semaine au départ, à régler avec la roue dentée de la tuile (0 pour ne pas en avoir).</p>` },
      { id: "noms", q: "Pourquoi un exercice garde-t-il un nom anglais ?", r: () => `<p>Garmin connaît près de 1 850 exercices. Foulée traduit les plus courants ; pour les autres, il affiche la famille de l'exercice en français suivie du nom donné par Garmin, par exemple « Pliométrie (tuck jump) ». Signale-le avec « Un bug, une idée ? » : il sera traduit dans une prochaine version.</p>` },
      { id: "ou", q: "Où trouver mon renfo dans Foulée ?", r: () => `<p>La vue « Renfo » apparaît dans la colonne de gauche, après « Entraînement », dès ta première séance de renfo détaillée (si tu la supprimes, elle ne revient pas : ses tuiles restent dans « Ajouter une tuile »). Dans la vue « Séance », la tuile « Exercices de renfo » s'affiche pour les séances de renfo et s'efface pour les autres. Claude Desktop les voit aussi : « Quels muscles ai-je travaillés ce mois-ci ? ».</p>` },
    ],
  },
  {
    id: "club", titre: "Mon club (FFA)", icone: "club",
    questions: [
      { id: "afficher", q: "Comment afficher mon club dans Foulée ?", r: () => `<p>${reglages("club", "Réglages → Mon club")} : coche « Je fais partie d'un club », saisis le numéro de club de ta licence, puis « Enregistrer mon club ». La vue « Mon club » apparaît dans la colonne de gauche, juste après l'Accueil : les coordonnées du club, ta licence et le classement du club en un clic.</p>` },
      { id: "numero", q: "Où trouver le numéro de mon club ?", r: () => `<p>Sur ta licence FFA (la carte, ou l'attestation de ton espace licencié) : la ligne « N° Club », six chiffres, par exemple <code>012345</code>. Ce n'est pas le nombre qui figure dans l'adresse de la page du club sur athle.fr. Tu peux taper le numéro sans les zéros du début : Foulée les ajoute.</p>` },
      { id: "classement", q: "Pourquoi le classement s'ouvre-t-il sur le site de la FFA ?", r: () => `<p>La FFA ne propose pas d'accès pour les applications, et son site n'autorise pas la lecture automatique : Foulée ne va donc rien chercher sur athle.fr. Il prépare le lien vers le classement officiel de ton club, pour la saison en cours ou la précédente, et ton navigateur l'ouvre : c'est toujours la version à jour, directement chez la FFA.</p>` },
      { id: "coordonnees", q: "Comment remplir les coordonnées du club sans tout taper ?", r: () => `<p>Ouvre la page de ton club sur ${ext("https://www.athle.fr/trouver-un-club/", "athle.fr")}, sélectionne du nom du club jusqu'à la fin du cadre « Coordonnées et contacts », copie, puis colle dans ${reglages("club", "Réglages → Mon club")} : Foulée reconnaît le président, l'adresse, le téléphone, l'e-mail et le site. Vérifie, puis enregistre. Colle aussi l'adresse de la page du club pour un lien direct.</p>` },
      { id: "saison", q: "Comment sont comptées les saisons ?", r: () => `<p>Comme à la FFA : une saison va du 1er septembre au 31 août. La saison 2026-2027 s'appelle « 2027 » sur athle.fr ; Foulée passe à la suivante tout seul le 1er septembre.</p>` },
      { id: "licence", q: "À quoi sert ma licence dans Foulée ?", r: () => `<p>C'est facultatif : son numéro, son type et sa date de fin s'affichent dans « Mon club », et un mois avant la fin, un rappel « Licence à renouveler » apparaît sur l'Accueil. Sans date, Foulée compte jusqu'au 31 août, fin de la saison.</p>` },
      { id: "retirer", q: "Comment retirer la vue « Mon club » ?", r: () => `<p>Décoche « Je fais partie d'un club » dans ${reglages("club", "Réglages → Mon club")} : la vue disparaît, et ce que tu as saisi est gardé si tu la recoches. Chaque profil a son propre club.</p>` },
    ],
  },
  {
    id: "withings", titre: "Withings", icone: "scale",
    questions: [
      { id: "relier", q: "Comment relier mon compte Withings ?", r: () => `<p>${reglages("withings", "Réglages → Withings")} te guide en quatre étapes : créer ton appli sur le tableau de bord développeur de Withings (gratuit, une seule fois), coller son ClientID et son Secret dans Foulée, cliquer sur « Connecter mon compte Withings » puis « Allow this app » chez Withings. La vue « Withings » apparaît ensuite dans la colonne de gauche, juste après l'Accueil.</p>` },
      { id: "appli", q: "Pourquoi faut-il créer une « appli » Withings ?", r: () => `<p>Withings ne donne pas une simple clé comme Garmin : il ne partage les données qu'avec une appli déclarée sur son site pour développeurs. En créant la tienne, tu gardes la main : ton Secret reste sur ta machine, rien ne passe par un service de Foulée, et tu peux retirer l'accès à tout moment dans ton compte Withings. C'est gratuit, et pas besoin d'être développeur.</p>` },
      { id: "relais", q: "À quoi sert la page « willyl02.github.io/foulee/withings » ?", r: () => `<p>Après « Autoriser », Withings renvoie ton navigateur vers une adresse fixée à l'avance, et il refuse celle de ton PC ou de ton serveur. Cette petite page relais de Foulée, sur GitHub, reçoit ton navigateur et le renvoie aussitôt vers ton Foulée, avec un code valable 30 secondes. Elle ne garde rien, ne contacte aucun service et ne renvoie que vers un Foulée de la maison. Le code ne sert à rien sans ton Secret, qui ne quitte pas ta machine.</p>` },
      { id: "donnees", q: "Quelles mesures Withings arrivent dans Foulée ?", r: () => `<p>Balance : poids, masse grasse, musculaire, osseuse et hydrique, graisse viscérale, IMC, vitesse de l'onde de pouls selon le modèle. Tensiomètre : tension et pouls (moyenne de la journée). Sleep Analyzer ou montre : durée et phases du sommeil, score, réveils, FC et respiration de la nuit. Montre ou téléphone : pas et activité. Toutes rejoignent la catégorie « Withings » du choix des métriques : tu peux les mettre dans n'importe quelle tuile, et Claude Desktop les voit. Les mesures médicales (ECG, fibrillation, âge vasculaire…) sont réservées par Withings à ses offres payantes.</p>` },
      { id: "withings-plus", q: "Faut-il un abonnement Withings+ ?", r: () => `<p>Seulement pour un compte Withings créé après le 12 octobre 2026 : Withings demande alors Withings+ pour partager les données avec une appli comme Foulée. Les comptes plus anciens ne sont pas concernés.</p>` },
      { id: "probleme", q: "Withings affiche une erreur, ou je reste bloqué au retour", r: () => `<p>« redirect_uri_mismatch » : l'adresse enregistrée dans ton appli Withings (Registered URLs) doit être exactement celle donnée dans ${reglages("withings", "Réglages → Withings")}, barre finale comprise. « Withings refuse de terminer la connexion » : recopie le ClientID et le Secret, ou relance simplement la connexion (l'autorisation ne vaut que 30 secondes). Bloqué sur « Retour vers Foulée… » : clique sur son bouton « Revenir à Foulée ».</p>` },
      { id: "deconnecter", q: "Comment déconnecter Withings ?", r: () => `<p>${reglages("withings", "Réglages → Withings")} → « Déconnecter Withings » : la synchro Withings s'arrête et la vue s'en va ; les mesures déjà importées restent dans Foulée. Tu peux aussi retirer l'accès de ton appli dans ton compte Withings. Chaque profil relie son propre compte.</p>` },
    ],
  },
  {
    id: "horaires", titre: "Horaires de travail", icone: "briefcase",
    questions: [
      { id: "pourquoi", q: "À quoi servent les horaires de travail ?", r: () => `<p>À comparer ta récupération d'un poste à l'autre (tuile « Comparaison par poste »), à colorer le fond des courbes selon le poste et à afficher ton poste du jour sur l'accueil.</p>` },
      { id: "pas-poste", q: "Je ne travaille pas en postes.", r: () => `<p>Choisis « Bureau » (mêmes horaires du lundi au vendredi), ou décoche « Tenir compte de mes horaires de travail » dans ${reglages("horaires", "Réglages → Horaires de travail")}.</p>` },
      { id: "cycle", q: "Comment saisir un 3x8, un 5x8 ou un cycle particulier ?", r: () => `<p>${reglages("horaires", "Réglages → Horaires de travail")} : choisis le modèle, ajuste les heures de chaque poste, puis la grille du cycle (une ligne par semaine, ou une suite de jours pour un cycle continu). Indique où tu en es aujourd'hui dans le cycle : l'aperçu montre les quatre semaines à venir.</p>` },
      { id: "conges", q: "Comment mettre de côté mes congés ?", r: () => `<p>Dans la rubrique Horaires de travail → Congés, ajoute chaque période (du… au…). Ces jours sont exclus des comparaisons entre postes.</p>` },
      { id: "repos", q: "Les jours de repos comptent-ils dans les comparaisons ?", r: () => `<p>Non par défaut : seuls les jours travaillés comptent. Décoche « Ne comparer que les jours travaillés » pour les rattacher au poste de leur semaine (dans un cycle en jours, ils forment un groupe à part).</p>` },
    ],
  },
  {
    id: "claude", titre: "Claude Desktop", icone: "chat",
    questions: [
      { id: "relier", q: "Comment relier Foulée à Claude Desktop ?", r: (b) => (b.machine === "pc" ? `<p>${reglages("claude", "Réglages → Claude Desktop")} → « Relier Foulée à Claude Desktop ». Claude doit être fermé : Foulée propose de le fermer pour toi. Rouvre-le ; dans une conversation, bouton + → Connecteurs : « foulee » y figure.</p>` : `<p>Depuis le PC où Claude Desktop est installé, avec Foulée installé sur ce PC : Réglages → Claude Desktop → « Relier Foulée à Claude Desktop ».</p>`) },
      { id: "quoi-faire", q: "Que peut faire Claude avec mes données ?", r: () => `<p>Analyser une séance, comparer des périodes ou tes postes, suivre ta charge, te donner tes allures, créer une vue, changer tes réglages… Par exemple : « Comment est ma forme ce matin ? », « Quelles allures pour 6 × 800 m à 100 % de VMA ? », « Compare mon sommeil d'un poste à l'autre depuis septembre ».</p>` },
      { id: "voit-cle", q: "Claude voit-il ma clé Garmin ?", r: () => `<p>Non. Claude interroge ta base par les outils de Foulée ; seuls leurs résultats passent dans la conversation.</p>` },
      { id: "introuvable", q: "Claude ne trouve pas Foulée.", r: () => `<p>Vérifie ${reglages("claude", "Réglages → Claude Desktop")} (relié, et à quelle installation), puis relance Claude Desktop. Au tout premier démarrage, compte une vingtaine de secondes : l'antivirus analyse les fichiers de Foulée. Claude n'a pas besoin que l'application Foulée soit ouverte.</p>` },
    ],
  },
  {
    id: "mobile", titre: "Téléphone et serveur", icone: "laptop",
    questions: [
      { id: "telephone", q: "Puis-je utiliser Foulée sur mon téléphone ?", r: () => `<p>Oui, en installant Foulée sur un serveur à la maison (mini-PC, machine virtuelle…) : tu l'ouvres ensuite de partout par Tailscale, ou depuis la maison par le réseau local avec un mot de passe. Le guide est dans le ${ext("https://github.com/willyl02/foulee#readme", "mode d'emploi du projet")}.</p>` },
      { id: "appli", q: "Comment l'installer comme une appli sur le téléphone ?", r: () => `<p>Ouvre Foulée dans le navigateur du téléphone (adresse Tailscale en https), puis : sur iPhone, Partager → « Sur l'écran d'accueil » ; sur Android, menu ⋮ → « Installer l'application ».</p>` },
      { id: "reglages-differents", q: "Pourquoi le PC et le serveur n'ont-ils pas les mêmes réglages ?", r: () => `<p>Chaque installation a sa propre base : ses réglages, ses vues, sa photo. Pour les aligner : ${reglages("sauvegarde", "Réglages → Sauvegarde des réglages")}, « Exporter » d'un côté, « Importer » de l'autre. Certaines rubriques n'existent que sur le PC (Claude Desktop, application) ou que sur le serveur (accès par le réseau local).</p>` },
      { id: "injoignable", q: "Le téléphone affiche « Foulée est injoignable ».", r: () => `<p>L'appli Tailscale est déconnectée sur le téléphone, ou le serveur est arrêté. Reconnecte Tailscale, puis « Réessayer ».</p>` },
    ],
  },
  {
    id: "installation", titre: "Installation et mises à jour", icone: "download",
    questions: [
      { id: "maj", q: "Comment mettre Foulée à jour ?", r: () => `<p>${reglages("maj", "Réglages → Mises à jour")} → « Vérifier les mises à jour », puis « Mettre à jour maintenant ». Foulée télécharge l'installateur, vérifie son empreinte, s'installe et se relance (une minute environ). Tes données, ta clé et tes vues ne bougent pas.</p>` },
      { id: "alerte-maj", q: "Comment savoir qu'une nouvelle version est sortie ?", r: () => `<p>Foulée regarde sur GitHub toutes les 3 heures, comme pour la synchro. Quand une version plus récente existe sur ton canal (stable ou bêta), « Une nouvelle version est disponible ! » s'affiche en haut à droite. Clique dessus : les nouveautés s'affichent, et « Installer maintenant » lance la mise à jour après ta confirmation. Rien ne s'installe sans ton accord.</p>` },
      { id: "beta", q: "Stable ou bêta : que choisir ?", r: () => `<p>Le canal stable reçoit les versions éprouvées. Les bêtas (case « Recevoir les versions bêta ») arrivent avant, pour essayer les nouveautés : elles peuvent contenir des défauts, signale-les ! Décocher ramène au stable à la prochaine version stable (Foulée ne redescend jamais de version).</p>` },
      { id: "windows-protege", q: "« Windows a protégé votre ordinateur » à l'installation.", r: () => `<p>L'installateur n'est pas signé par un éditeur payant. Clique sur « Informations complémentaires », puis « Exécuter quand même ». Son empreinte SHA-256 est publiée avec chaque version pour qui veut vérifier le fichier.</p>` },
      { id: "demarrage", q: "Foulée se lance-t-il au démarrage de Windows ?", r: () => `<p>Si tu l'as choisi : ${reglages("app", "Réglages → Application")} → « Lancer Foulée à l'ouverture de session Windows ». C'est ce qui permet la synchro automatique.</p>` },
      { id: "quitter", q: "Comment quitter Foulée ?", r: () => `<p>Clic droit sur son icône près de l'horloge (dans la flèche « ^ » si Windows la range) → « Quitter Foulée ». Fermer l'onglet du navigateur ne l'arrête pas : il continue de synchroniser.</p>` },
      { id: "rien", q: "Rien ne se passe quand je lance Foulée.", r: () => `<p>Il tourne sans doute déjà : cherche son icône près de l'horloge (dans la flèche « ^ »), puis clique dessus pour ouvrir l'interface. Si rien n'y fait, le journal de l'application (<code>app.log</code>, dans le sous-dossier <code>logs</code> du dossier des données) aide à comprendre : signale-le avec <a href="#/retours?type=bug">un bug ? Parles-en !</a></p>` },
      { id: "adresse", q: "L'adresse 127.0.0.1:8770 ne répond pas.", r: () => `<p>Foulée n'est peut-être pas lancé : menu Démarrer → Foulée. Si le port 8770 est pris par un autre programme, Foulée en prend un autre et ouvre la bonne adresse tout seul.</p>` },
      { id: "desinstaller", q: "Comment désinstaller Foulée ?", r: () => `<p>Paramètres de Windows → Applications → Foulée → Désinstaller. Foulée te demande s'il faut aussi effacer tes données : réponds « Non » pour les garder, par exemple pour réinstaller plus tard.</p>` },
    ],
  },
  {
    id: "vie-privee", titre: "Vie privée et sécurité", icone: "eye",
    questions: [
      { id: "internet", q: "Mes données partent-elles sur Internet ?", r: () => `<p>Elles restent sur ta machine. Foulée ne contacte que Garmin (pour les récupérer), GitHub (pour les mises à jour) et le fond de carte choisi (OpenStreetMap ou IGN, à couper dans ${reglages("synchro", "Réglages → Synchro et calculs")}). Un signalement de bug ne part que si tu cliques pour l'envoyer.</p>` },
      { id: "acces", q: "Qui peut ouvrir mon Foulée ?", r: () => `<p>Sur le PC, seulement ceux qui utilisent ce PC : l'interface n'écoute que la machine elle-même. Sur un serveur, tes appareils reliés par Tailscale, et ceux de la maison s'ils connaissent le mot de passe du réseau local. Avec plusieurs profils, un code à 4 chiffres protège celui qui le souhaite.</p>` },
      { id: "export", q: "Que contient un export de réglages ?", r: () => `<p>Tes réglages (VMA, FC, objectif, horaires, zones…), tes vues et ta photo si tu la joins. Jamais ta clé Garmin, ni ton mot de passe, ni ton jeton GitHub.</p>` },
      { id: "signalement", q: "Que contient un signalement de bug ?", r: () => `<p>Ce que tu écris, tes captures, et si tu le laisses coché, quelques informations techniques (version de Foulée, système, navigateur, page affichée). Tu vois le texte exact avant de l'envoyer.</p>` },
    ],
  },
  {
    id: "retours", titre: "Aide, bugs et idées", icone: "help",
    questions: [
      { id: "signaler", q: "Comment signaler un bug ou proposer une idée ?", r: () => `<p>Le bouton <a href="#/retours">« Un bug, une idée ? Parles-en ! »</a>, en bas de la colonne de gauche (menu ☰ sur téléphone), ouvre un formulaire : un titre, ton message, tes captures d'écran. Foulée met le tout en forme, puis ouvre GitHub pour l'envoyer.</p>` },
      { id: "github", q: "GitHub et ses « issues », c'est quoi ?", r: (b) => `<p>GitHub est le site où vit le code de Foulée. Son onglet ${ext(`https://github.com/${b.retours?.depot || "willyl02/foulee"}/issues`, "Issues")} (« sujets ») rassemble les bugs signalés et les idées proposées, chacun avec sa discussion. Avant d'écrire, cherche si ton sujet y est déjà : un 👍 ou un commentaire sur un sujet existant aide plus qu'un doublon.</p>` },
      { id: "compte", q: "Faut-il un compte GitHub ?", r: (b) => `<p>Pour écrire un sujet, oui : il est gratuit (github.com → « Sign up »). Pour les lire, non.${b.retours?.email ? " Sans compte, tu peux aussi envoyer ton message par e-mail depuis le formulaire." : ""}</p>` },
    ],
  },
];

const fold = (text) => String(text || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const plain = (html) => html.replace(/<[^>]+>/g, " ").replace(/&[a-z]+;/g, " ");
// Mots trop courants pour départager deux questions
const STOP = new Set(("avec dans pour plus moins sans sous elle elles nous vous leur leurs mais donc comme comment pourquoi "
  + "quand quel quelle quels quelles quoi faut fait faire peut peux veux suis sont etre avoir cette celle celui ceux tout "
  + "tous toute toutes alors aussi encore deja bien tres trop foulee marche marcher fonctionne probleme souci rien jamais "
  + "toujours plus").split(" "));
// Recherche tolérante : sans accents, et sur le début des mots longs (« refusée » trouve « refuse »,
// « synchronisation » trouve « synchro », « zones » trouve « zone »)
const stem = (w) => (w.length > 6 ? w.slice(0, 6) : w.length > 4 ? w.replace(/(e?s|x|e)$/, "") : w);
const terms = (text) => fold(text).split(/[^a-z0-9]+/).filter((w) => w.length >= 2).map(stem);
const words = (text) => fold(text).split(/[^a-z0-9]+/).filter((w) => w.length >= 3 && !STOP.has(w)).map(stem);

/** Toutes les questions à plat : { cat, item, id, html, texte }. */
function entries(boot) {
  return FAQ.flatMap((cat) => cat.questions.map((item) => {
    const html = item.r(boot);
    return { cat, item, id: `${cat.id}-${item.id}`, html, question: fold(item.q), texte: fold(`${item.q} ${plain(html)} ${cat.titre}`) };
  }));
}

/** Questions de l'aide proches d'un texte (titre d'un signalement) : les plus pertinentes d'abord. */
export function suggest(text, boot, limit = 3) {
  const wanted = [...new Set(words(text))];
  if (!wanted.length) return [];
  return entries(boot).map((e) => {
    let score = 0;
    wanted.forEach((w) => { if (e.question.includes(w)) score += 2; else if (e.texte.includes(w)) score += 1; });
    return { ...e, score };
  }).filter((e) => e.score >= (wanted.length > 2 ? 2 : 1))
    .sort((a, b) => b.score - a.score).slice(0, limit);
}

/** Page d'aide : thèmes, questions dépliables, recherche ; #/aide?q=…, ?theme=…, ?question=… */
export function renderHelp(page, boot, { query = "", theme = "", question = "" } = {}) {
  const all = entries(boot);
  page.innerHTML = `
    <header class="head"><div><h1>Aide et questions fréquentes</h1>
      <div class="head-sub">${all.length} questions rangées par thème : clique sur une question pour lire la réponse, ou cherche un mot.</div></div></header>
    <div class="faq">
      <div class="faq-tools">
        <label class="search-field">${icon("search")}<input type="search" data-search placeholder="Chercher : clé, synchro, zones, VMA, téléphone…" aria-label="Chercher dans l'aide" value="${F.escape(query)}"></label>
        <button class="btn btn-ghost" type="button" data-all aria-pressed="false">${icon("list")}<span>Tout déplier</span></button>
      </div>
      <nav class="faq-cats" aria-label="Thèmes">${FAQ.map((c) => `<a href="#/aide?theme=${c.id}" data-cat="${c.id}">${icon(c.icone)}<span>${F.escape(c.titre)}</span></a>`).join("")}</nav>
      <p class="faq-count" data-count aria-live="polite"></p>
      ${FAQ.map((c) => `<section class="faq-cat" id="faq-${c.id}" data-cat-section="${c.id}">
        <h2>${icon(c.icone)}${F.escape(c.titre)}</h2>
        ${all.filter((e) => e.cat === c).map((e) => `<details class="faq-item" id="faq-${e.id}" data-text="${F.escape(e.texte)}">
            <summary><span>${F.escape(e.item.q)}</span>${icon("chevron")}</summary><div class="faq-answer">${e.html}</div></details>`).join("")}
      </section>`).join("")}
      <p class="faq-empty" data-empty hidden>Aucune question ne correspond à ta recherche. Pose-la : <a href="#/retours?type=question">une question ? Parles-en !</a></p>
      <div class="callout faq-foot"><b>Pas trouvé ta réponse ?</b>
        <p>Raconte ce qui coince ou ce qui te manque : <a href="#/retours">un bug, une idée ? Parles-en !</a></p></div>
    </div>`;

  const search = page.querySelector("[data-search]");
  const toggle = page.querySelector("[data-all]");
  const count = page.querySelector("[data-count]");
  const items = [...page.querySelectorAll(".faq-item")];
  const setToggle = (open) => {
    toggle.setAttribute("aria-pressed", String(open));
    toggle.querySelector("span").textContent = open ? "Tout replier" : "Tout déplier";
  };
  const filter = () => {
    const wanted = terms(search.value);
    let shown = 0;
    page.querySelectorAll("[data-cat-section]").forEach((section) => {
      let inSection = 0;
      section.querySelectorAll(".faq-item").forEach((item) => {
        const ok = wanted.every((w) => item.dataset.text.includes(w));
        item.hidden = !ok;
        item.open = ok && wanted.length > 0;
        if (ok) inSection += 1;
      });
      section.hidden = !inSection;
      shown += inSection;
    });
    page.querySelector("[data-empty]").hidden = shown > 0;
    page.querySelector(".faq-cats").hidden = wanted.length > 0;
    count.textContent = wanted.length ? (shown ? `${shown} question${shown > 1 ? "s" : ""} trouvée${shown > 1 ? "s" : ""}` : "") : "";
    setToggle(wanted.length > 0 && shown > 0);
  };
  search.addEventListener("input", filter);
  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-pressed") !== "true";
    items.filter((item) => !item.hidden).forEach((item) => { item.open = open; });
    setToggle(open);
  });
  page.querySelector(".faq-cats").addEventListener("click", (e) => {
    const link = e.target.closest("[data-cat]");
    if (!link) return;
    e.preventDefault();
    page.querySelector(`#faq-${link.dataset.cat}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  if (query) filter();
  const target = question ? page.querySelector(`#faq-${CSS.escape(question)}`) : theme ? page.querySelector(`#faq-${CSS.escape(theme)}`) : null;
  if (target) {
    if (target.tagName === "DETAILS") target.open = true;
    requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
  }
}
