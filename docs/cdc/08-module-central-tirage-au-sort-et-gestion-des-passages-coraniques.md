# 8. Module central : tirage au sort et gestion des passages coraniques

Ce module représente la fonctionnalité distinctive de QURANOVA.

## 8.1. Modèle de tirage retenu

La version 1.0 décrivait deux modèles incompatibles (« le serveur choisit une série admissible » et « le candidat tire un lot de questions »). Le modèle unique retenu est le suivant :

1. pour chaque épreuve, l'opérateur prépare un **lot** composé de séries ; chaque **série** contient exactement P **questions** ;
2. le candidat **déclenche** le tirage par une action explicite ; il ne choisit ni la série ni son contenu ;
3. le **serveur** sélectionne aléatoirement une série parmi les séries disponibles du lot, à l'aide d'un générateur aléatoire cryptographiquement sûr ;
4. la série tirée est enregistrée avant toute communication du résultat ; elle est ensuite indisponible selon les règles de réutilisation (RM-21).

Une éventuelle animation sur l'écran de tirage (cartes qui se retournent, roue, etc.) est purement décorative : le résultat est déterminé et enregistré par le serveur avant le début de l'animation.

## 8.2. Articulation des paramètres quantitatifs

Les notions « nombre de questions par candidat » (§7.2), « nombre de passages par choix » (version 1.0), « nombre de tirages par candidat » et « nombre de passages par tirage » sont articulées comme suit, pour une épreuve donnée :

| Symbole | Paramètre | Saisie | Définition |
|---|---|---|---|
| P | Questions par série | Saisi | Nombre de questions contenues dans chaque série du lot ; équivaut au nombre de passages coraniques attribués par tirage (ex-« nombre de passages par choix »). |
| T | Tirages par candidat | Saisi | Nombre de tirages successifs effectués par chaque candidat pour l'épreuve (valeur par défaut : 1). |
| Q | Questions par candidat | Calculé | Q = T × P. |
| S | Séries dans le lot | Constaté | Nombre de séries effectivement préparées dans le lot. |
| N | Candidats de l'épreuve | Constaté | Nombre de participations admises à l'épreuve. |

```text
Épreuve
 └── Lot  (S séries)
      └── Série  (exactement P questions)
           └── Question = Passage coranique  (n versets)
                └── Diapositive(s)  (1 verset ou 1 segment de verset)

Participation ──► T tirages ──► T séries ──► Q = T × P questions

Exemple : P = 3, T = 1  →  chaque candidat reçoit 1 série de 3 passages
          P = 2, T = 2  →  chaque candidat reçoit 2 séries, soit 4 passages
```

**Contrôle de suffisance du lot.** Avant l'ouverture de l'épreuve, le système vérifie que le lot permet de servir tous les tirages prévus compte tenu des règles de réutilisation (RM-24) :

- si une série tirée est exclue pour tous les candidats (réglage par défaut) : S ≥ N × T ;
- si une série peut être réattribuée à d'autres candidats : S ≥ T (un candidat ne reçoit jamais deux fois la même série dans une épreuve).

Si la condition n'est pas remplie, l'ouverture de l'épreuve est bloquée et le système indique le nombre de séries manquantes.

## 8.3. Cycle d'un tirage et d'une prestation

Le déroulement d'une prestation suit le cycle ci-dessous. Chaque transition est horodatée, enregistrée par le serveur et diffusée aux écrans autorisés.

```text
[1] PRÉPARATION        Opérateur   : lot complet, jurés affectés, candidat appelé
        │               État : EN_ATTENTE
        ▼
[2] TIRAGE             Candidat : clic « Effectuer mon tirage »
        │               Serveur : contrôles + sélection aléatoire
        ▼
[3] VALIDATION         Serveur : enregistrement transactionnel du tirage
        │               puis diffusion du résultat (« Série 4 »)
        │               État : TIRÉ
        ▼
[4] AFFICHAGE          Opérateur   : « Démarrer la prestation »
        │               Diapositive par diapositive, sur commande manuelle
        │               État : EN_AFFICHAGE  (⇄ EN_PAUSE)
        ▼
[5] NOTATION           Jurés : saisie possible dès l'état EN_AFFICHAGE,
        │               validation après « Terminer la prestation »
        │               État : EN_NOTATION
        ▼
[6] CLÔTURE            Opérateur   : clôture lorsque toutes les évaluations
                        requises sont validées
                        État : CLÔTURÉE   (incident possible : ANNULÉE)
```

**Étape 1 — Préparation**

- l'opérateur compose le lot de l'épreuve : séries et questions (passages coraniques définis selon §8.4) ;
- il fixe P et T (cf. §8.2), le mode d'affichage (arabe seul ou arabe avec traduction) et les règles de réutilisation ;
- le texte des versets provient exclusivement du corpus de référence décrit en §12.

**Étape 2 — Tirage du candidat**

Le candidat clique pour déclencher le tirage autorisé (cf. §8.5).

**Étape 3 — Validation du tirage**

La série est attribuée, enregistrée par le serveur, puis communiquée aux écrans autorisés.

**Étape 4 — Affichage des versets**

Les écrans autorisés reçoivent la série et affichent ses questions dans l'ordre, diapositive par diapositive. Un clic de l'opérateur fait avancer l'affichage vers la diapositive suivante jusqu'à la fin de la série. Des **diapositives intercalaires** marquent les transitions : « Question 1/3 — Sourate 2, versets 142 à 150 » avant chaque question, « Fin de la question » après chaque question et « Fin de la série » à la fin.

