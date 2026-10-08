# Chapitre 16 — Le protocole temps réel et le plan des diapositives (itération 3, étapes 1.3 et 3a)

> **Commit de référence :** `c63d1dc` · **Durée :** 4 à 5 heures · **Résultat :** le document de protocole, l'application `presentation` (plan des diapositives, segmentation) et **55 tests**, dont une règle à écrire par vous : la **segmentation d'un verset**.

## Objectif

Avant de coder le diaporama synchronisé, on **fige le langage** que parleront le serveur et les écrans (étape 1.3), puis on construit **ce qui sera affiché** : la suite ordonnée des diapositives d'une prestation.

## Django Channels en cinq idées

| Notion | Rôle |
|---|---|
| **Consumer** | Une classe par connexion WebSocket. Elle reçoit les messages du navigateur et peut en envoyer. |
| **Groupe** | Un nom auquel les consumers s'abonnent. On diffuse **à un groupe**, chaque abonné reçoit. |
| **Couche de canaux** | Le « bus » qui fait circuler les messages entre consumers. |
| **`InMemoryChannelLayer`** | Le bus vit dans la mémoire d'**un seul processus** : parfait en développement, inutilisable avec plusieurs processus, vidé au redémarrage. |
| **Redis** | Le même bus, partagé entre processus (serveur de salle, phase 3). |

**Pourquoi la différence compte :** rien ne doit dépendre du bus. La vérité est en base, l'état est versionné, et un message perdu se rattrape par un instantané. Le bus accélère ; il ne garantit rien.

## Étape A — Le protocole

Ce document est la référence des chapitres 17 à 19. Lisez-le en entier : c'est lui qui définit l'instantané versionné, les commandes (identifiant unique, version attendue — RM-30), les trois exemples et le scénario de reconnexion.

**Fichier `docs\conception\protocole-temps-reel.md`**

````markdown
# Protocole temps réel de la présentation (étape 1.3 — §9, §13.5, RM-30)

Ce document fixe **le format des messages** échangés par WebSocket entre le serveur et les écrans de
**commande** (opérateur) et de **scène**. Il est écrit AVANT le code (consumer, store Vue) : les deux côtés
le suivent à la lettre. Le jury s'y raccordera à l'itération 4 (D40).

## 1. Principes

1. **Le serveur détient l'état** (base de données). Les écrans n'en sont que des reflets : ils ne calculent
   jamais une diapositive eux-mêmes (§13.5).
2. **Le bus WebSocket n'est jamais une garantie.** Un message diffusé peut se perdre (couche en mémoire en
   développement, coupure Wi-Fi). Chaque état porte donc une **version** strictement croissante ; un écran qui
   constate un trou redemande un **instantané** complet.
3. **Une commande est idempotente** : elle porte un `id` unique et la `version_attendue` (RM-30). Rejouée,
   elle n'est jamais appliquée deux fois.
4. **Le texte des versets n'est envoyé qu'aux écrans autorisés** (RM-14) : opérateur ; scène seulement si
   l'épreuve a `affichage_scene` (D15). Le terminal de tirage et l'écran candidat n'ouvrent jamais ce canal.
   La projection est faite **côté serveur** avant l'envoi.
5. **Une seule présentation active par session** (D41) : la connexion se fait sur la **session** ; l'état
   suivi est celui de `session.prestation_active`. Changer de prestation active = nouvel état, version
   repartant de 1.

## 2. Connexion et authentification

URL : `ws://<serveur>/ws/presentation/<uuid de la session>/`.

| Écran | Authentification | Rôle |
|---|---|---|
| Commande (opérateur) | cookie de session Django, **contrôle d'origine**, accès à la mission (RM-20) | `operateur` |
| Scène | **premier message** `{"type":"auth","jeton":"…"}` dans les 5 s (D38) ; jamais dans l'URL | `scene` |

Codes de fermeture : `4401` non authentifié ou jeton invalide · `4403` interdit (autre session, autre client) ·
`4408` délai d'authentification dépassé.

Dès l'authentification réussie, le serveur envoie l'**instantané** (§3).

## 3. Messages du serveur vers l'écran

### 3.1. `etat` — l'instantané versionné

```json
{
  "type": "etat",
  "instantane": true,
  "session": "7c9b…",
  "prestation": {
    "id": "bd6b…",
    "candidat": {"numero": 12, "prenom": "Awa"},
    "epreuve": "Mémorisation",
    "serie": "Série 4"
  },
  "version": 17,
  "phase": "affichage",
  "rejeu": 0,
  "diapositive": {
    "index": 5,
    "total": 23,
    "type": "verset",
    "question": {"rang": 2, "total": 3, "libelle": "Sourate 2, versets 142 à 150"},
    "reference": "2:144",
    "segment": {"rang": 1, "total": 2},
    "texte": "…"
  }
}
```

