# Tutoriel QURANOVA — réaliser le projet pas à pas

Ce tutoriel vous permet de **construire QURANOVA du début à la fin**, sous Windows, dans PowerShell, en suivant les chapitres dans l'ordre. Il est écrit **au fur et à mesure** du projet : un nouveau chapitre est ajouté à chaque étape terminée.

## Comment l'utiliser

1. Faites les chapitres **dans l'ordre**. Chacun part de l'état laissé par le précédent.
2. Dans chaque chapitre, les fichiers sont donnés **en entier**, tels qu'ils sont dans le dépôt à ce moment-là. Vous pouvez les taper (pour comprendre chaque ligne) ou les copier.
3. Une règle d'or du projet : **les tests d'abord**. Quand un chapitre vous dit de lancer `pytest` avant d'avoir écrit le code, l'échec est **voulu** : il prouve que le test vérifie bien quelque chose.
4. À la fin de chaque chapitre : vérifiez le résultat attendu, faites le commit proposé, répondez aux questions de compréhension, remplissez votre journal (`docs\journal-apprentissage.md`).

## Les blocs « Solution »

Quelques règles métier sont à **écrire par vous** (`TODO(human)`) : c'est la partie du projet où vous apprenez le plus. Chaque chapitre concerné contient un bloc replié :

> **Solution (n'ouvrez qu'après avoir essayé)**

Essayez d'abord seul, en vous aidant des tests. Si vous manquez de temps, la solution est là et elle fait passer tous les tests.

## Conventions

| Notation | Signification |
|---|---|
| `apps\coran\models.py` | un chemin du projet, avec des `\` comme sous Windows |
| bloc ```` ```powershell ```` | une commande à taper dans PowerShell, à la racine du projet, venv activé |
| bloc ```` ```python ```` | le contenu d'un fichier, ou une partie de fichier |
| « attendu » | ce que vous devez voir ; si ce n'est pas le cas, ne continuez pas |

## Avancement

| Chapitre | Contenu | Étape du plan |
|---|---|---|
| [01](01-installation-windows.md) | Installer les outils, PostgreSQL, cloner le dépôt | 0.1 |
| [02](02-squelette-django.md) | Projet Django, réglages, `.env`, premier test | 0.2 |
| [03](03-modeles-du-corpus.md) | `VersionCorpus`, `Sourate`, `Verset` et leurs contraintes | 0.3 |
| [04](04-garde-d-immuabilite.md) | Une version validée ne change plus | 0.3 |
| [05](05-administration-lecture-seule.md) | Administration du corpus en lecture seule | 0.3 |
| [06](06-import-du-corpus.md) | Télécharger Tanzil et importer le corpus | 0.4 |
| [07](07-passages-coraniques.md) | Résoudre un passage en versets (REC-04, 31, 32) | 0.5 |
| [08](08-conception-phase-1.md) | Décisions de conception du modèle de données | 1.1 |
| [09](09-socle-clients-utilisateurs.md) | Classes de base, clients, utilisateurs et rôles | 1.2 |
| [10](10-concours-et-candidats.md) | Concours, catégories, épreuves, barème ; candidats, participations, consentements | 1.2 |
| [11](11-jures-et-import-csv.md) | Jurés, codes d'accès de session, import CSV des candidats | 1.2 |
| [12](12-questions-lots-series.md) | Questions, passages coraniques, lots et séries | 3.1-3.2 |
| [13](13-prestations-et-tirage.md) | Prestations, tirage, ouverture d'épreuve, annulation | 3.2-3.3 |
| [14](14-administration.md) | L'administration : voir et manipuler les données | console |
| [15](15-ecran-de-tirage.md) | L'écran de tirage : Vue 3, Pinia, API à jeton | 3.4 |
| [16](16-protocole-et-diapositives.md) | Protocole temps réel, segmentation, plan des diapositives | 1.3, 3a |
| [17](17-etat-et-commandes.md) | État de présentation, commandes versionnées, transitions | 3b |
| [18](18-consumer-websocket.md) | Le consumer WebSocket (Channels) | 3c |
| [19](19-ecrans-scene-et-commande.md) | Écrans de scène et de commande (Vue) | 3d |
| [20](20-journal-d-audit.md) | Le journal d'audit chaîné | 4a |
| [21](21-evaluations-et-acces-jury.md) | Évaluations des jurés, connexion par code, API de notation | 4b, 4c |
| [22](22-ecran-du-jure.md) | L'écran du juré en Vue | 4d |
| [23](23-resultats-et-classement.md) | Résultats, classement et validation par le responsable client | 4e, 4f |
| [24](24-documents-et-sauvegarde.md) | Procès-verbal, exports, sauvegarde et restauration | 4g, 4h |
| [25](25-identite-visuelle.md) | Identité visuelle : logo, charte, marque du client | 6 (phase 3) |
| [26](26-reglages-de-production-et-redis.md) | Réglages de production et Redis (channels-redis) | 6.0a (phase 3) |
| [27](27-docker-compose.md) | Docker Compose : PostgreSQL, Redis, Daphne, Nginx | 6.0b (phase 3) |
| [28](28-simulation-de-charge.md) | Simulation de charge (REC-19, REC-20) | 6.2 (phase 3) |
| [29](29-accessibilite-et-repetition-generale.md) | Accessibilité (WCAG 2.1 AA) et répétition générale | 6.3 (phase 3) |
| [30](30-duplication-de-concours.md) | Duplication d'un concours (REC-02) | 4 (post-phase 3) |
| [31](31-pdf-weasyprint.md) | Procès-verbal et classements en PDF (WeasyPrint) | 4 (post-phase 3) |
| [32](32-analyse-de-securite.md) | Analyse de sécurité automatisée (bandit, pip-audit, npm audit) | REC-28 |
| [33](33-securite-des-comptes.md) | Sécurité des comptes : mots de passe, limitation des essais, deuxième facteur | A1–A3 (phase 4) |

## Si vous êtes bloqué

- Comparez votre fichier à celui du dépôt : `git diff --no-index votre-fichier.py autre-fichier.py`, ou ouvrez le fichier sur GitHub, branche `claude/confident-goodall-7iqyck`.
- Chaque chapitre indique le **commit de référence** : `git show <commit>:chemin\du\fichier` affiche le fichier exact.
- Un test qui échoue **dit pourquoi** : lisez le message en entier, de bas en haut.
- Dernier recours : demandez de l'aide en collant la sortie complète de `pytest` (jamais un mot de passe).

## Vue d'ensemble de la route

```text
Phase 0  Cadrage et corpus       chapitres 01 à 07   (S1-S2)
Phase 1  Conception              chapitres 08 à ...  (S3-S4) ; la phase 2 (itération 1) commence au chapitre 9
Phase 2  Développement V1        4 itérations : clients/concours, tirage, diaporama, notation
Phase 3  Autorecette et kit      tests de recette, Docker
Phase 4  Concours pilote
Phase 5  Corrections et lancement
Phase 6  V2
```

Le planning complet est dans `docs\cdc\24-planning-et-phasage.md`.
