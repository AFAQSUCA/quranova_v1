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
| D21 | L'import CSV des candidats est **tout ou rien** : toutes les lignes sont contrôlées avant toute écriture, le rapport liste **toutes** les erreurs (avec le numéro de ligne du fichier), et une option de simulation (`--dry-run`) donne le même rapport sans rien enregistrer. CSV uniquement (UTF-8 ou Windows-1252, séparateur `;`, `,` ou tabulation) ; Excel `.xlsx` exigerait une dépendance (`openpyxl`) à valider d'abord. | |
| D22 | Doublon de candidat = même nom et prénom (casse ignorée) et même date de naissance, **dans le même client uniquement** (RM-20). Un candidat existant est réutilisé ; la même personne dans deux catégories donne un seul `Candidat` et deux `Participation` ; la même personne deux fois dans la même catégorie est une erreur. | |
| D23 | `CodeAccesJure` vit dans l'application `jury` (pas `utilisateurs`) pour éviter une dépendance circulaire. Le code (8 caractères, alphabet sans `0 O 1 I`, tiré avec `secrets`) n'est jamais stocké : seule son empreinte HMAC-SHA256 (clé `SECRET_KEY`) l'est. Un seul code actif par juré et par session ; en régénérer un révoque l'ancien. La limitation des tentatives se fera dans les vues. | |
| D24 | Un lot par épreuve en V1 (`Lot.epreuve` est un `OneToOneField`). Le partage d'un lot entre épreuves (RM-21.b) est repoussé ; le paramètre est stocké mais sans effet tant qu'aucun lot n'est partagé. | |
| D25 | Un tirage n'est possible que si le concours est « en cours » et l'épreuve « ouverte » (§8.5, point 1). *(à implémenter avec `effectuer_tirage`)* | |
| D26 | L'annulation d'un tirage exige un motif, un auteur et une date (contrainte en base) ; elle est réservée au personnel du prestataire. Le tirage n'est jamais supprimé (ni par `delete()`, ni remplacé). **Correction par rapport au plan** : le drapeau `diapositive_affichee` est porté par le **tirage** (pas par la prestation), car une prestation peut avoir T tirages et seul celui dont la série a été affichée reste exclu (RM-25). Le diaporama (itération 3) le renseignera. | |
| D27 | Un tirage annulé dont une diapositive a été affichée compte comme un tirage valide pour l'exclusion (RM-21) : la série reste exclue pour ce candidat, et pour les autres selon RM-21.a. Sans diapositive affichée, il est ignoré (série réintégrée). *À confirmer : le CDC §8.5 dit « demeure exclue ».* | |
| D28 | Le tirage ne démarre qu'avec un `id_demande` unique ; une demande annulée n'est pas rejouable. Le tirage T>1 laisse la prestation « en attente » jusqu'au T-ième tirage. | |
| D29 | **Console provisoire** : en attendant les vrais écrans de gestion, l'administration Django sert aux trois rôles. L'accès dépend du **rôle** (administrateur et opérateur écrivent, responsable client consulte et valide la configuration), pas des permissions Django par modèle ; `is_staff` est fixé à vrai à la création d'un compte. Chaque liste et chaque menu déroulant est filtré par client (RM-20). *Limite connue : le cloisonnement est au niveau du client, pas encore de la mission.* | |
| D30 | Dans l'administration, les états (concours, épreuve, prestation) et les tirages ne s'écrivent pas à la main : ils passent par les services (actions « Ouvrir », « Démarrer », « Valider la configuration »). Une participation se crée par `inscrire` (numéro attribué sous verrou), une série par `composer_serie`. | |
| D31 | Un terminal de tirage s'authentifie par un **jeton secret** (256 bits, `secrets`) envoyé dans l'en-tête `Authorization: Bearer` ; seule son empreinte HMAC est stockée ; il est révocable et propre à une session. Sans cookie, donc sans CSRF. Le jeton est transmis à la tablette dans le **fragment** de l'adresse (`/tirage/#jeton`), qui n'est jamais envoyé au serveur ni écrit dans ses journaux. | |
| D32 | La tablette interroge `GET /api/tirage/etat/` toutes les 2 secondes (pas de WebSocket pour l'instant). Le WebSocket arrive avec le diaporama (itération 3). | |
| D33 | L'écran de tirage n'affiche pas les références de début des questions (option du §8.5, repoussée). | |
| D34 | La tablette affiche le **numéro et le prénom** du candidat appelé, jamais son nom de famille (écran visible de la salle, parfois pour des mineurs, §16), et jamais le texte d'un verset (RM-14). Le client n'envoie que `id_demande` : la prestation est celle appelée par l'opérateur (REC-25). | |
| D35 | **Dépendances du front** (validées par l'utilisateur) : `vue`, `pinia` (imposés par §13) ; en développement `vite`, `@vitejs/plugin-vue`, `typescript`, `vue-tsc`, `vitest`, `@vue/test-utils`, `jsdom`. **TypeScript est volontairement fixé en 5.9** (`~5.9`) : la version 7, plus récente, n'est pas encore compatible avec `vue-tsc`. Le build écrit dans `static/frontend/` avec des noms fixes (`tirage.js`, `tirage.css`) ; ce dossier n'est pas versionné. Node.js 22 ou plus est requis. | |
| D36 à D41 | Voir `docs/conception/protocole-temps-reel.md` (§8) : `pytest-asyncio`, `Terminal` généralisé (tirage / scène), jeton de la scène par premier message, plan de diapositives figé à « Préparer l'affichage », jury à l'itération 4, une présentation active par session. | |
| D42 | La taille d'une diapositive (nombre maximal de caractères d'un segment de verset) est pour l'instant une **constante** (`TAILLE_SEGMENT_PAR_DEFAUT` = 180). Elle deviendra un réglage de l'épreuve (§9.2 : « taille de texte configurée »), ce qui fera partie de la configuration validée par le client (empreinte, D14). | |
| D43 | Une évaluation par couple (juré, prestation), portant sur toutes les séries tirées par la prestation. Pour REC-11 (« le bon tirage »), le lien se fait par la prestation ; la validation enregistre aussi le libellé des séries évaluées. *(itération 4, étape 4b)* | |
| D44 | Le juré reçoit le **texte des versets** sur sa tablette, comme l'opérateur (§9.1) ; ce rôle est vérifié côté serveur. *(étape 4c)* | |
| D45 | Le journal d'audit est protégé par un **déclencheur PostgreSQL** (UPDATE et DELETE refusés, même en SQL direct) en plus du contrôle des empreintes. Pas de déclencheur TRUNCATE (Django vide les tables de test ainsi) : la disparition d'entrées est détectée par la tête de chaîne. Une chaîne par client (RM-20) et une chaîne « système ». | |
| D46 | Le jeton de connexion d'un juré a la durée de validité de son code de session. *(étape 4c)* | |

### Ce qui reste hors de ce lot

- `Jure` et `AffectationJury`, `CodeAccesJure` : lot suivant de l'itération 1 (avec l'import CSV des candidats).
- Le verrouillage des paramètres structurants quand le concours est « en cours » (§7.2), avec modification exceptionnelle motivée et tracée : à concevoir avec le journal d'audit.
- Les lots, séries et questions (itération 2), les tirages (itération 2), etc.

