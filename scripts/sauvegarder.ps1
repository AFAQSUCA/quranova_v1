# Sauvegarde PostgreSQL horodatée dans le dossier DOSSIER_SAUVEGARDES du .env (par défaut .\sauvegardes).
# À planifier toutes les 15 minutes pendant un concours (Planificateur de tâches Windows).
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose exec -T web python manage.py sauvegarder --dossier /data/sauvegardes