- `prestation` vaut `null` quand aucune présentation n'est active (l'écran affiche « en attente »).
- `phase` : `preparee` (série chargée, rien d'affiché) · `affichage` · `pause` · `terminee`.
- `diapositive` vaut `null` en phase `preparee`.
- `diapositive.type` : `intercalaire_question` (« Question 1/3 — Sourate 2, versets 142 à 150 ») · `verset` ·
  `fin_question` · `fin_serie`.
- `reference` et `segment` n'existent que pour un `verset` (« 2:282 — 1/3 »). La concaténation des
  `texte` des segments d'un verset est **identique** au texte du corpus (REC-33).
- `texte` est **absent** pour un écran non autorisé (scène avec `affichage_scene` faux). Les intercalaires
  n'ont jamais de texte coranique : ils ne contiennent que le libellé de la question.
- `rejeu` est un compteur : quand il augmente alors que `index` ne change pas, l'écran rejoue l'animation
  (« Réafficher la diapositive »).
- `instantane` est vrai pour une réponse à la connexion ou à une demande de `snapshot` : l'écran se
  **reconstruit sans animation**. Il est faux (ou absent) pour une diffusion après commande : l'écran anime
  la transition (balayage de droite à gauche).

### 3.2. `ack` — réponse à une commande (envoyée à l'émetteur seulement)

```json
{"type": "ack", "id": "5f1c…", "statut": "appliquee", "version": 18}
{"type": "ack", "id": "5f1c…", "statut": "deja_traitee", "version": 18}
{"type": "ack", "id": "9a2e…", "statut": "rejetee", "raison": "version_obsolete", "version": 18}
```

`raison` : `version_obsolete` · `transition_interdite` · `non_autorise` · `commande_inconnue`.
Un refus renvoie toujours la `version` courante : l'écran sait de quoi il est en retard.

### 3.3. `ecrans` — présence (envoyé à l'opérateur)

```json
{"type": "ecrans", "ecrans": [{"nom": "Scène 1", "type": "scene", "connecte": true}]}
```

Calculé depuis la dernière activité enregistrée en base (30 s) : correct même avec plusieurs processus.

### 3.4. `pong`

```json
{"type": "pong"}
```

## 4. Messages de l'écran vers le serveur

### 4.1. `commande`

```json
{"type": "commande", "id": "5f1c…", "version_attendue": 17, "action": "suivante"}
```

Actions : `preparer` · `demarrer` · `suivante` · `precedente` · `pause` · `reprendre` · `reafficher` · `terminer`.

- `preparer` ajoute `"prestation": "<uuid>"` (elle devient la prestation active de la session) et n'exige pas
  de `version_attendue`. Refusée tant qu'une présentation est en `affichage` ou `pause`.
- `precedente` est **journalisée** (§9.3).
- Seul l'opérateur envoie des commandes (REC-14) : le serveur refuse (`non_autorise`) toute commande d'un
  écran de scène, **message par message** (règle absolue n°4).

### 4.2. `auth`, `snapshot`, `ping`

```json
{"type": "auth", "jeton": "…"}
{"type": "snapshot"}
{"type": "ping"}
```

`ping` toutes les **15 s** ; sans `pong` pendant **30 s**, l'écran considère la connexion perdue.

## 5. Règles côté écran

| Message reçu | Action |
|---|---|
| `etat`, même prestation, `version` = locale + 1 | appliquer, avec animation si `instantane` est faux |
| `etat`, même prestation, `version` ≤ locale | ignorer (message en retard ou doublon) |
| `etat`, même prestation, `version` > locale + 1 | **trou** : envoyer `snapshot`, ne rien appliquer |
| `etat`, autre prestation ou `instantane` vrai | remplacer l'état, **sans animation** |
| `ack` `rejetee` + `version_obsolete` | afficher la version courante, ne pas renvoyer automatiquement |

## 6. Trois exemples

**a) L'opérateur passe à la diapositive suivante.**

```text
opérateur → {"type":"commande","id":"5f1c…","version_attendue":17,"action":"suivante"}
serveur   → opérateur : {"type":"ack","id":"5f1c…","statut":"appliquee","version":18}
serveur   → opérateur, scène : {"type":"etat","version":18,"phase":"affichage","diapositive":{"index":6,…}}
```

**b) Double clic (REC-24) : deux « suivante » avec la même version.**

```text
opérateur → {…"id":"A","version_attendue":17,"action":"suivante"}
opérateur → {…"id":"B","version_attendue":17,"action":"suivante"}
serveur   → ack A : appliquee (version 18)
serveur   → ack B : rejetee, version_obsolete (version 18)       ← une seule diapositive franchie
```

**c) Message perdu, puis trou de version.**

```text
scène a la version 18. Elle reçoit la version 20 (la 19 s'est perdue).
scène → {"type":"snapshot"}
serveur → {"type":"etat","instantane":true,"version":20,…}      ← sans animation
```

## 7. Scénario de reconnexion (REC-15, REC-21, REC-23)

