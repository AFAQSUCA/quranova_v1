# Chapitre 26 — Réglages de production et Redis (phase 3, étape 6.0a)

## Objectif
Préparer le serveur de salle : un module de réglages `config/settings/prod.py` qui **refuse de démarrer** si un réglage
dangereux est oublié, et une couche de canaux **Redis** pour que plusieurs processus Daphne partagent leurs groupes WebSocket.

## Pourquoi Redis (et `channels-redis`) ?
En développement, `InMemoryChannelLayer` garde les groupes dans la mémoire d'UN processus. Dès qu'il y a deux processus
(deux workers Daphne), un message envoyé dans l'un n'arrive pas aux écrans connectés à l'autre : le diaporama ne se
synchronise plus. Redis sert de boîte aux lettres commune. `channels-redis` est le pont officiel entre Channels et Redis
(nouvelle dépendance de `requirements/base.txt`, validée). Il tire le paquet `redis`.

## Fichiers
- `config/settings/prod.py` : `DEBUG=False` ; clé secrète d'au moins 50 caractères et différente du modèle ; `DJANGO_ALLOWED_HOSTS`
  obligatoire et sans `*` (cette liste sert aussi au contrôle d'origine du WebSocket) ; Redis via `REDIS_URL` ;
  `STATIC_ROOT` ; cookies `HttpOnly` ; `X-Frame-Options: DENY` ; journaux sur la sortie standard.
- `.env.example` : les variables de production, en commentaire.
- `requirements/base.txt` : `channels-redis`.
- `apps/commun/tests/test_reglages_production.py` : chaque contrôle dans un sous-processus ; un test d'intégration Redis
  (ignoré si Redis n'est pas joignable sur `localhost:6379`).

## Commandes (PowerShell)
```powershell
pip install -r requirements\dev.txt
pytest apps\commun\tests\test_reglages_production.py
# Essai des réglages de production (variables posées pour cette session PowerShell seulement) :
$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
$env:DJANGO_ALLOWED_HOSTS = "192.168.50.10"
python manage.py check --deploy
```

## Résultat attendu
- Les tests passent (le test Redis est « skipped » sous Windows tant que Redis n'y est pas : il tournera dans Docker).
- `check --deploy` affiche 4 avertissements HTTPS (HSTS, redirection SSL, cookies sécurisés) : **voulu**, le serveur de salle
  parle en HTTP sur un Wi-Fi sans Internet. `DJANGO_HTTPS=1` les active si un certificat est installé un jour.

**Question :** pourquoi refuser `DJANGO_ALLOWED_HOSTS=*` alors que le Wi-Fi est dédié et sans Internet ?
