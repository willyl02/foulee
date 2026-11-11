"""Withings : balances, tensiomètres, Sleep Analyzer, montres.

- ``client`` : autorisation OAuth 2.0 (appli Withings de l'utilisateur, page relais), jetons, appels ;
- ``parse`` : réponses de Withings → métriques quotidiennes « wi_… » ;
- ``sync`` : la synchro (mesures, nuits, activité), appelée par l'orchestrateur ``foulee.sync`` ;
- ``vue`` : état de la connexion, résumé pour la tuile, vue « Withings » créée d'office.
"""
