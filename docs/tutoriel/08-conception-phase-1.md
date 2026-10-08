# Chapitre 8 — Concevoir le modèle de données (phase 1)

> **Étape du plan :** 1.1 · **Durée :** 1 à 2 heures de lecture et de décisions · **Résultat :** douze décisions de conception, consignées dans `docs\conception\modele-de-donnees.md`.

## Objectif

Avant d'écrire les modèles de la V1 (une trentaine), **figer le plan** : quelles tables, quelles relations, quelles règles dans la base ou dans le code. Cette étape ne demande **aucun code**.

## Méthode recommandée

1. **Dessinez d'abord votre propre schéma** sur papier, avant de relire le §14 du cahier des charges. Pensez aux grands blocs : *qui* (clients, utilisateurs, rôles), *quoi* (concours, catégories, épreuves, candidats), *le déroulement* (sessions, prestations, tirages), *le contenu* (questions, passages, séries, lots), *l'évaluation* (jurés, notes, résultats), *la traçabilité* (journal d'audit).
2. Comparez à `docs\cdc\14-modele-de-donnees-previsionnel.md` et aux règles RM-01 à RM-31 (`docs\cdc\19-regles-metier-detaillees.md`) : listez les manques, les erreurs, les risques.
3. Confrontez-vous aux **règles absolues** de `CLAUDE.md` : séparation des clients (n°3), validation des résultats (n°5), mineurs et consentement (n°6), note manquante différente de zéro (n°9).
4. Tranchez les décisions ci-dessous.

## Le document de référence

Voici le fichier à placer dans votre dépôt, `docs\conception\modele-de-donnees.md` :

**Fichier `docs\conception\modele-de-donnees.md`**

```markdown
# Modèle de données V1 — décisions de conception (phase 1)

Ce document fige le modèle de données de la V1. Il complète le §14 du cahier des charges
(`docs/cdc/14-modele-de-donnees-previsionnel.md`) et en précise les choix. Il est la référence
de l'étape 1.2 (« Modèles, application par application »).

## 1. Décisions confirmées

| N° | Décision | Conséquence |
|---|---|---|
| D1 | **Utilisateur Django personnalisé** dès maintenant (`AUTH_USER_MODEL = "utilisateurs.Utilisateur"`) | à faire avant toute table qui référence l'utilisateur ; la base de développement est recréée |
| D2 | **UUID comme clé primaire** de toutes les tables client | identifiants non devinables dans les URL (§13.4) |
| D3 | **`organisation` recopiée sur toutes les tables client**, avec test de cohérence parent-enfant | règle absolue n°3 ; classe abstraite `ModeleDuClient` |
| D4 | Jurés **hors comptes Django** : code de session haché, pas d'e-mail | §7.4 |
| D5 | Affectation d'un juré **toujours au niveau épreuve** | l'interface sait « affecter à tout le concours » en créant les lignes |
| D6 | Diapositives **stockées** à la préparation de l'affichage | l'état de présentation n'est qu'un pointeur ; reprise simple (§13.5) |
| D7 | Journal d'audit **simple** en V1, colonne d'empreinte chaînée prévue mais vide | autorisé par le §24 |
| D8 | Barème : **critères seulement** en V1 | pénalités et bonus si un règlement les exige |
| D9 | Départage : **règle de classement sur la catégorie** ; décision manuelle documentée plus tard | §10.4 |
| D10 | Une mission regroupe un ou plusieurs concours ; un concours appartient à une mission | |
| D11 | `Traduction` / `TraductionVerset` à l'itération 3 (diaporama) | |
| D12 | `Incident` rattaché au concours, et à la prestation si elle existe | |

## 2. Principes communs

- Toute table propre à un client : `organisation` non nulle, indexée, `on_delete=PROTECT`, filtrée par `.pour_organisation(...)`.
- Si une table a un parent client (par exemple une affectation et sa mission), l'`organisation` de l'enfant **doit** être celle du parent : elle est recopiée automatiquement et refusée si elle diffère.
- `cree_le` et `modifie_le` sur toutes les tables.
- Aucune suppression en cascade d'une donnée de concours : on archive.
- Ce qui se déduit d'une autre table n'est pas stocké : Q = T × P, disponibilité d'une série (déduite des tirages), classement provisoire (calculé), candidat mineur (déduit de la date de naissance).

## 3. Catalogue des modèles par application

| Application | Modèles | Itération du planning |
|---|---|---|
| `commun` | `ModeleHorodate`, `ModeleDuClient` (classes abstraites, gestionnaire filtré) | 1 |
| `clients` | `Organisation`, `Mission` | 1 |
| `utilisateurs` | `Utilisateur`, `AffectationOperateur`, `CodeAccesJure` | 1 |
| `concours` | `Concours`, `Categorie`, `Epreuve`, `CritereNotation`, `Session` | 1 |
| `candidats` | `Candidat`, `Participation`, `Consentement` | 1 |
| `jury` | `Jure`, `AffectationJury` (itération 1) ; `Evaluation`, `NoteCritere`, `CorrectionEvaluation` (itération 4) | 1 et 4 |
| `questions` | `PassageCoranique`, `Question`, `Lot`, `Serie`, `SerieQuestion` | 2 |
| `prestations` | `Prestation`, `Tirage`, `Incident` | 2 |
| `presentation` | `Diapositive`, `EtatPresentation`, `EvenementPresentation` | 3 |
| `resultats` | `Classement`, `LigneClassement`, `DocumentResultat` | 4 |
| `audit` | `JournalAudit` | 4 |
| `coran` | `VersionCorpus`, `Sourate`, `Verset` (fait) ; `Traduction`, `TraductionVerset` | 0 et 3 |

## 4. Ce que garantit la base de données et ce que garantit le code

| Règle | Où |
|---|---|
| Un seul tirage valide par `(prestation, rang)` ; une série n'est jamais tirée deux fois par un même candidat dans une épreuve ; identifiant de demande unique | base de données |
| Numéro de participation unique par concours ; une évaluation par juré et par prestation | base de données |
| Dates cohérentes (fin ≥ début), couleurs au format `#RRGGBB`, rôle et organisation cohérents | base de données |
| Réutilisation des séries (RM-21) | service, dans une transaction avec verrou sur le lot (règle absolue n°2) |
| Série de P questions exactement, suffisance du lot (RM-22, RM-24) | service, à l'ouverture de l'épreuve |
| Une note ne dépasse pas le maximum du critère | service (la règle croise deux tables) |
| Organisation de l'enfant = organisation du parent | modèle (`save()`), avec tests |

## 5. Points délicats à garder en tête

1. Une trentaine de modèles : l'ordre d'implémentation suit les itérations du planning.
2. `organisation` répétée : sûre, mais exige le test de cohérence parent-enfant.
3. RM-21 est la règle la plus délicate du projet (trois réglages combinables) : elle est écrite par l'utilisateur.
4. Les paramètres structurants sont verrouillés quand le concours est en cours (§7.2) : un mécanisme de modification exceptionnelle, motivée et tracée, reste à concevoir à l'itération 1.
```

## Questions de compréhension

1. La disponibilité d'une série est **calculée** à partir des tirages, et non stockée sur la série. Quel problème évite-t-on, et quel inconvénient cela introduit-il quand deux candidats tirent presque en même temps ?
2. Pourquoi recopier `organisation` sur **toutes** les tables client, plutôt que de la déduire en remontant les relations ?

<details>
<summary>Réponses</summary>

1. On évite deux sources de vérité qui se désynchronisent (la colonne « disponible » et les tirages). L'inconvénient : deux requêtes simultanées peuvent lire « disponible » en même temps et attribuer la même série. D'où la règle absolue n°2 : le tirage s'exécute dans une transaction avec `select_for_update` sur le lot (verrou), ce qui sérialise les tirages.
2. Pour qu'une requête puisse **toujours** filtrer par client en une seule condition, sans jointure, et pour qu'un oubli de jointure ne laisse pas passer les données d'un autre client (RM-20, règle n°3). Le prix : il faut vérifier que l'enfant et son parent ont la même organisation, ce que fait `ModeleDuClient` (chapitre 9).
</details>

## Journal d'apprentissage

Notez votre schéma de départ, ce que la comparaison avec le cahier des charges vous a fait corriger, et les décisions que vous auriez prises autrement.
