# Chapitre 2 — Le squelette Django

> **Étape du plan :** 0.2 · **Durée :** 60 minutes · **Commit de référence :** `f308ceb` · **Résultat :** un projet Django qui démarre en ASGI, connecté à PostgreSQL, avec un premier test vert.

## Objectif

Créer le projet `config`, avec des réglages séparés (`base` commun, `dev` pour votre PC), la configuration par variables d'environnement (`.env`), PostgreSQL, Channels en mémoire, et un test « smoke » : *la page d'accueil répond*.

## 1. L'environnement virtuel et les dépendances

À la racine du projet (`C:\Projets\quranova`) :

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Attendu : l'invite PowerShell commence par `(.venv)`.

Créez le dossier et les deux fichiers de dépendances :

```powershell
New-Item -ItemType Directory requirements | Out-Null
```

**Fichier `requirements\base.txt`**

```text
Django>=5.2,<5.3
channels>=4.2,<5
daphne>=4.1,<5
psycopg[binary]>=3.2,<4
python-dotenv>=1.0,<2
```

**Fichier `requirements\dev.txt`**

```text
-r base.txt
pytest>=8.3,<9
pytest-django>=4.9,<5
```

```powershell
pip install -r requirements\dev.txt
python -c "import django, channels, daphne, psycopg; print(django.get_version())"
```

Attendu : `5.2.x`.

- **Deux fichiers** : `base` pour tout le monde, `dev` y ajoute les outils de test.
- **`psycopg[binary]`** embarque la bibliothèque PostgreSQL pour Windows : rien à compiler.

## 2. Le `.gitignore`

À créer **avant** le premier commit, pour ne jamais versionner le `.venv` ni les secrets :

**Fichier `.gitignore`**

```text
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
node_modules/
frontend/dist/
staticfiles/
*.log
db.sqlite3
```

## 3. Créer le projet Django

```powershell
django-admin startproject config .
New-Item -ItemType Directory config\settings, config\tests, templates, static | Out-Null
Move-Item config\settings.py config\settings\base.py
New-Item -ItemType File config\settings\__init__.py, config\tests\__init__.py, templates\.gitkeep, static\.gitkeep | Out-Null
```

Le point final de `startproject config .` crée `manage.py` et le dossier `config\` directement à la racine.

Ouvrez `manage.py`, `config\asgi.py` et `config\wsgi.py` : dans chacun, une ligne contient `"config.settings"`. Modifiez-la, **à la main**, pour voir où Django choisit ses réglages :

```python
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
```

## 4. Les réglages

**Fichier `config\settings\base.py`**

```python
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
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

**Fichier `config\settings\dev.py`**

```python
"""Réglages de développement : Windows local, sans Docker ni Redis."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Couche de canaux en mémoire : valable avec UN seul processus (cf. phase 3 : Redis).
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}
```

À retenir :

- **`os.environ["DJANGO_SECRET_KEY"]`** sans valeur par défaut : si la clé manque, Django refuse de démarrer, au lieu de tourner avec une clé faible oubliée.
- **`"daphne"` en premier dans `INSTALLED_APPS`** : `runserver` sert alors en ASGI, seul mode qui sait tenir un WebSocket.
- **`InMemoryChannelLayer`** : valable avec **un seul** processus (le développement). En production (phase 3), on passera à Redis en changeant uniquement ce réglage.

## 5. Les secrets : `.env`

**Fichier `.env.example`**

```text
# Copier ce fichier en .env puis remplir les valeurs. Le .env n'est JAMAIS versionné.
DJANGO_SECRET_KEY=remplacer-par-une-cle-aleatoire

# PostgreSQL local
DB_NAME=quranova
DB_USER=quranova
DB_PASSWORD=remplacer-par-le-mot-de-passe
DB_HOST=localhost
DB_PORT=5432
```

Créez votre vrai `.env` et générez une clé secrète :