1. Le Wi-Fi coupe 30 s en pleine présentation, à la diapositive 5 de la scène.
2. L'écran de scène n'a plus de `pong` depuis 30 s : il affiche un bandeau « connexion perdue » mais
   **conserve** la diapositive 5 (mieux vaut une diapositive figée qu'un écran vide).
3. Il retente la connexion avec les délais 0,5 s → 1 s → 2 s → 5 s (puis toutes les 5 s).
4. Wi-Fi rétabli : connexion, message `auth`, puis l'instantané `etat` (version courante, `instantane: true`).
5. L'écran **remplace** son état sans rejouer les diapositives manquées : il affiche directement la
   diapositive courante (objectif : moins de 2 s).
6. Côté opérateur, une commande envoyée pendant la coupure est **renvoyée avec le même `id`** : si le serveur
   l'avait déjà appliquée, il répond `deja_traitee` ; sinon il la traite (ou la rejette si la version a changé).
   Aucune commande n'est perdue ni dupliquée.

## 8. Décisions

| N° | Décision |
|---|---|
| D36 | `pytest-asyncio` (dev) pour tester le consumer. |
| D37 | `Terminal` devient `Terminal` avec un type `tirage` ou `scene`. |
| D38 | Le jeton de la scène passe par le premier message, jamais par l'URL. |
| D39 | Le plan des diapositives est calculé à « Préparer l'affichage » puis figé ; il ne contient que des références. |
| D40 | Le jury se raccorde à l'itération 4. |
| D41 | Une seule présentation active par session ; la connexion se fait sur la session. |
````

## Étape B — L'application et les dossiers

```powershell
New-Item -ItemType Directory "apps\presentation\tests" -Force | Out-Null
New-Item -ItemType File "apps\presentation\__init__.py", "apps\presentation\tests\__init__.py" -Force | Out-Null
```

Dans `config\settings\base.py`, ajoutez `"apps.presentation",` à `INSTALLED_APPS` (après `apps.prestations`).

**Fichier `apps\presentation\apps.py`**

```python
from django.apps import AppConfig


class PresentationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.presentation"
    label = "presentation"
    verbose_name = "Présentation"
```

**Fichier `apps\presentation\exceptions.py`**

```python
"""Erreurs de l'application presentation."""


class PlanImpossibleError(Exception):
    """Le plan des diapositives ne peut pas être construit (prestation sans tirage valide, etc.)."""


class TransitionInterditeError(Exception):
    """L'action demandée n'est pas permise dans l'état courant (§9.3)."""
```

## Étape C — La segmentation : les tests d'abord, puis **votre** algorithme (§9.2, REC-33)

Un verset trop long pour la taille de texte configurée est découpé en plusieurs diapositives. **Règle absolue n°1** : le texte n'est jamais modifié ; la concaténation des segments doit être **strictement identique** au texte du corpus, et on ne coupe qu'**entre deux mots**.

**Fichier `apps\presentation\tests\test_segmentation.py`**

```python
"""Tests de la segmentation d'un verset (§9.2, REC-33) — algorithme à écrire par vous.

Les textes de test sont NEUTRES (jamais un verset, règle n°1) : des mots inventés, et des suites de lettres
arabes avec signes diacritiques pour vérifier que les caractères Unicode ne sont ni normalisés ni cassés.
"""
import pytest

from apps.presentation.segmentation import segmenter_verset

MOTS_ARABES = ["ابتَ", "ثجحْ", "خدذُ", "رزسِ"]


def texte_neutre(n_mots, mot="mot"):
    return " ".join(f"{mot}{i}" for i in range(n_mots))


def texte_arabe(n_mots):
    return " ".join(MOTS_ARABES[i % 4] + MOTS_ARABES[(i + 1) % 4] for i in range(n_mots))


@pytest.mark.parametrize("texte", [texte_neutre(1), texte_neutre(40), texte_arabe(25), "a b c d e f g"])
@pytest.mark.parametrize("taille", [1, 5, 12, 30, 80, 500])
def test_rec33_la_concatenation_des_segments_est_identique_au_texte(texte, taille):
    assert "".join(segmenter_verset(texte, taille)) == texte


@pytest.mark.parametrize("texte", [texte_neutre(40), texte_arabe(25)])
@pytest.mark.parametrize("taille", [10, 30, 80])
def test_on_ne_coupe_jamais_a_l_interieur_d_un_mot(texte, taille):
    segments = segmenter_verset(texte, taille)

    mots_d_origine = texte.split()
    mots_des_segments = [mot for segment in segments for mot in segment.split()]
    assert mots_des_segments == mots_d_origine
    for segment in segments:
        assert not segment[0].isspace()  # un segment commence par un mot
    for segment in segments[:-1]:
        assert segment[-1] == " "  # l'espace de séparation reste à la fin du segment qui précède


@pytest.mark.parametrize("taille", [10, 30, 80])
def test_un_segment_ne_depasse_pas_la_taille_maximale(taille):
    for segment in segmenter_verset(texte_neutre(60), taille):
        assert len(segment) <= taille


def test_un_mot_plus_long_que_la_taille_n_est_pas_coupe():
    segments = segmenter_verset("court immensementlong fin", 8)

    assert segments == ["court ", "immensementlong ", "fin"]


def test_un_texte_court_donne_un_seul_segment():
    assert segmenter_verset("deux mots", 100) == ["deux mots"]


def test_exemple_simple_avec_l_espace_a_la_fin_du_segment():
    assert segmenter_verset("aaaa bbbb", 5) == ["aaaa ", "bbbb"]


def test_aucun_segment_vide():
    for segment in segmenter_verset(texte_neutre(30), 15):
        assert segment != ""


def test_les_caracteres_unicode_ne_sont_pas_normalises():
    texte = texte_arabe(10)

    assert "".join(segmenter_verset(texte, 12)) == texte
    assert all(c in texte for c in "".join(segmenter_verset(texte, 12)))


def test_le_resultat_est_deterministe():
    assert segmenter_verset(texte_neutre(50), 20) == segmenter_verset(texte_neutre(50), 20)


@pytest.mark.parametrize("taille", [0, -3])
def test_une_taille_invalide_est_refusee(taille):
    with pytest.raises(ValueError):
        segmenter_verset("texte", taille)
```

Voici le fichier tel qu'il est dans le dépôt, avec la fonction **à écrire par vous** :

**Fichier `apps\presentation\segmentation.py`**

```python
"""Découpage d'un verset trop long en plusieurs diapositives (§9.2, REC-33).

Règle absolue n°1 : le texte n'est JAMAIS modifié. Découper, c'est choisir où couper ; ce n'est ni
reformater, ni supprimer une espace, ni normaliser un caractère.
"""


def segmenter_verset(texte, taille_max):
    """Découpe ``texte`` en segments d'au plus ``taille_max`` caractères, en coupant ENTRE DEUX MOTS.

    TODO(human) : écrivez l'algorithme de découpage. Contrat (voir ``test_segmentation.py``) :
    - la concaténation des segments est STRICTEMENT identique à ``texte`` (aucun caractère perdu,
      ajouté, réordonné ni dupliqué) ;
    - on ne coupe jamais à l'intérieur d'un mot ; l'espace qui sépare deux mots reste à la FIN du
      segment qui précède (un segment commence donc toujours par un mot) ;
    - un segment ne dépasse pas ``taille_max`` caractères (espace finale comprise), SAUF s'il ne contient
      qu'un seul mot plus long que ``taille_max`` : on ne coupe pas un mot ;
    - un texte qui tient en une diapositive donne une liste d'un seul segment ;
    - aucun segment vide ; ``taille_max`` inférieur à 1 lève ``ValueError``.
    Indice : parcourez les mots (``re.findall(r"\\S+\\s*", texte)`` en garde les espaces de fin) et
    remplissez le segment courant tant que le mot suivant y tient.
    """
    raise NotImplementedError("TODO(human) : segmentation d'un verset (voir la docstring)")
```

```powershell
pytest apps\presentation\tests\test_segmentation.py
```

Attendu avant d'écrire la fonction : `41 failed`. Après : `41 passed`.

**Indice :** `re.findall(r"\S+\s*", texte)` découpe le texte en « mots » qui gardent leurs espaces de fin ; recoller les mots redonne exactement le texte. Remplissez ensuite un segment tant que le mot suivant y tient.

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
# Dans apps/presentation/segmentation.py, ajoutez « import re » en haut du fichier, puis remplacez le corps de la fonction par :

def segmenter_verset(texte, taille_max):
    """Découpe ``texte`` en segments d'au plus ``taille_max`` caractères, en coupant ENTRE DEUX MOTS."""
    if taille_max < 1:
        raise ValueError("La taille maximale d'un segment doit être d'au moins 1 caractère.")
    # Chaque « mot » garde ses espaces de fin : en les recollant, on retrouve exactement le texte.
    mots = re.findall(r"\S+\s*", texte)
    segments, courant = [], ""
    for mot in mots:
        if courant and len(courant) + len(mot) > taille_max:
            segments.append(courant)
            courant = ""
        courant += mot
    if courant:
        segments.append(courant)
    return segments
```

</details>

## Étape D — Le plan des diapositives

Le plan ne contient que des **références** (identifiant du verset, bornes du segment dans son texte) : le texte est relu dans le corpus quand on l'envoie (D39). Une version du corpus figée (RM-27) garantit alors que l'affichage est celui du corpus validé.

Ajoutez au fichier de fabriques `apps\prestations\tests\outils.py` le paramètre `version=None` de `creer_epreuve_ouverte` (il permet de donner un corpus à l'épreuve) :

**Fichier `apps\prestations\tests\outils.py`**

```python
"""Fabriques de test pour les prestations et les tirages."""
import itertools
import uuid
from datetime import date

from django.utils import timezone

from apps.candidats.models import Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_epreuve,
    creer_mission,
    creer_participation,
    creer_session,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours.models import Concours, Epreuve
from apps.prestations.models import Prestation, Tirage
from apps.questions import services as services_questions
from apps.questions.tests.outils import creer_question
from apps.utilisateurs.models import Utilisateur

_rangs = itertools.count(1)


def creer_epreuve_ouverte(series=4, p=1, version=None, **champs):
    """Une épreuve OUVERTE d'un concours EN COURS, avec un lot de ``series`` séries de ``p`` questions."""
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)
    concours = creer_concours(
        creer_mission(responsable.organisation),
        etat=Concours.Etat.EN_COURS,
        version_corpus=version or creer_version_validee(),
        configuration_validee_par=responsable,
        configuration_validee_le=timezone.now(),
        configuration_empreinte="a" * 64,
    )
    champs.setdefault("etat", Epreuve.Etat.OUVERTE)
    epreuve = creer_epreuve(creer_categorie(concours), questions_par_serie=p, **champs)
    ajouter_series(epreuve, series)
    return epreuve


