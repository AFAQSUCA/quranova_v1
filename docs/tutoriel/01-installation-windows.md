# Chapitre 1 — Installer l'environnement sous Windows

> **Étape du plan :** 0.1 · **Durée :** 45 à 90 minutes · **Résultat :** un dossier de projet prêt, PostgreSQL local, Python 3.12.

## Objectif

Avoir sur votre PC tout ce qu'il faut pour développer : Git, Python 3.12, Node.js, VS Code, PostgreSQL, et le dépôt cloné **dans un dossier sans espace ni accent**.

> **Piège rencontré :** un chemin comme `G:\afaq projet\QURANOVA` (avec un espace) provoque des erreurs obscures avec les environnements virtuels, npm et Docker. Utilisez un chemin comme `C:\Projets\quranova`.

## 1. Installer les outils

Ouvrez **PowerShell** (menu Démarrer, tapez « PowerShell ») puis lancez :

```powershell
winget install Git.Git
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Microsoft.VisualStudioCode
```

**Fermez et rouvrez PowerShell**, puis vérifiez :

```powershell
git --version
py -3.12 --version
node --version
```

Attendu : trois numéros de version, dont `Python 3.12.x`. Si une commande est « introuvable », rouvrez PowerShell une fois de plus.

## 2. Autoriser les scripts PowerShell (une seule fois)

Sans cela, `.venv\Scripts\Activate.ps1` est refusé.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. Dire à Git qui vous êtes (une seule fois)

```powershell
git config --global user.name "Votre Nom"
git config --global user.email "votre@email"
```

## 4. Installer PostgreSQL

1. Téléchargez l'installateur Windows sur https://www.postgresql.org/download/windows/ (version 16 ou plus récente ; la 18 convient).
2. Pendant l'installation, **notez le mot de passe** de l'utilisateur `postgres` : vous en aurez besoin juste après.
3. Laissez le port `5432` et acceptez les composants proposés.

Retrouvez ensuite le dossier d'installation, il contient le numéro de version :

```powershell
dir "C:\Program Files\PostgreSQL"
```

## 5. Créer l'utilisateur et la base du projet

Remplacez `18` par votre numéro de version, si besoin. PowerShell vous demande le mot de passe de `postgres` à chaque commande.

```powershell
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
& $psql -U postgres -c "CREATE USER quranova WITH PASSWORD 'choisissez-un-mot-de-passe' CREATEDB;"
& $psql -U postgres -c "CREATE DATABASE quranova OWNER quranova;"
& $psql -U postgres -d quranova -c "SHOW server_encoding;"
```

Attendu : `CREATE ROLE`, `CREATE DATABASE`, puis `UTF8`.

- **`CREATEDB`** : pytest crée une base temporaire `test_quranova` à chaque lancement. Sans ce droit, tous les tests échouent avec `permission denied to create database`.
- **`UTF8`** : le corpus est en arabe. Un autre encodage corromprait le texte.

Vérifiez que le mot de passe fonctionne avec l'utilisateur du projet :

```powershell
& $psql -U quranova -d quranova -h localhost -c "SELECT 1;"
```

Attendu : un tableau avec `1`.

## 5 bis. Où trouver l'invite psql

« SQL Shell (psql) » n'est **pas** dans VS Code : c'est un programme Windows installé avec PostgreSQL (menu Démarrer, tapez « SQL Shell »). Les commandes ci-dessus font la même chose depuis PowerShell, sans l'ouvrir.

## 6. Cloner le dépôt dans un chemin sans espace

```powershell
New-Item -ItemType Directory -Force C:\Projets | Out-Null
Set-Location C:\Projets
git clone https://github.com/AFAQSUCA/quranova_v1.git quranova
Set-Location quranova
git switch -c travail
dir
```

Attendu : vous voyez `CLAUDE.md`, `DEMARRAGE.md`, `docs`, `data`. Vous travaillerez sur votre branche `travail` ; le dépôt contient aussi, sur la branche `claude/confident-goodall-7iqyck`, un exemple de référence de chaque chapitre.

Pour pouvoir comparer plus tard :

```powershell
git fetch origin claude/confident-goodall-7iqyck
```

## 7. Ouvrir le projet dans VS Code

```powershell
code .
```

Installez les extensions **Python** et **Pylance**, si VS Code les propose. Créez ensuite `.vscode\settings.json` pour que VS Code utilise le bon Python et lance pytest :

```json
{
  "python.defaultInterpreterPath": ".venv\\Scripts\\python.exe",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": ["."]
}
```

(Ce fichier sera pris en compte une fois le `.venv` créé au chapitre suivant.)

## Vérification de fin de chapitre

- [ ] `py -3.12 --version` répond.
- [ ] `psql` répond `UTF8` pour la base `quranova`.
- [ ] Le dépôt est dans un dossier **sans espace**, et `dir` y montre `CLAUDE.md`.

## Pour comprendre

- **Pourquoi Python 3.12 ?** C'est la version visée par le cahier des charges (§13.2) ; Django 5.2 la prend en charge.
- **Pourquoi PostgreSQL local sans Docker ?** Pendant les phases 0 à 2, on évite la complexité de Docker. Il sera introduit en phase 3 pour empaqueter le serveur de salle.
- **Pourquoi un utilisateur `quranova` séparé de `postgres` ?** Moindre privilège : l'application n'a pas besoin des droits de super-utilisateur.

## Journal d'apprentissage

Notez dans `docs\journal-apprentissage.md` : ce que vous avez installé, ce qui a posé problème, et pourquoi l'encodage UTF8 compte pour ce projet.
