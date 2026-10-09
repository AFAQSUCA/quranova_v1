# Arrête le serveur de salle. Les données (PostgreSQL, logos) sont conservées dans des volumes Docker.
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose down