def ajouter_series(epreuve, nombre):
    """Ajoute ``nombre`` séries complètes au lot de l'épreuve ; renvoie la liste des séries créées."""
    lot = services_questions.obtenir_lot(epreuve)
    return [
        services_questions.composer_serie(
            lot, [creer_question(epreuve.organisation) for _ in range(epreuve.questions_par_serie)]
        )
        for _ in range(nombre)
    ]


def creer_prestation(epreuve, participation=None, session=None, **champs):
    """Une prestation EN_ATTENTE pour un candidat ADMIS, majeur (donc sans exigence de consentement)."""
    participation = participation or creer_participation(
        epreuve.categorie,
        creer_candidat(epreuve.organisation, date_naissance=date(1990, 1, 1)),
        statut=Participation.Statut.ADMIS,
    )
    valeurs = {
        "participation": participation,
        "epreuve": epreuve,
        "session": session or creer_session(epreuve.categorie.concours),
        "rang_passage": next(_rangs),
    }
    valeurs.update(champs)
    return Prestation.objects.create(**valeurs)


def creer_tirage(prestation, serie, **champs):
    valeurs = {"prestation": prestation, "serie": serie, "rang": 1, "id_demande": uuid.uuid4()}
    valeurs.update(champs)
    return Tirage.objects.create(**valeurs)


