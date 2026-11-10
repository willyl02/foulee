# Composants tiers

Foulée s'appuie sur ces briques open source, installées ou embarquées localement
(aucune n'envoie tes données ailleurs).

| Composant | Rôle | Licence |
|---|---|---|
| garmin-connect-personal-api-python (Garmin Ltd.) | Client officiel de l'API personnelle Garmin | Apache 2.0 |
| garmin-fit-sdk (Garmin International) | Décodage des fichiers FIT | FIT Protocol License |
| FastAPI, Uvicorn, Starlette, Pydantic | Serveur web local | MIT / BSD |
| mcp (Model Context Protocol, SDK Python) | Serveur pour Claude Desktop | MIT |
| keyring | Accès au Gestionnaire d'identification Windows | MIT |
| Apache ECharts 5 (`foulee/static/vendor/echarts.min.js`) | Graphiques | Apache 2.0 |
| Leaflet 1.9 (`foulee/static/vendor/leaflet/`) | Cartes | BSD 2 clauses |
| Barlow et Barlow Semi Condensed (`foulee/static/fonts/`) | Polices | SIL Open Font License 1.1 |

Sur un serveur, le script `installer-serveur.sh` installe aussi **uv** (Astral,
Apache 2.0 / MIT) et **Tailscale** (client BSD 3 clauses) depuis leurs sites officiels.

Les fonds de carte (OpenStreetMap, Plan IGN) sont chargés depuis Internet quand
tu ouvres une carte ; le réglage « Aucun » les désactive.