```powershell
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Ouvrez `.env` dans VS Code (`code .env`) et remplacez :

- `DJANGO_SECRET_KEY` par la clé affichée ;
- `DB_PASSWORD` par le mot de passe de l'utilisateur `quranova` (chapitre 1).

Règles de format : une variable par ligne, **pas d'espace** autour du `=`, **pas de guillemets**.

> **Piège rencontré :** un `.env` hérité d'un ancien modèle utilisait des noms `POSTGRES_*`. Le projet attend `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`. Un nom différent donne `KeyError: 'DB_PASSWORD'`.

Pour voir **les noms** des variables que Python lit, sans afficher les valeurs :

```powershell
python -c "from dotenv import dotenv_values; v = dotenv_values('.env'); print({k: ('rempli' if val else 'VIDE') for k, val in v.items()})"
```

## 6. La page d'accueil

**Fichier `config\urls.py`**

```python
"""Routes racine du projet QURANOVA."""
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="accueil.html"), name="accueil"),
    path("admin/", admin.site.urls),
]
```

**Fichier `templates\accueil.html`**

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>QURANOVA</title>
</head>
<body>
  <h1>QURANOVA</h1>
  <p>Serveur de salle en cours de construction.</p>
</body>
</html>
```

## 7. pytest et le premier test

**Fichier `pytest.ini`**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.dev
python_files = test_*.py
```

**Fichier `config\tests\test_accueil.py`**

```python
"""Test « smoke » : vérifie que le projet démarre et que la page d'accueil répond."""
from django.urls import reverse


def test_page_accueil_repond(client):
    reponse = client.get(reverse("accueil"))

    assert reponse.status_code == 200
    assert "QURANOVA" in reponse.content.decode()
```

## 8. Vérifier

```powershell
python manage.py check
python manage.py migrate
pytest
python manage.py runserver
```

Attendu :

- `check` : `System check identified no issues`.
- `migrate` : une série de `Applying ... OK`.
- `pytest` : `1 passed`.
- `runserver` : une ligne `Starting ASGI/Daphne ... development server`. Ouvrez http://127.0.0.1:8000/ : la page « QURANOVA » s'affiche. Arrêtez avec `Ctrl+C`.

## 9. Commit

```powershell
git add .gitignore .env.example requirements config manage.py pytest.ini static templates
git status
git commit -m "Squelette Django : projet config, réglages base/dev, PostgreSQL, Channels en mémoire, test smoke"
```

Vérifiez dans `git status` que **`.env` et `.venv` n'apparaissent pas**.

## Pour comprendre : le trajet d'une requête HTTP

1. Le navigateur envoie `GET /` à Daphne (serveur ASGI).
2. Daphne appelle l'application ASGI de `config\asgi.py`, qui route le HTTP vers Django.
3. Django traverse les *middlewares* (sécurité, sessions, CSRF...).
4. Le résolveur d'URL (`ROOT_URLCONF = "config.urls"`) trouve la route `""` et appelle `TemplateView`.
5. La vue charge `templates\accueil.html` (dossier déclaré dans `TEMPLATES["DIRS"]`) et le rend.
6. La réponse remonte par les mêmes middlewares jusqu'au navigateur.

Le test `test_page_accueil_repond` rejoue ce trajet sans navigateur grâce au `client` de pytest-django.

## Questions de compréhension

1. Pourquoi `base.py` remonte-t-il de **trois** niveaux (`.parent.parent.parent`) pour trouver la racine du projet, alors que le `settings.py` d'origine n'en remontait que deux ?
2. Pourquoi sépare-t-on `base.py` et `dev.py` plutôt que d'écrire des `if DEBUG:` dans un seul fichier ?
3. Dans `dev.py`, la couche de canaux est en mémoire. Que se passerait-il avec **deux** processus Daphne ?

<details>
<summary>Réponses</summary>

1. `base.py` est dans `config\settings\` : `base.py` → `settings` → `config` → racine. Il y a un dossier de plus que dans le `settings.py` d'origine, qui était directement dans `config\`.
2. Le commun est écrit une fois ; ce qui change selon l'environnement est isolé. Avec des `if DEBUG:`, un oubli de condition suffit à exposer un réglage de développement en salle. La phase 3 ajoutera simplement un `prod.py`.
3. Chaque processus aurait sa propre mémoire : un message envoyé au groupe d'une prestation depuis le processus A ne serait jamais reçu par un écran connecté au processus B, sans aucune erreur visible. Redis est un serveur à part que tous les processus consultent.
</details>

## Journal d'apprentissage

Notez le trajet d'une requête avec vos mots, et la différence entre `base.py` et `dev.py`.