def creer_terminal_de_test(epreuve, nom="Tablette 1"):
    """Un terminal de tirage pour la session du concours de l'épreuve ; renvoie (terminal, jeton, session)."""
    from apps.prestations import terminaux

    session = creer_session(epreuve.categorie.concours)
    terminal, jeton = terminaux.creer_terminal(session, nom)
    return terminal, jeton, session
```

**Fichier `apps\presentation\tests\outils.py`**

```python
"""Fabriques de test pour la présentation : un corpus minimal et une prestation tirée."""
import uuid

from django.utils import timezone

from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_verset, creer_version
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage
from apps.questions import services as services_questions

# Textes NEUTRES : jamais un verset (règle absolue n°1).
def texte_du_verset(sourate, verset):
    return " ".join(f"s{sourate}v{verset}m{i}" for i in range(1, 9))


def creer_corpus_de_test(sourates=((1, 7), (2, 20))):
    """Une version avec des sourates et des versets au texte neutre ; validée APRÈS l'écriture (RM-27)."""
    version = creer_version()
    for numero, nombre in sourates:
        sourate = creer_sourate(version, numero=numero, nombre_versets=nombre, ordre_revelation=numero)
        for verset in range(1, nombre + 1):
            creer_verset(sourate, numero=verset, texte=texte_du_verset(numero, verset))
    version.statut = VersionCorpus.Statut.VALIDEE
    version.date_validation = timezone.now()
    version.save()
    return version


def creer_prestation_tiree(passages=(((2, 3), (2, 5)), ((1, 1), (1, 2))), series=1, tirages=1):
    """Une prestation à l'état TIRÉ ; chaque série est composée des ``passages`` donnés (P = len(passages)).

    Renvoie ``(prestation, epreuve, version)``.
    """
    version = creer_corpus_de_test()
    epreuve = creer_epreuve_ouverte(series=0, p=len(passages), version=version, tirages_par_candidat=tirages)
    lot = services_questions.obtenir_lot(epreuve)
    toutes = []
    for _ in range(max(series, tirages)):
        questions = [
            services_questions.creer_question_passage(epreuve.organisation, version, debut, fin)
            for debut, fin in passages
        ]
        toutes.append(services_questions.composer_serie(lot, questions))
    prestation = creer_prestation(epreuve)
    for rang in range(1, tirages + 1):
        creer_tirage(prestation, toutes[rang - 1], rang=rang, id_demande=uuid.uuid4())
    Prestation.objects.filter(pk=prestation.pk).update(etat=Prestation.Etat.TIRE)
    prestation.refresh_from_db()
    return prestation, epreuve, version


