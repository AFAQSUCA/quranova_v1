# Lance toute la suite de tests Python dans Docker (même environnement que le serveur de salle).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose --profile outils run --rm --build tests
