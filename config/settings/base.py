"""Réglages communs à tous les environnements (développement, production)."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Racine du dépôt : base.py -> settings -> config -> racine (3 niveaux)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Charge le fichier .env (non versionné) dans les variables d'environnement.
load_dotenv(BASE_DIR / ".env")

# Pas de valeur par défaut : si la clé manque, Django refuse de démarrer.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = False
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "daphne",  # doit précéder staticfiles : fait servir runserver en ASGI
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "apps.commun",
    "apps.clients",
    "apps.utilisateurs",
    "apps.concours",
    "apps.candidats",
    "apps.coran",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# PostgreSQL : paramètres lus dans .env (jamais écrits dans le code).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "quranova"),
        "USER": os.environ.get("DB_USER", "quranova"),
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Utilisateur personnalisé (rôles, organisation) : à fixer AVANT la première migration d'un projet.
AUTH_USER_MODEL = "utilisateurs.Utilisateur"

# Fichiers téléversés (logos des clients, formulaires de consentement...). Jamais versionnés.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