def operateur_de(epreuve):
    """Un opérateur affecté à la mission du concours de l'épreuve."""
    from apps.commun.tests.outils import creer_utilisateur
    from apps.utilisateurs.models import AffectationOperateur, Utilisateur

    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    return operateur


def commande(session, action, version=None, *, auteur, prestation=None, id_commande=None):
    """Envoie une commande au service avec un identifiant neuf (ou celui donné)."""
    from apps.presentation import services

    return services.appliquer_commande(
        session, id_commande or uuid.uuid4(), action, version, auteur=auteur, prestation=prestation
    )


def presentation_demarree(**options):
    """(prestation, session, operateur, état) avec la présentation préparée puis démarrée (version 2)."""
    prestation, epreuve, _ = creer_prestation_tiree(**options)
    operateur = operateur_de(epreuve)
    session = prestation.session
    commande(session, "preparer", auteur=operateur, prestation=prestation)
    resultat = commande(session, "demarrer", 1, auteur=operateur)
    return prestation, session, operateur, resultat.etat
```

**Fichier `apps\presentation\tests\test_diapositives.py`**

```python
"""Tests du plan des diapositives (§8.3 étape 4, §9.2, REC-33 ; D39).

Le plan ne contient que des RÉFÉRENCES (verset, bornes du segment) : le texte est relu dans le corpus.
"""
import uuid

import pytest
from django.utils import timezone

from apps.commun.tests.outils import creer_utilisateur
from apps.coran.models import Verset
from apps.prestations.models import Prestation, Tirage
from apps.presentation import diapositives
from apps.presentation.exceptions import PlanImpossibleError
from apps.presentation.tests.outils import creer_prestation_tiree, texte_du_verset
from apps.prestations.tests.outils import creer_prestation, creer_tirage
from apps.questions import services as services_questions

def un_seul_segment(texte, taille):
    return [texte]


def types(plan):
    return [d["type"] for d in plan]


@pytest.mark.django_db
def test_sequence_des_diapositives_d_une_serie():
    prestation, *_ = creer_prestation_tiree()  # 2 questions : 2:3-5 (3 versets) puis 1:1-2 (2 versets)

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    assert types(plan) == [
        "intercalaire_question", "verset", "verset", "verset", "fin_question",
        "intercalaire_question", "verset", "verset", "fin_question",
        "fin_serie",
    ]


@pytest.mark.django_db
def test_les_intercalaires_portent_le_rang_et_le_libelle_de_la_question():
    prestation, *_ = creer_prestation_tiree()

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    premiere, seconde = [d for d in plan if d["type"] == "intercalaire_question"]
    assert (premiere["question_rang"], premiere["question_total"]) == (1, 2)
    assert premiere["libelle"] == "Sourate 2, versets 3 à 5"
    assert (seconde["question_rang"], seconde["libelle"]) == (2, "Sourate 1, versets 1 à 2")
    assert plan[-1]["serie"] == "Série 1"


@pytest.mark.django_db
def test_les_versets_sont_dans_l_ordre_canonique_avec_leur_reference():
    prestation, *_ = creer_prestation_tiree()

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    assert [d["reference"] for d in plan if d["type"] == "verset"] == ["2:3", "2:4", "2:5", "1:1", "1:2"]


@pytest.mark.django_db
def test_index_et_total_sont_coherents():
    prestation, *_ = creer_prestation_tiree()

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    assert [d["index"] for d in plan] == list(range(len(plan)))
    assert {d["total"] for d in plan} == {len(plan)}


@pytest.mark.django_db
def test_d39_le_plan_ne_contient_aucun_texte_coranique():
    prestation, *_ = creer_prestation_tiree()

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    for d in plan:
        assert not ({"texte", "contenu"} & set(d))
        assert "s2v3" not in str(d)  # aucun fragment de texte du verset dans le plan


@pytest.mark.django_db
def test_regle_absolue_1_le_texte_vient_du_corpus_sans_modification():
    prestation, *_ = creer_prestation_tiree()
    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    textes = diapositives.textes_du_plan(plan)

    versets = [d for d in plan if d["type"] == "verset"]
    assert textes[versets[0]["index"]] == texte_du_verset(2, 3)
    assert textes[versets[-1]["index"]] == texte_du_verset(1, 2)
    assert all(d["index"] not in textes for d in plan if d["type"] != "verset")


@pytest.mark.django_db
def test_rec33_un_verset_long_est_segmente_et_la_concatenation_est_identique_au_corpus():
    prestation, *_ = creer_prestation_tiree(passages=(((2, 3), (2, 3)),))

    plan = diapositives.construire_plan(prestation, taille_max=20)  # segmentation réelle, 20 caractères

    segments = [d for d in plan if d["type"] == "verset"]
    textes = diapositives.textes_du_plan(plan)
    assert len(segments) > 1
    assert [(d["segment_rang"], d["segment_total"]) for d in segments] == [(i, len(segments)) for i in range(1, len(segments) + 1)]
    assert "".join(textes[d["index"]] for d in segments) == texte_du_verset(2, 3)
    assert all(len(textes[d["index"]]) <= 20 for d in segments)


