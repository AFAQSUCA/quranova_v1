# QURANOVA — Exécuter l'application de A à Z (Windows, PowerShell)

Ce fichier te mène, **dans l'ordre**, de « le dossier est cloné » à « un concours de démonstration complet : tirage, diaporama, notation, classement, procès-verbal », puis au **serveur de salle** (Docker) et au **jour J**.
Toutes les commandes sont pour **PowerShell**, lancées **depuis la racine du projet** (`C:\quranova_v1`).

> Légende : 🟢 à faire une seule fois · 🔁 à refaire à chaque session de travail · ⚠️ piège fréquent

---

## PARTIE 1 — Installer (🟢 une seule fois)

### 1.1 Outils
```powershell
winget install Git.Git
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
Set-Location C:\
```
Ferme et rouvre PowerShell, puis :
```powershell
git --version ; py -3.12 --version ; node --version
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
**PostgreSQL 16+** : installe-le depuis https://www.postgresql.org/download/windows/ (note le mot de passe de l'utilisateur `postgres`).

### 1.2 Récupérer le code
```powershell
git clone https://github.com/afaqsuca/quranova_v1.git
Set-Location C:\quranova_v1
git checkout claude/confident-goodall-7iqyck
```
🔁 Pour récupérer mes mises à jour plus tard : `git pull origin claude/confident-goodall-7iqyck`, puis `pip install -r requirements\dev.txt`, `python manage.py migrate` et `cd frontend; npm install; npm run build; cd ..`.

### 1.3 Base de données
Ouvre **SQL Shell (psql)**, connecte-toi en `postgres`, puis :
```sql
CREATE USER quranova WITH PASSWORD 'choisis-un-mot-de-passe';
CREATE DATABASE quranova OWNER quranova;
ALTER USER quranova CREATEDB;
```
⚠️ `CREATEDB` est **obligatoire** : les tests créent une base temporaire.

### 1.4 Fichier `.env`
```powershell
Copy-Item .env.example .env
notepad .env
```
À remplir : `DJANGO_SECRET_KEY` (une longue chaîne aléatoire : `py -3.12 -c "import secrets; print(secrets.token_urlsafe(50))"`) et `DB_PASSWORD` (le mot de passe de l'étape 1.3). Le reste (`DB_NAME=quranova`, `DB_USER=quranova`, `DB_HOST=localhost`, `DB_PORT=5432`) convient.
⚠️ Le `.env` n'est **jamais** versionné.

### 1.5 Python
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements\dev.txt
python manage.py check
python manage.py migrate
```

### 1.6 Corpus coranique
Les fichiers Tanzil sont déjà dans `data\corpus\`. Importe-les (sans aucune transformation du texte) :
```powershell
python manage.py import_corpus --dry-run     # contrôle sans rien écrire
python manage.py import_corpus
```
Résultat attendu : « 114 sourates, 6236 versets » et un statut **« importée »**.

### 1.7 Écrans temps réel (tirage, scène, commande, jury)
```powershell
Set-Location frontend
npm install
npm run build
Set-Location ..
```
⚠️ Sans `npm run build`, ces quatre écrans restent **blancs**.

### 1.8 Compte administrateur
```powershell
python manage.py createsuperuser
```
Mot de passe de **12 caractères minimum**. (En développement, le deuxième facteur est désactivé ; il est obligatoire en production.)

---

## PARTIE 2 — Lancer et voir l'application (🔁)

```powershell
.venv\Scripts\Activate.ps1
python manage.py creer_demo --valider-corpus-pour-test     # 1re fois seulement (voir ci-dessous)
python manage.py runserver
```
La commande `creer_demo` (développement uniquement) crée : un client « Association Démo », un concours **en cours** avec une épreuve **ouverte**, **6 candidats admis**, des séries de vrais passages, une session, une **tablette de tirage**, et deux comptes :

| Compte | Mot de passe | Rôle |
|---|---|---|
| `operateur` | `demo-12345` | opérateur (appelle, commande, clôture) |
| `responsable` | `demo-12345` | responsable du client (valide les classements) |

Elle affiche aussi l'**adresse de la tablette de tirage** `http://127.0.0.1:8000/tirage/#<jeton>` : **copie-la tout de suite** (le jeton n'est affiché qu'une fois).
⚠️ La validation du corpus « pour test » n'est **pas** celle du référent coranique : voir la Partie 4.

Ouvre `http://127.0.0.1:8000/` (accueil) puis `http://127.0.0.1:8000/admin/`.

---

## PARTIE 3 — Dérouler un concours de démonstration, étape par étape

Utilise **deux navigateurs (ou un navigateur normal + une fenêtre privée)** : l'un connecté en `operateur`, l'autre en `responsable`.

