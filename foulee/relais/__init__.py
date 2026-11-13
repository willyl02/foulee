"""Le relais de Foulée : le petit serveur, sur Internet, qui relie un coach et ses élèves.

Chacun garde Foulée et son historique chez lui ; le relais ne garde que les comptes (coachs, élèves),
les invitations et, plus tard, l'extrait que chaque élève choisit de partager. C'est Foulée lui-même,
lancé en « mode relais » (``foulee relais serveur``) : il n'expose que son API, rien de Garmin.
"""

API_VERSION = 1  # version du dialogue entre Foulée et le relais : un relais accepte toutes les Foulée de la même
