# Prompts de travail par phase

Comment utiliser ce fichier :
- copiez un prompt dans Claude Code, une étape à la fois ;
- faites `/clear` entre deux grandes étapes (CLAUDE.md et le cahier des charges restent sur disque) ;
- passez en **plan mode** (Maj+Tab) pour les prompts marqués 🧭 ;
- après chaque étape, utilisez un ou deux « prompts de compréhension » (en bas de page), puis remplissez `docs/journal-apprentissage.md`.

---

## Phase 0 — Cadrage et corpus (S1–S2)

**0.1 🧭 Structure du dépôt**
> Lis CLAUDE.md et docs/cdc/13-architecture-technique.md. Je développe sous Windows en PowerShell, sans Docker pour l'instant. Propose la structure du dépôt (projet Django `config`, applications, dossier `frontend/`, `data/`, `docker/` qui servira en phase 3) et la configuration de développement : environnement virtuel, PostgreSQL local, Channels avec `InMemoryChannelLayer`. Explique le rôle de chaque élément. N'écris pas encore de code.

**0.2 Squelette Django**
> Crée le projet Django selon le plan validé : réglages séparés (`base`, `dev`), configuration par variables d'environnement avec un `.env.example`, connexion PostgreSQL, pytest-django configuré, et un test « smoke » qui vérifie que la page d'accueil répond. Explique-moi le cheminement d'une requête HTTP dans Django sur cet exemple.

**0.3 🧭 Modèles du corpus**
> J'ai placé le fichier Tanzil dans data/corpus/ (voir data/corpus/LISEZMOI.md). Lis docs/cdc/12-corpus-coranique-de-reference.md et la partie corpus de §14. Propose les modèles de l'application `coran` (VersionCorpus, Sourate, Verset, Traduction) et les contraintes d'intégrité. Explique pourquoi une version validée doit être immuable.

**0.4 Commande d'import**
> Écris la commande `import_corpus` : lecture du XML Tanzil sans aucune transformation du texte, calcul et enregistrement de l'empreinte SHA-256, création d'une VersionCorpus au statut « importée ». Laisse-moi écrire les contrôles automatiques de §12.2 (114 sourates, 6 236 versets, nombre de versets par sourate conforme aux métadonnées) en TODO(human).

**0.5 Tests du corpus**
> Écris les tests REC-30, REC-31 et REC-32 (§21) puis la fonction de service `resoudre_passage(debut, fin, version)` qui renvoie la liste ordonnée des versets ou lève une erreur explicite. Laisse-moi écrire la gestion de la traversée de sourates en TODO(human).

---

## Phase 1 — Conception (S3–S4)

**1.1 🧭 Critique de mon modèle de données**
> Voici mon schéma de données dessiné sur papier : [décrivez vos tables, champs et relations, ou joignez une photo]. Compare-le à docs/cdc/14-modele-de-donnees-previsionnel.md et aux règles RM-01 à RM-31. Liste les manques, les erreurs et les risques, sans corriger à ma place : pose-moi des questions.

**1.2 Modèles, application par application**
> Crée les modèles de l'application `clients` (Organisation, Mission) avec `organisation_id` là où c'est nécessaire, les migrations et des tests. Explique chaque champ et chaque contrainte. Puis on passera à `concours`.

**1.3 🧭 Protocole temps réel**
> Lis §9 et §13.5. Propose le format JSON de l'état de présentation (instantané versionné) et des commandes (identifiant unique, version attendue). Donne trois exemples de messages et le scénario d'une reconnexion. Pas de code.

**1.4 Maquettes**
> Propose des maquettes HTML statiques (Tailwind) des quatre écrans temps réel : tirage, commande, jury, scène. Grandes cibles tactiles, texte arabe `lang="ar" dir="rtl"`. Juste du HTML pour valider l'ergonomie.

---

## Phase 2 — Itération 1 : clients, concours, candidats, jurés (S5–S6)

**2.1** 🧭
> Lis §7.1 à §7.4 et §6. Propose le plan des écrans de gestion (gabarits Django + HTMX) et des permissions par rôle. Explique-moi comment HTMX remplace un morceau de page sans JavaScript personnalisé.

**2.2**
> Implémente la création et la modification d'un concours, de ses catégories et de ses épreuves, avec les tests de permission (un opérateur non affecté à la mission ne voit rien, cf. REC-29).

**2.3**
> Implémente l'import CSV/Excel des candidats (§7.3, REC-37) : aperçu, rapport d'erreurs ligne par ligne, aucune donnée invalide enregistrée. Laisse-moi écrire les règles de validation d'une ligne en TODO(human).

**2.4**
> Implémente les jurés, leurs affectations et la génération de codes d'accès limités à une session (§7.4, §15.1).

---

## Phase 2 — Itération 2 : passages, séries, lots, tirage (S7–S8)

