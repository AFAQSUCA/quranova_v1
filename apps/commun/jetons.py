"""Jetons secrets des terminaux (tirage, commande, scène) : générés avec ``secrets``, jamais stockés.

Seule l'empreinte HMAC-SHA256 (clé : ``SECRET_KEY``) est enregistrée. Le jeton est long (256 bits) :
contrairement au code court d'un juré, il ne peut pas être deviné par essais successifs.
"""
import hashlib
import hmac
import secrets

from django.conf import settings


def fabriquer_jeton():
    return secrets.token_urlsafe(32)


def empreinte_du_jeton(jeton, contexte):
    """Empreinte du jeton pour un usage donné (``contexte`` évite de réutiliser un jeton ailleurs)."""
    message = f"{contexte}:{jeton}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()