@pytest.mark.django_db
def test_un_verset_court_n_est_pas_segmente():
    prestation, *_ = creer_prestation_tiree(passages=(((2, 3), (2, 3)),))

    plan = diapositives.construire_plan(prestation, taille_max=500)

    (verset,) = [d for d in plan if d["type"] == "verset"]
    assert (verset["segment_rang"], verset["segment_total"]) == (1, 1)


@pytest.mark.django_db
def test_plusieurs_tirages_donnent_une_fin_de_serie_par_serie_dans_l_ordre_des_tirages():
    prestation, *_ = creer_prestation_tiree(passages=(((2, 3), (2, 3)),), series=2, tirages=2)

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    assert types(plan).count("fin_serie") == 2
    assert [d["serie"] for d in plan if d["type"] == "fin_serie"] == ["Série 1", "Série 2"]


@pytest.mark.django_db
def test_une_question_enonce_est_presentee_comme_une_diapositive_d_enonce():
    prestation, epreuve, _ = creer_prestation_tiree(passages=(((2, 3), (2, 3)),))
    lot = epreuve.lot
    enonce = services_questions.creer_question_enonce(epreuve.organisation, "Quel est le sens de ce mot ?")
    serie = services_questions.composer_serie(lot, [enonce])
    Tirage.objects.filter(prestation=prestation).update(serie=serie)

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    assert types(plan) == ["intercalaire_question", "enonce", "fin_question", "fin_serie"]
    assert diapositives.textes_du_plan(plan)[1] == "Quel est le sens de ce mot ?"


@pytest.mark.django_db
def test_les_tirages_annules_sont_ignores():
    prestation, epreuve, _ = creer_prestation_tiree(passages=(((2, 3), (2, 3)),), series=2)
    autre_serie = epreuve.lot.series.exclude(tirages__prestation=prestation).get()
    creer_tirage(
        prestation, autre_serie, rang=1, statut=Tirage.Statut.ANNULE, motif_annulation="Incident",
        annule_par=creer_utilisateur(), annule_le=timezone.now(), id_demande=uuid.uuid4(),
    )

    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    assert types(plan).count("fin_serie") == 1


@pytest.mark.django_db
def test_sans_tirage_valide_le_plan_est_impossible():
    prestation, epreuve, _ = creer_prestation_tiree()
    nouvelle = creer_prestation(epreuve)  # en attente, aucun tirage

    with pytest.raises(PlanImpossibleError, match="tirage"):
        diapositives.construire_plan(nouvelle, segmenter=un_seul_segment)


@pytest.mark.django_db
def test_il_faut_tous_les_tirages_prevus():
    prestation, *_ = creer_prestation_tiree(passages=(((2, 3), (2, 3)),), series=2, tirages=2)
    Tirage.objects.filter(prestation=prestation, rang=2).update(
        statut=Tirage.Statut.ANNULE, motif_annulation="Incident",
        annule_par=creer_utilisateur(), annule_le=timezone.now(),
    )

    with pytest.raises(PlanImpossibleError, match="tirages prévus"):
        diapositives.construire_plan(prestation, segmenter=un_seul_segment)


@pytest.mark.django_db
def test_les_textes_se_lisent_en_une_seule_requete(django_assert_num_queries):
    prestation, *_ = creer_prestation_tiree()
    plan = diapositives.construire_plan(prestation, segmenter=un_seul_segment)

    with django_assert_num_queries(1):
        diapositives.textes_du_plan(plan)
```

**Fichier `apps\presentation\diapositives.py`**

```python
"""Plan des diapositives d'une prestation (§8.3 étape 4, §9.2, D39).

Le plan est une liste de dictionnaires qui ne contiennent QUE des références : l'identifiant du verset et les
bornes (``debut``, ``fin``) du segment dans son texte. Le texte lui-même est relu dans le corpus au moment de
l'envoyer (``textes_du_plan``) : on ne copie jamais un verset (règle absolue n°1), donc une version du corpus
figée (RM-27) garantit que le texte affiché est celui du corpus validé.
"""
from apps.coran.models import Verset
from apps.coran.passages import resoudre_passage
from apps.prestations.models import Prestation, Tirage
from apps.presentation.exceptions import PlanImpossibleError
from apps.presentation.segmentation import segmenter_verset
from apps.questions.models import Question

TAILLE_SEGMENT_PAR_DEFAUT = 180  # caractères par diapositive (D42) ; deviendra un réglage de l'épreuve


