# QURANOVA — Instructions pour Claude Code

## Le projet

QURANOVA est l'outil interne d'un prestataire qui gère des concours coraniques pour le compte de clients
(associations, écoles coraniques, mosquées). Le jour du concours, un ordinateur portable (le « serveur de salle »)
fait tourner l'application sur un Wi-Fi dédié, sans Internet ; tablettes de tirage, tablettes des jurés et écran scène s'y connectent.

- Cahier des charges : `docs/cdc/00-index.md` (une section par fichier). **Avant toute tâche, lis la ou les sections concernées.**
- Planning et itérations : `docs/cdc/24-planning-et-phasage.md` ; prompts de travail : `docs/prompts-iterations.md`.
- Tutoriel pas à pas : `docs/tutoriel/` (un chapitre par étape terminée). **Claude : à la fin de chaque étape, ajoute ou met à jour le chapitre correspondant** (fichiers complets, commandes PowerShell, résultat attendu, solutions des `TODO(human)` en blocs repliés).
- Phase en cours : **Phase 1 — Conception** (mettre à jour cette ligne à chaque changement de phase).
  Reste de la phase 0 à clôturer : règles `TODO(human)` de `apps/coran/services.py` (garde d'immuabilité, contrôles du §12.2, traversée de sourates) et jalon J0 (validation du corpus par le référent coranique).

## Qui je suis et comment travailler avec moi

Je suis le développeur unique du projet et je veux **comprendre chaque ligne** du code. Je connais Python et les bases de Django ;
je découvre Django Channels, HTMX et Vue 3.

1. **Plan avant le code.** Pour toute tâche non triviale, propose d'abord un plan (fichiers, modèles, fonctions, tests) et attends mon accord.
2. **Petites étapes.** Une étape = un modèle, une fonction ou une vue, avec ses tests. Jamais un module entier d'un coup.
3. **Explique le pourquoi**, pas seulement le quoi : alternatives écartées, pièges, lien avec la règle du cahier des charges (RM-xx, REC-xx).
4. **Laisse-moi écrire la logique métier** (`TODO(human)`) : sélection du tirage et RM-21, contrôle de suffisance des lots,
   segmentation des versets longs, protocole d'état du diaporama, calcul des notes et classements, contrôles du corpus.
5. **Tests d'abord pour les règles métier.** Nomme les tests d'après la règle : `test_rm21_serie_exclue_apres_tirage`, `test_rec31_verset_invalide`.
6. **Pas de nouvelle dépendance** sans me demander et m'expliquer pourquoi.
7. **Ne fais pas les commits toi-même** : propose un message de commit, je relis le diff et je commite.
8. Termine une étape en me posant **une question de compréhension** sur ce qui vient d'être fait.
9. Réponds en **français**. Commentaires et docstrings en français.

## Environnement de développement

- **Windows 10/11 natif, terminal PowerShell.** Donne toujours les commandes en PowerShell et des chemins Windows ;
  n'utilise pas de syntaxe Linux (`export`, `source`, `/` dans les chemins de commandes Windows, etc.).
- Python dans un environnement virtuel `.venv` ; PostgreSQL installé localement sur Windows.
- **Pas de Docker ni de Redis pendant le développement** (phases 0 à 2) : Channels utilise `InMemoryChannelLayer` en développement.
  Redis et Docker Compose sont introduits en phase 3 pour empaqueter le serveur de salle (Docker Desktop).
- WeasyPrint sous Windows nécessite les bibliothèques Pango (via MSYS2) ; voir DEMARRAGE.md.
- Évite les dépendances qui ne fonctionnent pas sous Windows ; si une bibliothèque pose problème sous Windows, dis-le avant de l'utiliser.

## Stack (cf. §13)

- Python 3.12+, Django 5.2 LTS, Django Channels (WebSocket), PostgreSQL 16+ ; Redis en production (serveur de salle)
- Écrans de gestion : gabarits Django + HTMX + Tailwind CSS
- Écrans temps réel (tirage, commande, jury, scène) : Vue 3 + TypeScript + Pinia, construits avec Vite, servis en statique par Django
- PDF : WeasyPrint · Tests : pytest + pytest-django · Déploiement du serveur de salle (phase 3) : Docker Compose (Nginx + Daphne + Redis + PostgreSQL)

## Organisation du code

Applications Django prévues (§13.8) : `clients`, `utilisateurs`, `concours`, `candidats`, `questions`, `coran`,
`prestations`, `presentation`, `jury`, `resultats`, `audit` (puis `synchro` en V2). Front temps réel dans `frontend/`.
Les applications vivent dans le dossier `apps/` (ex. `apps.coran`, label `coran`) ; chaque application est créée au moment où on en a besoin.

- La logique métier va dans des **fonctions de service** (`services.py`), pas dans les vues ni les templates.
- Les vues restent fines : permissions → appel du service → réponse.

## Vocabulaire (glossaire §2) → noms dans le code

Les noms du domaine sont en **français sans accents** ; le code purement technique peut être en anglais.

| Terme du CDC | Modèle / nom de code |
|---|---|
| Organisation (client) | `Organisation` |
| Mission | `Mission` |
| Concours / Édition | `Concours` (champ `edition`) |
| Catégorie / Épreuve / Session | `Categorie` / `Epreuve` / `Session` |
| Prestation (passage d'un candidat) | `Prestation` |
| Candidat / Participation | `Candidat` / `Participation` |
| Juré | `Jure` (+ `AffectationJury`) |
| Question / Passage coranique | `Question` / `PassageCoranique` |
| Série / Lot / Tirage | `Serie` / `Lot` / `Tirage` |
| Version du corpus / Sourate / Verset | `VersionCorpus` / `Sourate` / `Verset` |
| Responsable client / Opérateur | rôles `responsable_client` / `operateur` |

N'utilise **jamais** « passage » seul (dis `PassageCoranique` ou `Prestation`), ni « choix » pour une série.

## Règles absolues (ne jamais enfreindre)

1. **Texte coranique** : il provient uniquement du fichier Tanzil importé (`data/corpus/`). Ne génère, ne tape, ne corrige,
   ne normalise jamais un verset. Aucune normalisation Unicode à l'import (§12.2).
2. **Tirage** : côté serveur, module `secrets`, dans une transaction avec `select_for_update` sur le lot ;
   idempotent via un identifiant de demande (§8.5, RM-07, RM-21, RM-25, RM-28).
3. **Séparation des clients** : toute table propre à un client a une clé étrangère `organisation` (colonne `organisation_id`, appelée `organization_id` dans le CDC) ; toute requête est filtrée par client (§13.4, RM-20).
4. **Permissions côté serveur** pour chaque vue **et** chaque message WebSocket. Masquer un bouton ne protège rien.
5. **Validation des résultats** : seul le responsable client valide le classement définitif, jamais l'opérateur (RM-18).
6. **Mineurs** : aucun tirage sans consentement parental enregistré (RM-28).
7. **Diaporama** : l'état est détenu par le serveur et versionné ; chaque commande porte un identifiant unique
   et la version attendue (RM-30). L'écran candidat ne reçoit jamais le texte des versets (RM-14).
8. **Secrets** : jamais dans le code ni dans Git ; tout passe par `.env` (non versionné).
9. **Note manquante ≠ zéro** (RM-16).

## Commandes

À compléter au fur et à mesure (Claude : mets à jour cette section quand une commande est créée).

```powershell
.venv\Scripts\Activate.ps1                         # activer l'environnement Python
pip install -r requirements\dev.txt                # installer les dépendances de développement
python manage.py check                             # vérifier la configuration
python manage.py migrate                           # appliquer les migrations (PostgreSQL)
python manage.py runserver                         # lancer le serveur de développement (ASGI via daphne)
pytest                                             # lancer les tests
python manage.py import_corpus                     # importe data\corpus\quran-uthmani.xml et quran-data.xml (version « importée »)
python manage.py import_corpus --dry-run           # lit et contrôle, puis annule sans rien enregistrer
python manage.py importer_candidats <uuid-concours> fichier.csv [--dry-run]   # importe des candidats (tout ou rien)
```

## Définition de « terminé » pour une étape

- Les tests de l'étape passent, ainsi que tous les tests existants.
- Je sais expliquer le code avec mes mots (je l'écris dans `docs/journal-apprentissage.md`).
- Le diff est relu et commité avec un message clair.
