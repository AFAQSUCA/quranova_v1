# Répétition générale et installation du kit (REC-40, REC-41, REC-21, REC-36)

Objectif : un concours fictif de **20 candidats** avec de **vrais jurés**, sur le **vrai matériel**, installation comprise.
Critère de réussite : déroulement complet **sans anomalie bloquante** ; **installation en moins de 45 minutes** (§22).

## 1. Avant le jour (J − 7)
- [ ] Matériel : portable serveur + secours, onduleur, routeur Wi-Fi dédié (sans Internet), tablettes de tirage, tablettes des jurés, écran/projecteur de scène, câbles, rallonges, clé USB de secours (`.env`, derniers `.dump`).
- [ ] Sur les **deux** portables : Docker Desktop installé, projet cloné, `.env` rempli, images construites (`.\scripts\demarrer.ps1` avec Internet une fois) — voir `docs/recette/installation-serveur-de-salle.md`.
- [ ] Corpus **validé par le référent coranique** (jalon J0) : `import_corpus` puis validation. Sans cela, aucun concours réel.
- [ ] Données du concours fictif saisies (client, concours, catégories, épreuve, barème, 20 candidats, séries composées de vrais passages) ; jurés créés et affectés.
- [ ] `python manage.py check --deploy` (réglages de production) et `.\scripts\tests-docker.ps1` verts.

## 2. Installation chronométrée (cible : 45 minutes)
Un chronomètre, une personne qui note l'heure de chaque étape. Écart > 20 % sur une étape : la noter comme point d'amélioration.

| # | Étape | Cible | Début | Fin |
|---|---|---|---|---|
| 1 | Déballer, brancher le portable sur l'onduleur, l'onduleur sur le secteur | 5 min | | |
| 2 | Allumer le routeur Wi-Fi dédié, contrôler l'IP fixe du serveur | 5 min | | |
| 3 | Démarrer Docker Desktop puis `.\scripts\demarrer.ps1` ; contrôler les adresses affichées | 8 min | | |
| 4 | Connecter les tablettes de tirage (adresse + jeton), appeler un candidat d'essai, tirer | 8 min | | |
| 5 | Connecter l'écran de scène (jeton) ; connecter les tablettes des jurés (codes) | 8 min | | |
| 6 | **Test de synchronisation de tous les écrans** : préparer, démarrer, 5 × « suivante », « précédente » ; tous les écrans identiques | 6 min | | |
| 7 | Lancer la sauvegarde planifiée (`.\scripts\sauvegarder.ps1` toutes les 15 min) et vérifier qu'un `.dump` apparaît | 5 min | | |
| | **Total** | **≤ 45 min** | | |

## 3. Déroulement du concours fictif
- [ ] 20 candidats tirent leur série (dont un mineur sans consentement : tirage **refusé**, REC-38 ; un double clic : un seul tirage, REC-07).
- [ ] Chaque prestation : préparation, diaporama complet, jurés notent (une note laissée vide : évaluation **incomplète**, jamais zéro, REC-12), validation des évaluations.
- [ ] Une correction de note validée par un juré, approuvée par le responsable client (REC-17).
- [ ] Clôture de l'épreuve par l'opérateur ; classement provisoire contrôlé par un **calcul manuel indépendant** sur trois candidats (REC-13) ; validation par le **responsable client** uniquement (REC-39).
- [ ] Procès-verbal généré (seuls les résultats validés), export CSV ouvert dans le tableur, `verifier_audit` sans anomalie (REC-16).

## 4. Pannes provoquées (à chaud, pendant une prestation)
| Test | Geste | Attendu | Résultat |
|---|---|---|---|
| REC-21 | Couper le Wi-Fi 30 s | Tous les écrans retrouvent l'état courant en < 2 s après rétablissement, aucune commande perdue ni dupliquée | |
| REC-23 | Redémarrer l'écran de scène et une tablette de juré à la 5e diapositive | 5e diapositive en < 2 s ; brouillon de notes conservé | |
| REC-41 | Débrancher le secteur (onduleur) | Aucune interruption ; autonomie notée | |
| REC-36 | Éteindre brutalement le serveur, basculer sur le secours (guide §5) | Reprise en < 15 min, dernière sauvegarde restaurée, `verifier_audit` propre | |
| REC-18 | Restaurer une sauvegarde sur une base vierge | Données cohérentes et exploitables | |

## 5. Bilan
- Durée d'installation réelle : ______ min ; anomalies bloquantes : ______ ; non bloquantes (à corriger avant la V1) : ______
- Décision : ☐ prêt pour le concours pilote ☐ corrections puis nouvelle répétition
- Signatures : opérateur ______ référent coranique ______ responsable client ______
