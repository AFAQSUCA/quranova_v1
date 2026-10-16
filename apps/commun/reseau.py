"""Adresse réelle du client d'une requête.

Derrière Nginx, ``REMOTE_ADDR`` est l'adresse de Nginx pour TOUT le monde : une limitation « par adresse » bloquerait alors toutes les tablettes
en même temps. Nginx transmet donc l'adresse réelle dans ``X-Real-IP`` (il l'écrase à chaque requête : un client ne peut pas la forger,
puisque Daphne n'est joignable que par Nginx). On ne croit cet en-tête que si ``PROXY_DE_CONFIANCE`` est vrai (production) ; en développement,
sans Nginx, n'importe quel client pourrait l'envoyer : on l'ignore.
"""
from django.conf import settings


def adresse_du_client(requete):
    if getattr(settings, "PROXY_DE_CONFIANCE", False):
        transmise = requete.META.get("HTTP_X_REAL_IP", "").strip()
        if transmise:
            return transmise[:64]
    return requete.META.get("REMOTE_ADDR", "")[:64]