**3.1** 🧭
> Lis §8 en entier et RM-21 à RM-28. Propose le plan : modèles Serie/Lot/Tirage, fonctions de service, tests. Explique pourquoi le tirage doit être dans une transaction avec `select_for_update`.

**3.2**
> Écris d'abord les tests : RM-21 (trois paramètres), RM-24 (suffisance du lot), RM-25 (annulation), RM-28 (mineur sans consentement), REC-06 et REC-07 (double clic). Ils doivent échouer pour l'instant.

**3.3**
> Écris la fonction `effectuer_tirage(prestation, id_demande)` : contrôles, verrouillage, sélection, enregistrement, idempotence. Laisse-moi écrire la sélection des séries admissibles selon RM-21 en TODO(human).

**3.4**
> Crée l'écran de tirage en Vue 3 (bouton unique, confirmation, animation décorative déclenchée après la réponse du serveur). Explique la structure d'un composant Vue et d'un store Pinia.

---

## Phase 2 — Itération 3 : diaporama synchronisé (S9–S10) — chemin critique

**4.1** 🧭
> Relis le protocole validé en 1.3, puis §9 et §13.5. Explique-moi Django Channels : consumer, groupe, couche de canaux (InMemory en développement, Redis en production) et pourquoi la différence compte. Propose le plan du consumer de présentation.

**4.2**
> Implémente le consumer : authentification et permission à la connexion, envoi de l'instantané, commandes idempotentes avec contrôle de version (RM-30). Tests : REC-24 (deux commandes simultanées). Laisse-moi écrire la fonction de transition d'état en TODO(human).

**4.3**
> Implémente l'écran de commande et l'écran scène en Vue : balayage de droite à gauche, texte arabe RTL, reconnexion automatique avec délais croissants, reconstruction depuis l'instantané (REC-15, REC-21, REC-23).

**4.4**
> Segmentation des versets longs (§9.2, REC-33) : écris d'abord le test « la concaténation des segments est identique au texte du corpus », puis laisse-moi écrire l'algorithme de découpage en TODO(human).

---

## Phase 2 — Itération 4 : notation, résultats, documents (S11–S12)

**5.1**
> Écran jury en Vue : grille de critères, brouillon conservé côté serveur, validation, suivi du verset courant (§10). Tests REC-11 et REC-12.

**5.2**
> Calcul des résultats (§10.3, §10.4) : écris d'abord les tests avec un exemple calculé à la main (je te donne les chiffres), puis laisse-moi écrire le calcul et le départage en TODO(human).

**5.3**
> Validation du classement par le responsable client (RM-18, REC-39), puis génération du procès-verbal PDF avec WeasyPrint (§11, REC-42).

**5.4**
> Journal d'audit en ajout seul avec empreinte chaînée (§15.2) et script de sauvegarde PostgreSQL toutes les 15 minutes vers un disque externe (§15.5). Teste une restauration (REC-18).

---

## Phase 3 — Autorecette et kit (S13–S14)

**6.1**
> Lis §21. Fais-moi un tableau de l'état de chaque test REC : automatisé, manuel ou manquant. Propose les tests automatisés manquants.

**6.0 Empaquetage du serveur de salle**
> Installe-moi pas à pas Docker Desktop sous Windows (backend WSL 2), puis crée le `docker-compose.yml` du serveur de salle : PostgreSQL, Redis, Django (Daphne), Nginx. Bascule Channels sur Redis. Explique chaque service et vérifie que tous les tests passent dans les conteneurs.

**6.2**
> Écris un script de simulation de charge (Locust ou script asyncio) pour REC-19 et REC-20 : 500 candidats, 30 terminaux connectés. Explique comment lire les résultats.

**6.3**
> Rédige avec moi le guide de l'opérateur (§22.1, §13.6) et les listes de contrôle J-1 et jour J.

---

## Prompts de compréhension (à utiliser après chaque étape)

- « Explique ce fichier ligne par ligne, comme à un étudiant qui connaît Python mais pas cette bibliothèque. »
- « Trace le chemin complet d'un clic sur "Diapositive suivante" jusqu'à l'écran scène. »
- « Qu'est-ce qui casserait si on retirait cette ligne ? Montre-le avec un test. »
- « Quelle alternative existait ? Pourquoi l'as-tu écartée ? »
- « Pose-moi 5 questions pour vérifier que j'ai compris ce module, puis corrige mes réponses. »
- « Je vais modifier X moi-même sans ton aide. Donne-moi seulement un indice si je bloque. »

## Prompts de débogage

- « Voici l'erreur complète : [coller]. Avant de corriger, explique la cause probable et comment la vérifier. »
- « Ce test échoue. Ne modifie pas le test : trouve pourquoi le code ne respecte pas la règle. »
