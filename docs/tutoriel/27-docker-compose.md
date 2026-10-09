# Chapitre 27 — Empaqueter le serveur de salle avec Docker Compose (phase 3, étape 6.0b)

## Objectif
Un seul ordre (`.\scripts\demarrer.ps1`) lance les quatre services du serveur de salle, sans rien installer d'autre que Docker Desktop.

## Les quatre services (`compose.yaml`)
| Service | Rôle | Remarque |
|---|---|---|
| `db` | PostgreSQL 16 | données dans le volume `donnees-postgres` ; jamais exposé hors de Docker |
| `redis` | couche de canaux WebSocket | sans persistance : ce ne sont que des messages éphémères |
| `web` | Daphne (ASGI) + Django | au démarrage : attend la base, `migrate`, `collectstatic` |
| `nginx` | porte d'entrée port 80 | sert `/static/` et `/media/`, relaie HTTP et `/ws/` (WebSocket) vers `web` |

## Fichiers
- `Dockerfile` : étape `front` (Node compile le front Vue), étape `base`/`web` (Python, sans Node), cible `test` (+ pytest).
- `docker/entrypoint.sh`, `docker/nginx.conf`, `.dockerignore`.
- `scripts/demarrer.ps1`, `arreter.ps1`, `tests-docker.ps1`, `sauvegarder.ps1`.
- `docs/recette/installation-serveur-de-salle.md` : guide pas à pas Windows (Docker Desktop, WSL 2, IP fixe, pare-feu, reprise REC-36).
- `conftest.py` : les fichiers téléversés par les tests vont dans un dossier jetable.

## Points d'attention (pourquoi c'est écrit ainsi)
- **Nginx et le WebSocket** : sans les en-têtes `Upgrade` / `Connection`, la connexion `/ws/` échoue. `proxy_read_timeout 3600s` évite qu'une
  connexion calme soit coupée (le cœur de la présentation bat toutes les 15 s).
- **`ALLOWED_HOSTS`** : l'en-tête `Host` que Nginx transmet doit y figurer, sinon Django répond 400 (testé : un hôte inconnu reçoit 400).
  Le test de santé de `web` envoie donc le premier hôte autorisé.
- **Données et redémarrage** : un `docker compose down` garde les volumes ; seul `down -v` efface la base. À ne jamais lancer le jour J.
- **Sans Internet le jour J** : les images construites restent sur le disque ; rien n'est téléchargé au démarrage.

## Commandes (PowerShell)
```powershell
Copy-Item .env.example .env ; notepad .env
.\scripts\demarrer.ps1
docker compose exec web python manage.py createsuperuser
.\scripts\tests-docker.ps1
.\scripts\arreter.ps1
```

## Ce qui a été vérifié (dans le conteneur de développement, pas sous Windows)
- Les quatre services démarrent et deviennent « healthy » ; migrations et collectstatic automatiques.
- Via Nginx : accueil, `/static/` (logo, front compilé, CSS de l'admin), pages admin et tirage en 200 ; hôte inconnu en 400.
- WebSocket à travers Nginx : la connexion s'ouvre, puis est refusée proprement (4403) pour une session inconnue.
- Les données survivent à un `down` puis `up` ; `verifier_audit` s'exécute dans le conteneur.
- 1048 tests passent dans l'image de test (les 12 « skipped » dépendent de Redis ou de `pg_dump`).

## Ce qui n'a PAS pu être vérifié
- Docker Desktop / WSL 2 sous Windows et les scripts PowerShell : à jouer par toi (REC-40).
- Le paquet `postgresql-client` (pour `pg_dump`/`pg_restore` dans l'image) : le sandbox de développement bloque le dépôt Debian ; l'étape `apt-get`
  est écrite mais non exécutée ici. Premier contrôle à faire chez toi : `.\scripts\sauvegarder.ps1`.

**Question :** pourquoi Redis n'a-t-il pas besoin de volume alors que PostgreSQL en a un ?
