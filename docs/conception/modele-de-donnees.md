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

## 6. Décisions complémentaires (étape 1.2, deuxième lot : concours et candidats)

| N° | Décision | Pourquoi |
|---|---|---|
| D13 | **Date de naissance inconnue : le consentement parental est exigé par prudence.** `est_mineur` renvoie « inconnu » (`None`), et `consentement_requis` le traite comme un mineur. | règle absolue n°6 : mieux vaut demander la date de naissance (ou le consentement) que laisser passer un mineur. Réversible en changeant une seule fonction. |
| D14 | **La validation de la configuration porte sur une configuration précise** : une empreinte SHA-256 des catégories, épreuves, barème et réglages de tirage est enregistrée à la validation, et comparée à l'ouverture. | RM-31 : si la configuration change après validation, le responsable client doit la valider de nouveau. |
| D15 | `affichage_scene` est **désactivé par défaut** sur une épreuve. | §9.1 : en mémorisation, l'écran scène ne doit pas être visible du candidat ; l'opérateur l'active volontairement. |
| D16 | **Un concours non brouillon exige, en base de données**, une version du corpus et une configuration validée. | RM-27 et RM-31 appliquées par une contrainte, pas seulement par du code. |
| D17 | **Numéro de candidat** : plus élevé du concours plus un, retraits compris, sous verrou sur le concours. Un numéro n'est jamais réutilisé. | évite deux inscriptions simultanées avec le même numéro, et toute ambiguïté sur les documents déjà imprimés. |
| D18 | **Consentement retiré = formulaire conservé et marqué « retiré »** ; un retrait partiel se fait en retirant le formulaire puis en en enregistrant un nouveau. Un seul formulaire valide par participation. | §16.2 : le retrait prend effet pour l'avenir et l'historique reste. |
| D19 | `Format` du concours : seul « présentiel » en V1. | en ligne et hybride sont en V2 (§5.2). |
| D20 | Le stockage **chiffré** des formulaires de consentement et des logos est repoussé à la sécurité du serveur de salle (§15). Le champ fichier existe déjà. | |

### Ce qui reste hors de ce lot

- `Jure` et `AffectationJury`, `CodeAccesJure` : lot suivant de l'itération 1 (avec l'import CSV des candidats).
- Le verrouillage des paramètres structurants quand le concours est « en cours » (§7.2), avec modification exceptionnelle motivée et tracée : à concevoir avec le journal d'audit.
- Les lots, séries et questions (itération 2), les tirages (itération 2), etc.
