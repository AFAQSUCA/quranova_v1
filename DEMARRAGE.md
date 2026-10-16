w# Démarrer QURANOVA avec Claude Code (Windows)

Tout se fait sous **Windows 10 ou 11**, dans **PowerShell**. Aucun Linux n'est nécessaire pour développer.
Docker Desktop ne sera installé qu'en phase 3, pour empaqueter le serveur de salle.

## 1. Installer les outils (une seule fois)

Ouvrir **PowerShell** (menu Démarrer → « PowerShell ») et installer avec `winget` :

```powershell
winget install Git.Git
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Microsoft.VisualStudioCode
winget install Anthropic.ClaudeCode
```

Puis **fermer et rouvrir PowerShell** et vérifier :

```powershell
git --version
py -3.12 --version
node --version
claude --version
```

> Si `claude` n'est pas reconnu, utiliser l'installateur officiel : `irm https://claude.ai/install.ps1 | iex`, puis rouvrir PowerShell.
> Git for Windows est important : Claude Code s'en sert pour exécuter ses commandes.
> Claude Code nécessite un abonnement Claude Pro, Max, Team ou Enterprise ; à la première commande `claude`, connectez-vous via le navigateur.

**PostgreSQL** : télécharger l'installateur Windows sur https://www.postgresql.org/download/windows/ (version 16 ou plus récente).
Pendant l'installation, notez le mot de passe de l'utilisateur `postgres`. Ensuite, dans « SQL Shell (psql) » :

```sql
CREATE USER quranova WITH PASSWORD 'choisir-un-mot-de-passe';
CREATE DATABASE quranova OWNER quranova;
ALTER USER quranova CREATEDB;   -- nécessaire pour que les tests créent leur base temporaire
```

**WeasyPrint (PDF)** : le procès-verbal et les classements en PDF utilisent WeasyPrint, qui a besoin de la bibliothèque Pango. Sous Windows :

1. Installer MSYS2 (https://www.msys2.org), puis dans le terminal « MSYS2 UCRT64 » : `pacman -S mingw-w64-ucrt-x86_64-pango` (ou, pour le terminal MINGW64 : `pacman -S mingw-w64-x86_64-pango`).
2. Dire à Python où trouver les DLL (une fois, puis rouvrir PowerShell) :
   ```powershell
   [Environment]::SetEnvironmentVariable("WEASYPRINT_DLL_DIRECTORIES", "C:\msys64\ucrt64\bin", "User")   # mingw64\bin si vous avez installé la variante MINGW64
   ```
3. Vérifier : `python -c "from weasyprint import HTML; HTML(string='<p>ok</p>').write_pdf('essai.pdf')"` doit créer `essai.pdf`.

Sans Pango, rien ne casse : les tests PDF sont ignorés et les liens PDF affichent un message qui renvoie vers la version imprimable (« Imprimer → Enregistrer en PDF »).
Dans Docker (serveur de salle), les bibliothèques sont installées par le `Dockerfile` : rien à faire.

**Autoriser les scripts PowerShell** (pour activer l'environnement Python), une seule fois :

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**VS Code** : installer l'extension « Claude Code » (et « Python ») depuis le panneau Extensions.

## 2. Mettre en place le dépôt

Décompresser le kit, par exemple dans `C:\Projets\quranova`, puis :

```powershell
cd C:\Projets\quranova
git init
git config user.name "Votre Nom"
git config user.email "votre@email"
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
Copy-Item .env.example .env     # puis ouvrir .env et remplir les mots de passe
git add .
git commit -m "Kit de démarrage : CDC v2.0, CLAUDE.md, prompts"
```

> Évitez de placer le projet dans un dossier synchronisé (OneDrive) ou contenant des espaces et des accents dans le chemin.

Télécharger ensuite le corpus Tanzil comme indiqué dans `data\corpus\LISEZMOI.md`.

## 3. Première séance avec Claude Code

```powershell
cd C:\Projets\quranova
claude
```

(ou ouvrir le dossier dans VS Code et lancer Claude Code depuis l'extension)

1. Vérifier le style : taper `/output-style` → **Learning** doit être sélectionné (réglé dans `.claude\settings.json`).
2. Premier message :
   > Lis CLAUDE.md, docs/cdc/00-index.md et docs/cdc/24-planning-et-phasage.md. Résume-moi en 10 lignes ce que nous allons construire, la règle la plus importante selon toi, et ce que tu attends de moi dans la phase 0. Ne code rien.
3. Puis suivre `docs\prompts-iterations.md`, étape 0.1 (en plan mode : Maj+Tab).

## 4. Rituel de chaque séance

1. `git status` : partir d'un dépôt propre ; `.venv\Scripts\Activate.ps1` pour activer Python.
2. Un prompt de `docs\prompts-iterations.md`, une étape à la fois.
3. Lire le plan, poser des questions, valider.
4. Écrire vous-même les parties `TODO(human)`.
5. Lancer les tests (`pytest`), relire `git diff`, commiter.
6. Un prompt de compréhension, puis remplir `docs\journal-apprentissage.md`.
7. `/clear` avant l'étape suivante.

## 5. Et le serveur de salle ?

En phase 3 (étape 6.0 des prompts), vous installerez **Docker Desktop pour Windows**, qui active lui-même le composant WSL 2 de Windows
en arrière-plan : vous n'avez rien de Linux à gérer. Votre ordinateur portable Windows pourra alors servir de serveur de salle,
avec PostgreSQL, Redis et l'application dans des conteneurs.

## 6. Contenu du kit

| Fichier | Rôle |
|---|---|
| `CLAUDE.md` | Instructions lues par Claude à chaque session : projet, environnement Windows, méthode pédagogique, stack, vocabulaire, règles absolues |
| `.claude\settings.json` | Style « Learning » et interdiction de lire `.env` |
| `docs\cdc\` | Cahier des charges v2.0, une section par fichier |
| `docs\QURANOVA_CDC_v2.0_outil_interne.docx` | Le document Word de référence |
| `docs\prompts-iterations.md` | Les prompts de chaque phase, du squelette à l'autorecette |
| `docs\journal-apprentissage.md` | Votre journal de compréhension |
| `data\corpus\LISEZMOI.md` | Procédure de téléchargement et de traçabilité du corpus Tanzil |
| `.env.example`, `.gitignore` | Configuration et exclusions Git |