| D49 | Identité visuelle : charte vert/or tirée du logo ; sur les écrans publics le **client** est en avant (logo, couleur) et QURANOVA discret (sceau) ; l'écran de tirage n'a pas de marque client (terminal sans session). |

| D50 | Production : `config/settings/prod.py` refuse de démarrer sans clé secrète solide (≥ 50 car., hors modèle) ni `DJANGO_ALLOWED_HOSTS` explicite (jamais `*`) ; couche de canaux Redis (`channels-redis`, dépendance validée) ; pas de redirection HTTPS (Wi-Fi local sans Internet) sauf `DJANGO_HTTPS=1`. |

| D51 | Empaquetage : Docker Compose (db, redis, web/Daphne, nginx) ; front compilé dans l'image (pas de Node en production) ; Redis sans persistance ; `ALLOWED_HOSTS` = adresses du serveur ; images construites avec Internet puis utilisées hors ligne ; tests exécutables dans l'image (`--profile outils`). |

| D52 | Simulation de charge sans dépendance (client HTTP stdlib + client WebSocket maison) ; commande réservée aux bases jetables ; pool de connexions PostgreSQL prévu mais désactivé (`DB_POOL`) en attendant l'accord sur `psycopg_pool` ; le tirage reste sérialisé par le verrou de lot. |

| D53 | Pool de connexions PostgreSQL actif par défaut en production (`psycopg_pool`, accord du développeur) ; accessibilité : audit axe-core dans un vrai navigateur sans dépendance projet, scène conservant le balayage (§18.2), zone live sur la commande ; répétition générale chronométrée documentée (REC-40). |

| D54 | Duplication de concours : catégories, épreuves (remises en préparation), barèmes (critère prioritaire remappé) et séries ; questions recréées et passages revérifiés dans la version du corpus ; copie en brouillon, configuration à revalider (RM-31) ; sans candidats, sessions, tirages ni résultats ; sans version utilisable, séries à passages ignorées avec avertissement ; même client (RM-20) ; administrateur ou opérateur affecté ; tout ou rien et journalisée. |

| D55 | PDF : WeasyPrint (dépendance validée), même HTML que la version imprimable ; chercheur de ressources limité à `/static/` et `/media/` (aucun accès réseau ni fichier arbitraire) ; PDF indisponible → message et repli vers l'HTML (503), jamais d'erreur 500 ; deux PDF : procès-verbal et classements par catégorie (validés seulement), tous deux journalisés. |

| D56 | Sécurité : bandit, pip-audit et npm audit (outils de développement validés) lancés par `scripts/audit-securite.ps1` ; bandit aussi en garde-fou pytest ; XML corpus refusé avec DOCTYPE/ENTITY (sans `defusedxml`) ; nom de base de restauration validé et identifiants SQL quotés ; `pytest>=9.0.3`. |

| D57 | Comptes du personnel : mot de passe ≥ 12 caractères ; verrou de connexion 5 échecs/compte et 20/adresse sur 15 min, dans le backend ; adresse réelle via `X-Real-IP` derrière Nginx (`PROXY_DE_CONFIANCE`) ; TOTP (`django-otp`, `qrcode`, dépendances validées) obligatoire pour administrateur et opérateurs, contrôlé sur les pages, les API et le WebSocket ; coupé en développement seulement ; réinitialisation par un administrateur. |

| D58 | Validation du corpus : contrôles automatiques rejoués à l'enregistrement (dont l'aller-retour avec le fichier source retrouvé par empreinte) ; échantillon de relecture déterministe (CdC §12.2 point 5 + ≥ 1 % classé par SHA-256) ; procès-verbal HTML/PDF administrateur seulement ; `ValidationCorpus` écrite une fois ; une seule version active par riwāya (pas de bascule automatique) ; le rapport de différences pour une mise à jour de Tanzil reste à faire. |