**Étape 5 — Notation**

Les jurés saisissent leurs notes dans leur interface dédiée (cf. §10).

**Étape 6 — Clôture**

L'opérateur termine la prestation et autorise la validation des résultats.

## 8.4. Définition des questions par références coraniques

L'opérateur ne devra pas être obligé de saisir manuellement le texte des versets. Pour créer une question de type passage coranique, il renseignera uniquement :

- la sourate de début ;
- le numéro du verset de début ;
- la sourate de fin ;
- le numéro du verset de fin.

Exemple :

| Sourate de début | Verset de début | Sourate de fin | Verset de fin | Passage coranique enregistré |
|---|---|---|---|---|
| Sourate 2 | 142 | Sourate 2 | 150 | Sourate 2, versets 142 à 150 inclus, soit 9 versets. |

Le système devra ensuite :

1. vérifier que les références existent dans la version du corpus du concours ;
2. vérifier la cohérence du début et de la fin (la fin ne précède pas le début dans l'ordre canonique) ;
3. récupérer le texte arabe depuis le corpus de référence validé (cf. §12) ;
4. récupérer la traduction française validée, si le mode d'affichage l'exige ;
5. enregistrer la question dans la banque de questions de l'organisation ;
6. permettre de l'intégrer à une ou plusieurs séries selon les règles du concours.

Pour un passage coranique traversant plusieurs sourates, le système devra suivre l'ordre canonique des sourates et des versets.

> **Règle de référence :** les textes arabes, les numéros de sourates, les numéros de versets et les éventuelles marques de récitation devront provenir du corpus de référence validé avant mise en production (cf. §12). L'interface ne devra jamais reconstruire le texte coranique par simple concaténation de données non vérifiées.

## 8.5. Fonctionnement du tirage au sort

L'écran de tirage affichera une action explicite, par exemple : « Effectuer mon tirage ». Pour les concours en présentiel, les candidats viennent à tour de rôle, selon l'ordre de passage, cliquer sur le même écran de tirage.

Lorsque le candidat clique :

1. le système vérifie que le concours est en cours, que la prestation est à l'état EN_ATTENTE et que le candidat appelé est bien celui de la prestation ;
2. il vérifie que le nombre de tirages effectués pour cette prestation est inférieur à T ;
3. il vérifie que le consentement parental est validé si le candidat est mineur (RM-28) ;
4. le serveur sélectionne aléatoirement une série disponible du lot, selon RM-21 ;
5. le tirage est enregistré dans une transaction verrouillant le lot ; toute requête répétée portant le même identifiant de demande renvoie le tirage déjà enregistré ;
6. le résultat est affiché, par exemple : « Série 1 » ;
7. le résultat est transmis aux écrans autorisés.

L'écran du candidat ne reçoit jamais le texte des versets : il reçoit uniquement le libellé de la série et, si l'opérateur l'active, la référence de début de chaque question. Cette restriction est appliquée côté serveur sur le contenu des messages envoyés.

**Règle de réutilisation des séries (RM-21)**

> **RM-21 — Réutilisation des séries tirées.** Les trois paramètres suivants sont définis par l'opérateur pour chaque épreuve, avant son ouverture, puis verrouillés :

| Paramètre | Question tranchée | Valeurs | Défaut |
|---|---|---|---|
| RM-21.a — Réattribution à un autre candidat | Une série déjà tirée peut-elle être attribuée à un autre candidat de la même épreuve ? | Oui / Non | Non |
| RM-21.b — Réattribution au même candidat dans une autre épreuve | Lorsqu'un même lot est partagé entre plusieurs épreuves, une série tirée par un candidat peut-elle lui être de nouveau attribuée dans une autre épreuve ? | Oui / Non | Non |
| RM-21.c — Exclusion définitive | Une série tirée doit-elle être exclue de tous les tirages suivants du concours ? | Déduite : Oui si RM-21.a = Non et RM-21.b = Non | Oui |

- quelle que soit la configuration, un candidat ne reçoit jamais deux fois la même série au sein d'une même épreuve ;
- la configuration par défaut (Non, Non, exclusion définitive) correspond à la règle retenue dans la version 1.0 ;
- en cas d'épuisement du lot, le tirage est bloqué et un message invite l'opérateur à compléter le lot ; tout ajout de série en cours d'épreuve est journalisé ;
- un tirage annulé (incident technique, erreur d'appel) n'est jamais supprimé : il passe à l'état ANNULÉ avec motif et auteur. La série concernée est réintégrée au lot uniquement si aucune de ses diapositives n'a été affichée ; sinon, elle demeure exclue.

## 8.6. Limitation de l'écran du candidat

Conformément à la demande, le candidat disposera d'une interface volontairement limitée.

Il pourra :

- pour un concours en ligne (V2) :
  - s'identifier ou être identifié par l'opérateur ;
  - consulter les informations utiles à sa prestation ;
  - cliquer pour effectuer son tirage au sort ;
  - recevoir une confirmation que le tirage a été enregistré ;
- pour un concours en présentiel :
  - utiliser uniquement l'écran dédié au tirage, sans authentification individuelle ; l'identité du candidat est fixée par l'opérateur au moment de l'appel.

Il ne pourra pas :

- sélectionner librement une série ou une question ;
- consulter la banque complète des questions ;
- modifier son tirage ;
- accéder aux notes des jurés ;
- commander le défilement des diapositives ;
- consulter les interfaces de gestion ou de classement non publiques.

Le candidat ne verra pas le diaporama des versets destiné aux autres utilisateurs pendant sa prestation.
