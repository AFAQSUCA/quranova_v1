"""Réglages de production : serveur de salle (Docker Compose : Nginx + Daphne + Redis + PostgreSQL, §13).

Tout ce qui varie d'une salle à l'autre vient de variables d'environnement (fichier ``.env``, jamais versionné).
Principe : **refuser de démarrer** plutôt que de tourner avec un réglage dangereux ou oublié.
Le serveur de salle parle en HTTP sur un Wi-Fi dédié sans Internet : pas de redirection HTTPS par défaut
(``DJANGO_HTTPS=1`` active les cookies sécurisés si un certificat est installé un jour).
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, SECRET_KEY

DEBUG = False

# --- Contrôles de démarrage ---------------------------------------------------------------------------------------

_MARQUEURS_DE_MODELE = ("remplacer", "changeme", "change-me", "secret", "django-insecure")
if len(SECRET_KEY) < 50 or any(m in SECRET_KEY.lower() for m in _MARQUEURS_DE_MODELE):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY est trop courte ou ressemble à la valeur du modèle .env.example : "
        "générez-en une avec  python -c \"import secrets; print(secrets.token_urlsafe(50))\"."
    )


def _liste(nom):
    return [v.strip() for v in os.environ.get(nom, "").split(",") if v.strip()]


ALLOWED_HOSTS = _liste("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS doit lister les adresses du serveur de salle (ex. 192.168.50.10,quranova.local), "
        "sans « * » : c'est aussi la liste que le WebSocket utilise pour refuser une autre origine."
    )

# Origines autorisées pour les formulaires (CSRF) : « http://192.168.50.10 » ; à défaut, celles des hôtes en http.
CSRF_TRUSTED_ORIGINS = _liste("DJANGO_CSRF_TRUSTED_ORIGINS") or [f"http://{h}" for h in ALLOWED_HOSTS]

# --- PostgreSQL : pool de connexions ----------------------------------------------------------------------------------
# Sans pool, chaque requête et chaque commande WebSocket ouvre puis ferme sa propre connexion. En simulation de charge
# (docs/recette/charge.md), le pool a ramené le p95 de propagation de 537 à 306 ms et le p95 HTTP de 680 à 401 ms.
# Actif par défaut ; DB_POOL=0 le désactive (diagnostic). Le pool prête des connexions déjà ouvertes (paquet psycopg_pool).
if os.environ.get("DB_POOL", "1") == "1":
    DATABASES["default"]["OPTIONS"] = {
        "pool": {"min_size": 4, "max_size": int(os.environ.get("DB_POOL_MAX", "20")), "timeout": 10},
    }

# --- Redis : la couche de canaux partagée entre processus (§13.5) -------------------------------------------------

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [os.environ.get("REDIS_URL", "redis://redis:6379/0")]},
    },
}

# --- Fichiers : collectés dans STATIC_ROOT puis servis par Nginx ----------------------------------------------------

STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))

# --- Sécurité ---------------------------------------------------------------------------------------------------------

_HTTPS = os.environ.get("DJANGO_HTTPS") == "1"
SESSION_COOKIE_SECURE = _HTTPS
CSRF_COOKIE_SECURE = _HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Journaux : sur la sortie standard (Docker les recueille) -----------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