### 3.1 Préparer les écrans
1. **Tablette de tirage** : ouvre l'adresse affichée par `creer_demo` (`/tirage/#jeton`) dans un onglet.
2. **UUID de la session** : *Admin → Sessions* → ouvre la session → copie l'UUID dans l'adresse (`/admin/concours/session/<UUID>/change/`).
3. **Écran de scène** : *Admin → Terminaux → Ajouter* → session = la session, nom = « Scène 1 », **type = Écran de scène** → l'adresse s'affiche **une seule fois** dans le message jaune : ouvre-la (forme `/scene/<UUID>/#jeton`), puis appuie sur ⛶ pour le plein écran.
   *Astuce : pour voir le texte coranique sur la scène, coche « Affichage scène » dans la fiche de l'épreuve.*
4. **Écran de commande** : `http://127.0.0.1:8000/commande/<UUID de la session>/` (connecté en `operateur`).
5. **Juré** : *Admin → Jurés → Ajouter* (nom, prénom) ; dans le bloc « Affectations », affecte-le à l'épreuve. Puis, dans la liste des jurés : coche-le → **« Remettre un code d'accès pour une session »** → choisis la session → **note le code affiché (une seule fois)**. Ouvre `http://127.0.0.1:8000/jury/<UUID de la session>/` et saisis le code.

### 3.2 Faire passer un candidat
1. *Admin → Prestations* → coche une prestation → **« Appeler au tirage »**. Son nom apparaît sur la tablette de tirage.
2. Sur la tablette : **« Effectuer mon tirage »** → **« Oui, tirer »**. Une série s'affiche. (Un double clic ne donne qu'un tirage.)
3. **Commande** : choisis la prestation tirée → **« Préparer l'affichage »** → **« Démarrer la prestation »**. La scène et le juré affichent la première diapositive.
4. Clique **« Diapositive suivante ▶ »** plusieurs fois : la scène change avec un **balayage de droite à gauche**, au même rang sur tous les écrans. Teste **« ◀ Précédente »**, **pause / reprendre**, et ferme/rouvre l'écran de scène (il retrouve la bonne diapositive).
5. **« Terminer la prestation »**.
6. **Juré** : touche la prestation, saisis une note par critère (0 à 10), laisse un critère vide pour voir « évaluation incomplète » (jamais un zéro), complète, puis **« Valider mon évaluation »**.
7. *Admin → Prestations* → **« Clôturer la prestation (toutes les évaluations validées) »**.

Refais l'opération pour 2 ou 3 autres candidats (notes différentes) pour obtenir un vrai classement.

### 3.3 Résultats (côté `responsable`)
1. Connecté en `responsable` : *Admin → Épreuves* → ouvre l'épreuve pour voir le **classement provisoire** (recalculé à chaque affichage).
2. Coche l'épreuve → **« Valider le classement définitif (responsable client) »** (variante « en confirmant les ex aequo » si besoin). ⚠️ Seul le responsable peut : l'opérateur est refusé.
3. *Admin → Concours* → ouvre le concours → **« Documents à remettre »** : procès-verbal (imprimable et PDF), classements par catégorie (PDF), export CSV.
   *(Le PDF demande WeasyPrint et Pango : voir `DEMARRAGE.md`. Sans eux, la version imprimable fonctionne et le lien PDF explique le manque.)*

### 3.4 Autres gestes à essayer
- **Annuler un tirage** : *Admin → Tirages* → coche → « Annuler le tirage » (motif obligatoire).
- **Corriger une note validée** : le juré touche « Corriger… » → *Admin → Corrections de notes* (en `responsable`) → « Approuver ».
- **Journal des incidents** : *Admin → Incidents → Ajouter*.
- **Dupliquer le concours** : *Admin → Concours* → coche → « Dupliquer vers une nouvelle édition ».
- **Import de candidats** : *Concours → fiche → « Modèle d'import des candidats (CSV) »*, remplis-le, puis *Concours → coche → « Importer des candidats (fichier CSV) »* (simulation cochée par défaut).
- **Fiches de secours** : *Admin → Sessions →* fiche → « Fiches de notation de secours ».
- **Journal d'audit** : `python manage.py verifier_audit` (doit répondre « aucune anomalie »).

---

## PARTIE 4 — La vraie validation du corpus (jalon J0, avant tout concours réel)
La validation « pour test » de `creer_demo` ne sert qu'au développement. Pour un vrai concours :
1. Désigne le **référent coranique**.
2. *Admin → Versions du corpus* → ouvre la version « importée » → **« Procès-verbal à signer »** (imprimable ou PDF) : 5 contrôles automatiques + échantillon de relecture + rendu typographique + signatures.
3. Le référent relit au Mushaf de Médine et **signe**.
4. Coche la version → **« Enregistrer la validation du référent coranique »** (nom, date, attestation) → puis **« Activer pour les nouveaux concours »**.
Détails : `docs\recette\validation-du-corpus.md`.

---

