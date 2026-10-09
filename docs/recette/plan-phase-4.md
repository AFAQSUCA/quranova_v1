# Plan de la phase 4 — Concours pilote (S15–S16 : 11 – 22 janvier 2027, jalon J5)

Objectif : conduire un **concours réel** avec un client partenaire, mesurer (§18.1), consigner les incidents et décider des corrections (livrable L-09).
Avant cela, tout ce que le CdC place en **V1 / « avant le pilote »** et qui n'est pas encore fait doit l'être (écarts relevés dans le code au 9 octobre 2026).

## A. Écarts de sécurité des comptes (§15.1) — à fermer avant tout compte réel
| # | Écart constaté | Travail proposé | Dépendance |
|---|---|---|---|
| A1 ✅ | Mot de passe : 8 caractères minimum (défaut Django) ; le CdC exige **12** | `MinimumLengthValidator` à 12 ; tests | aucune |
| A2 ✅ | **Limitation des tentatives de connexion** absente pour les comptes du personnel (elle existe pour les codes de juré) ; désactivation immédiate d'un compte | compteur d'échecs par compte et par adresse, blocage temporaire, journalisé ; test | aucune (écrit sur le modèle de `jury/connexion.py`) |
| A3 ✅ | **Authentification à deux facteurs obligatoire** pour l'administrateur et les opérateurs : absente | TOTP (appli d'authentification, fonctionne hors ligne) : enrôlement, vérification à la connexion de l'administration, comptes sans 2FA refusés | **`django-otp`** (+ `qrcode` pour l'enrôlement) — à valider |

## B. Corpus : jalon J0 et livrable L-07
- B1 ✅ Action d'administration **« Valider cette version du corpus »** réservée à l'administrateur : enregistre le nom du référent coranique, la date et l'empreinte (aujourd'hui il n'existe que les champs du modèle ; la validation d'essai de `creer_demo` n'est qu'un raccourci de développement).
- B2 ✅ **Procès-verbal de validation du corpus** (PDF, WeasyPrint) : version, empreinte SHA-256, résultats des contrôles §12.2 (114 sourates, 6 236 versets, numérotation, versets non vides), espace de signature du référent. C'est le document à faire signer.

## C. Fonctions du pilote encore manquantes
- C1. **Journal des incidents** : saisie par l'opérateur (heure, type selon §13.6, description, durée, résolution) ; section 3 du procès-verbal complétée ; alimente le bilan L-09.
- C2. **Fiches de notation de secours** (§13.6, panne des deux ordinateurs) : impression la veille depuis l'application (une fiche par prestation et par juré, critères, barème) ; **saisie ultérieure avec motif** obligatoire, tracée.
- C3. *(optionnel)* **Correction d'un classement par l'administration** au lieu de la seule commande `corriger_classement`.
- C4. **Import Excel** : décision prise — **CSV seulement en V1** (écart au CdC §5.1 à acter), avec le modèle CSV fourni au client (D). Pas de dépendance `openpyxl`.

## D. Livrables « avant le concours pilote » (L-03, L-04, L-05)
| Livrable | Ce que je prépare | Ce qui reste à toi / au juridique |
|---|---|---|
| L-03 Guide de l'opérateur | procédure d'une mission (§22.1), listes J-1 et jour J, procédures d'incident (§13.6) | relecture sur le terrain |
| L-04 Fiches mémo | fiche d'une page « juré » et fiche de conduite d'une prestation « opérateur » (PDF A4) | essai avec de vrais jurés |
| L-05 Modèle d'import des candidats | fichier CSV modèle **généré à partir des colonnes réelles de l'importeur** et testé | — |
| L-05 Formulaire de consentement parental | **projet** de texte, aligné sur les champs de l'application | **relecture juridique obligatoire** |
| L-05 Contrat de mission et dossier ARTCI | **plan détaillé et clauses à couvrir** seulement | rédaction et validation par un juriste / déclaration ARTCI |

## E. Exploitation et matériel (hors code : à toi)
Kit complet (§22.2) · tablettes en mode kiosque · routeur de rechange préconfiguré (même SSID et mot de passe) · mot de passe Wi-Fi changé · tâche planifiée Windows des sauvegardes (non testée à ce jour) ·
mesure de REC-19/20 sur le portable de salle · répétition générale (`docs/recette/repetition-generale.md`) avec 3 jurés volontaires · installation chronométrée < 45 min · choix du client pilote et du lieu · deuxième opérateur en formation.

## F. Pendant le pilote
- **Gel du code** une semaine avant (étiquette Git `v1.0-pilote`) ; seuls des correctifs de blocage, un par un, avec test, après accord.
- **Mesures** (§18.1) relevées sur un gabarit : préparation d'un concours < 2 h, installation < 45 min, latences, nombre d'incidents, temps de reprise.
- **Sauvegarde** vérifiée avant, pendant (toutes les 15 min) et après ; `verifier_audit` à la clôture.
- **Clôture J à J+7** : validation du classement par le responsable client, procès-verbal signé, remise des documents et de l'export.

## G. Après le pilote
Bilan L-09 (déroulement, incidents, mesures, retours client et jurés) → liste des corrections → phase 5.

## Séquence proposée
1. **A1 → A2 → A3** (comptes) · 2. **B1 → B2** (corpus, signature du référent) · 3. **C1 → C2** (incidents, fiches de secours) · 4. **D** (guide, fiches, modèles) · 5. **C3 / C4** si le temps le permet · 6. gel `v1.0-pilote` · 7. répétition générale (E).
Chaque étape : tests d'abord, petite étape, chapitre du tutoriel, une question de compréhension.

## Décisions prises
2FA : `django-otp` + `qrcode` · Excel : CSV seulement en V1 · ordre : A1 d'abord (fait : A1, A2, A3).

## Décisions encore attendues
1. **2FA** : valider `django-otp` (+ `qrcode`) ?  2. **Excel** : ajouter `openpyxl` ou acter « CSV seulement » ?  3. **C3** : dans le pilote ou après ?  4. Ordre : commencer par A1 ?
