# Analyse de sécurité automatisée (REC-28) : code Python (bandit), dépendances Python (pip-audit), dépendances du front (npm audit).
# Usage :  .\scripts\audit-securite.ps1        (environnement virtuel actif, Internet nécessaire pour les bases de vulnérabilités)
# Code de sortie 0 : aucune alerte ; 1 : au moins une analyse a échoué.
Set-Location (Split-Path $PSScriptRoot -Parent)
$echecs = 0

Write-Host "`n== bandit : analyse statique du code Python ==" -ForegroundColor Cyan
bandit -r apps config -c bandit.yaml -q
if ($LASTEXITCODE -ne 0) { $echecs++ }

Write-Host "`n== pip-audit : vulnérabilités connues des dépendances Python ==" -ForegroundColor Cyan
pip-audit -r requirements\dev.txt --progress-spinner off
if ($LASTEXITCODE -ne 0) { $echecs++ }

Write-Host "`n== npm audit : vulnérabilités connues des dépendances du front (niveau élevé et critique) ==" -ForegroundColor Cyan
Push-Location frontend
npm audit --audit-level=high
if ($LASTEXITCODE -ne 0) { $echecs++ }
Pop-Location

if ($echecs -eq 0) { Write-Host "`nAucune alerte : audit de sécurité réussi." -ForegroundColor Green; exit 0 }
Write-Host "`n$echecs analyse(s) en alerte : voir ci-dessus." -ForegroundColor Red
exit 1
