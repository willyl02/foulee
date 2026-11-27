# Le manuel de Foulée

[**Foulee-manuel.pdf**](Foulee-manuel.pdf) : un seul document pour la présentation, l'installation et
l'utilisation de Foulée et de Foulée Coach (78 pages, A4). La version de Foulée qu'il décrit est sur sa couverture
(aujourd'hui la **0.8.3**). Sur GitHub, le bouton de téléchargement, en haut à droite du fichier, l'enregistre sur
ton appareil.

| Partie | Ce qu'on y trouve |
|---|---|
| 1. Foulée, c'est quoi ? | Ce que fait Foulée, ce qu'il te faut, l'interface |
| 2. Installer Foulée | Télécharger, installer, premier lancement, clé API Garmin, mises à jour |
| 3. Foulée au quotidien | Accueil, Aujourd'hui (et le temps par zone FC), calendrier, entraînement, séance, récup, ta course, Mon club, Withings, Strava |
| 4. Le renfo | Muscles travaillés, équilibre avant / arrière, progression, réglages du renfo |
| 5. L'Atelier | Séances de course et de renfo, bibliothèque, envoi sur la montre, compte « sans coach » |
| 6. Tes vues et tes réglages | Vues et tuiles, réglages par thème, zones FC et leurs couleurs, logothèque, Club en ligne, aide |
| 7. Foulée sur ton téléphone | Tailscale, l'accès depuis le téléphone, le dépannage |
| 8. Foulée Coach : le principe | Le relais du club, ce qui circule, la sécurité |
| 9. Côté élève | Rejoindre son coach, partager, Mon coach, la montre, les notifications, les messages |
| 10. Côté coach | Inviter, Mes élèves, groupes, bibliothèque, fiche, proposer une séance, montre, messages |

L'administration du relais (sur son serveur, en SSH) n'est volontairement pas dans ce manuel.

Il remplace les documents séparés de la 0.8.2 (présentation, présentation de Foulée Coach, guides de l'élève et du
coach, « Foulée sur ton téléphone »), qui restent dans l'historique du dépôt.

## Le mettre à jour

Les sources sont dans [`source/`](source/) : une partie par fichier dans `parts/`, les captures dans `img/`.

```
cd docs/presentation/source
uv run --with segno --with pillow --with playwright python build.py
uv run --with playwright python check.py build/Foulee-manuel.html
```

`build.py` régénère `Foulee-manuel.pdf` (même nom à chaque version : les liens ne changent pas) et un aperçu PNG de
chaque page dans `source/build/pages/`. `check.py` signale une page dont le contenu passe sous le pied de page.

À chaque version : changer `VERSION` et `MOIS` dans `source/kit.py`, mettre à jour les pages concernées, remplacer
les captures. Une capture n'arrive dans `img/` qu'une fois floutée : coordonnées du club, numéro de licence, nom de
famille, sujet ntfy, clés et jetons n'ont rien à faire dans le dépôt public.