def construire_plan(prestation, taille_max=TAILLE_SEGMENT_PAR_DEFAUT, segmenter=segmenter_verset):
    """Construit la suite ordonnée des diapositives des séries tirées par la prestation.

    Pour chaque question : un intercalaire « Question n/P », ses diapositives (un verset ou un segment de
    verset chacune), puis « Fin de la question » ; « Fin de la série » après la dernière question (§8.3).
    """
    tirages = list(
        prestation.tirages.filter(statut=Tirage.Statut.VALIDE).select_related("serie").order_by("rang")
    )
    if not tirages:
        raise PlanImpossibleError("Aucun tirage valide : il n'y a rien à présenter.")
    if len(tirages) < prestation.epreuve.tirages_par_candidat:
        raise PlanImpossibleError("Tous les tirages prévus ne sont pas encore effectués : la série n'est pas tirée.")

    plan = []

    def ajouter(type_, **champs):
        plan.append({"type": type_, **champs})

    for tirage in tirages:
        serie = tirage.serie
        liaisons = list(serie.questions_ordonnees.select_related("question__passage").order_by("rang"))
        total = len(liaisons)
        for liaison in liaisons:
            question = liaison.question
            repere = {
                "serie": serie.libelle, "serie_id": str(serie.pk),
                "question_rang": liaison.rang, "question_total": total,
            }
            if question.type == Question.Type.PASSAGE_CORANIQUE:
                passage = question.passage
                repere["libelle"] = passage.libelle
                ajouter("intercalaire_question", **repere)
                versets = resoudre_passage(passage.debut, passage.fin, question.version_corpus)
                for verset in versets:
                    segments = segmenter(verset.texte, taille_max)
                    debut = 0
                    for rang, segment in enumerate(segments, start=1):
                        ajouter(
                            "verset", verset_id=verset.pk,
                            reference=f"{verset.sourate.numero}:{verset.numero}",
                            segment_rang=rang, segment_total=len(segments),
                            debut=debut, fin=debut + len(segment), **repere,
                        )
                        debut += len(segment)
            else:
                repere["libelle"] = "Énoncé"
                ajouter("intercalaire_question", **repere)
                ajouter("enonce", question_id=str(question.pk), **repere)
            ajouter("fin_question", **repere)
        ajouter("fin_serie", serie=serie.libelle, serie_id=str(serie.pk))

    total_diapositives = len(plan)
    for index, diapositive in enumerate(plan):
        diapositive["index"] = index
        diapositive["total"] = total_diapositives
    return plan


def textes_du_plan(plan):
    """``{index: texte}`` des diapositives qui en ont un, lu dans le corpus (une seule requête pour les versets)."""
    identifiants = {d["verset_id"] for d in plan if d["type"] == "verset"}
    versets = {v.pk: v.texte for v in Verset.objects.filter(pk__in=identifiants).only("texte")}
    textes = {}
    for d in plan:
        if d["type"] == "verset":
            textes[d["index"]] = versets[d["verset_id"]][d["debut"] : d["fin"]]
        elif d["type"] == "enonce":
            textes[d["index"]] = Question.objects.values_list("enonce", flat=True).get(pk=d["question_id"])
    return textes


def texte_de(diapositive):
    """Le texte d'UNE diapositive (une requête), ou ``None`` pour un intercalaire (jamais de texte coranique)."""
    if diapositive["type"] == "verset":
        texte = Verset.objects.values_list("texte", flat=True).get(pk=diapositive["verset_id"])
        return texte[diapositive["debut"] : diapositive["fin"]]
    if diapositive["type"] == "enonce":
        return Question.objects.values_list("enonce", flat=True).get(pk=diapositive["question_id"])
    return None
```

```powershell
pytest apps\presentation\tests\test_diapositives.py
```

Attendu : tout passe **si vos règles du corpus (chapitres 04, 06, 07) et votre segmentation sont écrites** ; sinon les tests échouent sur `references_du_passage` ou `segmenter_verset`. C'est voulu : le plan lit de vrais versets.

> **Piège rencontré :** un test qui crée des sourates dans une version déjà **validée** échoue dès que votre règle d'immuabilité est écrite (RM-27). Dans les fabriques, on écrit dans une version *importée*, puis on la valide.

## Questions de compréhension

1. Pourquoi le plan stocke-t-il des bornes (`debut`, `fin`) et pas le texte du segment ?
2. Pourquoi l'espace entre deux mots reste-t-elle à la **fin** du segment qui précède ?
3. Pourquoi le protocole prévoit-il un instantané alors que chaque changement est déjà diffusé ?

<details>
<summary>Réponses</summary>

1. Pour ne jamais copier un verset (règle n°1) : le texte vient toujours du corpus figé ; une copie pourrait diverger de la version validée.
2. Pour que la concaténation des segments soit **strictement** égale au texte, et qu'un segment commence toujours par un mot (pas d'espace en tête d'une diapositive).
3. Parce qu'un message peut se perdre (Wi-Fi, bus en mémoire) : un écran qui se reconnecte, ou qui voit un trou de version, redemande l'état complet et se reconstruit sans rejouer d'animation.
</details>

## Journal d'apprentissage

Expliquez avec vos mots pourquoi `InMemoryChannelLayer` suffit en développement mais pas en salle.

## Commit proposé

```text
Itération 3 : protocole temps réel, segmentation et plan des diapositives
```
