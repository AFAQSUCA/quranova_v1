# Démarre le serveur de salle QURANOVA (PostgreSQL + Redis + Daphne + Nginx) avec Docker Desktop.
# Usage :  .\scripts\demarrer.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker n'est pas installé (voir docs\recette\installation-serveur-de-salle.md)."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop n'est pas démarré : lancez-le, attendez l'icône verte, puis relancez ce script." }

if (-not (Test-Path .env)) {
    throw "Fichier .env absent : copiez .env.example en .env et remplissez-le (clé secrète, mot de passe, DJANGO_ALLOWED_HOSTS)."
}
foreach ($cle in "DJANGO_SECRET_KEY", "DB_PASSWORD", "DJANGO_ALLOWED_HOSTS") {
    if (-not (Select-String -Path .env -Pattern "^\s*$cle\s*=\s*\S+" -Quiet)) {
        throw "La variable $cle est absente ou vide dans .env (voir .env.example)."
    }
}

Write-Host "Construction et démarrage (la première fois, plusieurs minutes)..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "Le démarrage a échoué : docker compose logs web" }

$port = (Select-String -Path .env -Pattern "^\s*PORT_HTTP\s*=\s*(\d+)").Matches | ForEach-Object { $_.Groups[1].Value } | Select-Object -First 1
$suffixe = if ($port -and $port -ne "80") { ":$port" } else { "" }
Write-Host ""
Write-Host "Serveur de salle prêt. Adresses à ouvrir depuis les tablettes :" -ForegroundColor Green
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    ForEach-Object { Write-Host ("  http://{0}{1}/" -f $_.IPAddress, $suffixe) }
Write-Host ""
Write-Host "Première installation : créer l'administrateur avec"
Write-Host "  docker compose exec web python manage.py createsuperuser"