## PARTIE 5 — Tests et contrôles (🔁 avant de livrer)
```powershell
.venv\Scripts\Activate.ps1
pytest                                   # ~1 300 tests Python (quelques-uns « skipped » sans Redis ou Pango : normal)
Set-Location frontend
npm test ; npm run typecheck
Set-Location ..
.\scripts\audit-securite.ps1             # bandit + pip-audit + npm audit
```
Les tests créent une base temporaire `test_<nom>` (d'où le droit `CREATEDB`).

---

## PARTIE 6 — Le serveur de salle (Docker, production)
Guide détaillé : `docs\recette\installation-serveur-de-salle.md`. Version courte :

### 6.1 Une seule fois, **avec Internet**
1. Installe **Docker Desktop** (option **WSL 2**), redémarre, attends l'icône verte.
2. Dans `.env`, ajoute pour la production :
   ```
   DJANGO_ALLOWED_HOSTS=192.168.50.10        # l'IP FIXE du portable sur le Wi-Fi dédié (jamais « * »)
   ```
   (`DJANGO_SECRET_KEY` : **50 caractères minimum**, différente de l'exemple ; `DB_PASSWORD` renseigné.)
3. Pare-feu (PowerShell **administrateur**) :
   ```powershell
   New-NetFirewallRule -DisplayName "QURANOVA HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -Profile Private
   ```

### 6.2 Démarrer / arrêter
```powershell
.\scripts\demarrer.ps1        # construit (1re fois : plusieurs minutes) et démarre PostgreSQL + Redis + Daphne + Nginx ; affiche les adresses
.\scripts\arreter.ps1         # arrête, les données sont conservées
```
⚠️ **Jamais** `docker compose down -v` : il **efface la base**.

### 6.3 Première installation
```powershell
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py import_corpus
```
En production, le **deuxième facteur est obligatoire** pour l'administrateur et les opérateurs : à la première connexion, installe une application d'authentification (FreeOTP, Google Authenticator), scanne le QR code, saisis le code à 6 chiffres. Téléphone perdu : un administrateur réinitialise (*Utilisateurs → « Réinitialiser le deuxième facteur »*).
Ensuite, valide le corpus selon la Partie 4. `creer_demo` **ne fonctionne pas** en production (réservé au développement).

### 6.4 Sauvegardes et reprise
```powershell
.\scripts\sauvegarder.ps1                                       # une sauvegarde horodatée (à planifier toutes les 15 min)
docker compose exec web python manage.py verifier_audit
```
Reprise sur l'ordinateur de secours (< 15 min) : `docs\recette\installation-serveur-de-salle.md` §5.

### 6.3 bis — Tests dans Docker et simulation de charge (facultatif)
```powershell
.\scripts\tests-docker.ps1
docker compose exec web python manage.py simuler_charge --confirmer-base-jetable --url http://nginx   # base JETABLE seulement
```

---

## PARTIE 7 — Le jour J (résumé)
Tout est détaillé dans **`docs\exploitation\guide-operateur.md`** (listes de contrôle J-1 et jour J, conduite d'une prestation, procédures d'incident, clôture). Fiches : `docs\exploitation\fiche-memo-jure.md`, `fiche-conduite-prestation.md`. Répétition générale chronométrée : `docs\recette\repetition-generale.md`.

Ordre d'une mission : **import des candidats → admission → configuration validée par le client → ouvrir le concours et les épreuves → codes des jurés et fiches de secours → J-1 (sauvegarde, kit) → installation (≤ 45 min) → prestations → clôture → classement validé par le client → procès-verbal et export → audit → sauvegarde finale**.

---

## Dépannage rapide

| Symptôme | Cause probable et remède |
|---|---|
| `droit refusé pour créer une base de données` (pytest) | `ALTER USER quranova CREATEDB;` dans psql |
| `could not connect to server` | le service PostgreSQL n'est pas démarré, ou `DB_*` du `.env` est faux |
| `KeyError: 'DJANGO_SECRET_KEY'` | le `.env` est absent ou vide |
| Écrans tirage / scène / commande / jury **blancs** | `Set-Location frontend; npm install; npm run build` |
| `Activate.ps1` refusé | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `creer_demo` : « La démonstration existe déjà » | normal : elle n'est créée qu'une fois (pour repartir de zéro, supprime et recrée la base `quranova`) |
| « Bad Request (400) » en production | l'adresse saisie n'est pas dans `DJANGO_ALLOWED_HOSTS` |
| Compte verrouillé | 5 mauvais mots de passe : attendre 15 minutes |
| Lien PDF « indisponible » | installer Pango (MSYS2) : voir `DEMARRAGE.md` ; la version imprimable marche déjà |
| Tablette sans réponse en salle | pare-feu (port 80) ou profil réseau Wi-Fi non « Privé » |

---

## Où est quoi
| Besoin | Fichier |
|---|---|
| Démarrage détaillé Windows | `DEMARRAGE.md` |
| Serveur de salle (Docker) | `docs\recette\installation-serveur-de-salle.md` |
| Guide de l'opérateur, fiches mémo | `docs\exploitation\` |
| Validation du corpus (J0) | `docs\recette\validation-du-corpus.md` |
| Recette : REC, charge, accessibilité, sécurité | `docs\recette\` |
| Plan de la phase 4 (pilote) | `docs\recette\plan-phase-4.md` |
| Modèles pour les clients (CSV, consentement, contrat, ARTCI) | `docs\modeles\` |
| Tutoriel pas à pas | `docs\tutoriel\00-lisez-moi.md` |
| Décisions de conception | `docs\conception\modele-de-donnees.md` |
