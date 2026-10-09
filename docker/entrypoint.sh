#!/bin/sh
# Démarrage du serveur de salle : attend PostgreSQL, applique les migrations, rassemble les fichiers statiques
# (partagés avec Nginx par un volume), puis lance la commande demandée (Daphne par défaut).
set -e

python - <<'PY'
import os, sys, time
import psycopg

parametres = dict(
    host=os.environ.get("DB_HOST", "db"), port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "quranova"), user=os.environ.get("DB_USER", "quranova"),
    password=os.environ["DB_PASSWORD"],
)
for essai in range(60):
    try:
        psycopg.connect(**parametres, connect_timeout=3).close()
        sys.exit(0)
    except psycopg.OperationalError as erreur:
        print(f"PostgreSQL pas encore prêt ({essai + 1}/60) : {erreur}", flush=True)
        time.sleep(2)
sys.exit("PostgreSQL injoignable après 2 minutes.")
PY

if [ "$1" = "daphne" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi
exec "$@"
