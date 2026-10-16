# Chapitre 7 — Résoudre un passage coranique en versets

> **Étape du plan :** 0.5 · **Durée :** 3 heures · **Commit de référence :** `1eeb743` · **Résultat :** `resoudre_passage((2, 142), (2, 150), version)` renvoie les 9 versets dans l'ordre. Fin de la phase 0 côté code.

## Objectif

Transformer une **référence de début et de fin** (par exemple « sourate 2, verset 142 » à « sourate 2, verset 150 ») en **liste ordonnée de versets**, en couvrant les critères de recette :

| Critère | Ce qu'il exige |
|---|---|
| **REC-04** | 2:142 à 2:150 : 9 versets, dans le bon ordre |
| **REC-31** | 2:287, 115:1, 0:1, 1:0, fin antérieure au début : chaque référence est **refusée avec un message explicite** |
| **REC-32** | traversée de sourates : 1:6 à 2:5 donne 7 versets ; 113:5 à 114:6 donne 7 versets ; la basmala de la sourate 2 n'est **pas** numérotée |
| **REC-33** | un seul verset (2:282) : résolution correcte |

## Répartition du travail

| Élément | Où | Qui |
|---|---|---|
| Validation d'une référence et de l'ordre début/fin (REC-31) | `services.py`, fonctions pures | déjà écrites ci-dessous |
| **La traversée de sourates** (`references_du_passage`) | `services.py` | **vous** (`TODO(human)`) |
| `resoudre_passage(debut, fin, version)` : lit la base, appelle les règles | `passages.py` | déjà écrit ci-dessous |

Une **référence** est un couple `(sourate, verset)`, par exemple `(2, 255)`. Le **plan** du corpus est un dictionnaire `{numéro de sourate: nombre de versets}`, dans l'ordre canonique.

## Étape A — L'exception

**Fichier `apps\coran\exceptions.py`**

```python
"""Exceptions de l'application coran."""


class CorpusImmuableError(Exception):
    """Une écriture est refusée parce qu'elle violerait l'immuabilité du corpus (RM-27, §12.3)."""


class CorpusInvalideError(Exception):
    """Le corpus lu n'a pas la structure attendue ou échoue aux contrôles du §12.2."""


class CorpusDejaImporteError(Exception):
    """Un fichier de même empreinte SHA-256 a déjà été importé."""


class ReferenceInvalideError(Exception):
    """Une référence de verset ou un passage coranique est invalide (§8.4, REC-31)."""
```

## Étape B — Les tests d'abord

D'abord les règles pures (aucune base de données) :

**Fichier `apps\coran\tests\test_regles_passage.py`**

```python
"""Tests des règles pures sur les passages coraniques (§8.4, §12.4 ; REC-04, REC-31, REC-32).

Ces règles ne touchent pas à la base : elles travaillent sur un « plan » du corpus,
c'est-à-dire un dictionnaire {numéro de sourate: nombre de versets}, dans l'ordre
canonique. Une référence est un couple (sourate, verset), par exemple (2, 255).
"""
import pytest

from apps.coran import services
from apps.coran.exceptions import ReferenceInvalideError

# Nombres de versets réels des sourates utilisées par les critères de recette.
PLAN_REEL = {1: 7, 2: 286, 3: 200, 112: 4, 113: 5, 114: 6}
# Un plan sans « trou » pour tester les traversées de trois sourates ou plus.
PLAN_CONSECUTIF = {1: 7, 2: 10, 3: 5, 4: 4}


# --- REC-31 : références invalides (règles écrites par Claude) ---------------


@pytest.mark.parametrize(
    "reference, morceaux",
    [
        ((2, 287), ["2:287", "286"]),  # la sourate 2 n'a que 286 versets
        ((115, 1), ["115:1", "sourate 115", "114"]),  # il n'y a que 114 sourates
        ((0, 1), ["0:1", "sourate"]),  # numéro de sourate nul
        ((1, 0), ["1:0", "verset"]),  # numéro de verset nul
        ((-3, 1), ["-3:1", "sourate"]),
        ((2, -1), ["2:-1", "verset"]),
    ],
)
def test_rec31_reference_invalide_refusee_avec_message_explicite(reference, morceaux):
    with pytest.raises(ReferenceInvalideError) as erreur:
        services.verifier_reference(PLAN_REEL, reference)

    message = str(erreur.value)
    for morceau in morceaux:
        assert morceau in message


@pytest.mark.parametrize("reference", [(1, 1), (1, 7), (2, 255), (2, 286), (114, 6)])
def test_references_valides_acceptees(reference):
    services.verifier_reference(PLAN_REEL, reference)  # ne doit rien lever


@pytest.mark.parametrize("reference", [("2", 5), (2, "5"), (2.0, 5), (None, 1), (True, 1)])
def test_rec31_reference_non_entiere_refusee(reference):
    with pytest.raises(ReferenceInvalideError, match="entier"):
        services.verifier_reference(PLAN_REEL, reference)


@pytest.mark.parametrize("reference", [None, 5, (2,), (2, 5, 1), "2:5"])
def test_rec31_reference_mal_formee_refusee(reference):
    with pytest.raises(ReferenceInvalideError, match="couple"):
        services.verifier_reference(PLAN_REEL, reference)


def test_rec31_fin_anterieure_au_debut_refusee():
    with pytest.raises(ReferenceInvalideError) as erreur:
        services.verifier_ordre_passage((2, 150), (2, 142))

    assert "2:150" in str(erreur.value) and "2:142" in str(erreur.value)


def test_rec31_fin_dans_une_sourate_anterieure_refusee():
    with pytest.raises(ReferenceInvalideError):
        services.verifier_ordre_passage((2, 1), (1, 7))


@pytest.mark.parametrize(
    "debut, fin", [((2, 142), (2, 150)), ((2, 282), (2, 282)), ((1, 7), (2, 1)), ((1, 1), (114, 6))]
)
def test_ordres_valides_acceptes(debut, fin):
    services.verifier_ordre_passage(debut, fin)  # un seul verset (début = fin) est permis


# --- REC-04, REC-32 : traversée de sourates (règle à écrire par l'utilisateur) -


def test_rec04_passage_2_142_a_2_150_donne_9_versets_dans_l_ordre():
    references = services.references_du_passage(PLAN_REEL, (2, 142), (2, 150))

    assert references == [(2, n) for n in range(142, 151)]
    assert len(references) == 9


def test_un_seul_verset_donne_une_seule_reference():
    assert services.references_du_passage(PLAN_REEL, (2, 282), (2, 282)) == [(2, 282)]


def test_rec32_traversee_1_6_a_2_5_donne_7_versets_sans_basmala_numerotee():
    references = services.references_du_passage(PLAN_REEL, (1, 6), (2, 5))

    assert references == [(1, 6), (1, 7), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5)]
    assert (2, 0) not in references  # la basmala de la sourate 2 n'est pas un verset numéroté


def test_rec32_traversee_113_5_a_114_6_donne_7_versets():
    references = services.references_du_passage(PLAN_REEL, (113, 5), (114, 6))

    assert references == [(113, 5)] + [(114, n) for n in range(1, 7)]
    assert len(references) == 7


def test_traversee_de_trois_sourates_inclut_celle_du_milieu_en_entier():
    references = services.references_du_passage(PLAN_CONSECUTIF, (1, 6), (3, 2))

    assert references == [(1, 6), (1, 7)] + [(2, n) for n in range(1, 11)] + [(3, 1), (3, 2)]


def test_passage_d_une_sourate_entiere():
    assert services.references_du_passage(PLAN_CONSECUTIF, (3, 1), (3, 5)) == [(3, n) for n in range(1, 6)]


def test_passage_qui_se_termine_a_la_fin_de_la_derniere_sourate():
    assert services.references_du_passage(PLAN_CONSECUTIF, (4, 3), (4, 4)) == [(4, 3), (4, 4)]


def test_passage_qui_commence_au_dernier_verset_d_une_sourate():
    assert services.references_du_passage(PLAN_CONSECUTIF, (1, 7), (1, 7)) == [(1, 7)]


def test_references_en_ordre_canonique_strict_sans_doublon():
    references = services.references_du_passage(PLAN_CONSECUTIF, (1, 1), (4, 4))

    assert references == sorted(set(references))
    assert len(references) == sum(PLAN_CONSECUTIF.values())


def test_le_plan_n_est_pas_modifie_par_la_resolution():
    plan = dict(PLAN_CONSECUTIF)

    services.references_du_passage(plan, (1, 6), (3, 2))

    assert plan == PLAN_CONSECUTIF
```

Puis les tests avec la base, qui importent les **vrais fichiers Tanzil** (ils sont ignorés si `data\corpus` est vide) :

**Fichier `apps\coran\tests\test_passages.py`**

```python
"""Tests de resoudre_passage avec la base de données (§8.4, §12.4 ; REC-04, REC-31, REC-32, REC-33).

Les critères de recette sont vérifiés sur les VRAIS fichiers Tanzil de data/corpus
(importés dans une base de test). Les cas fins (isolation par version, corpus
incohérent) utilisent un petit corpus aux textes neutres.
"""
import re

import pytest
from django.conf import settings

from apps.coran.exceptions import CorpusInvalideError, ReferenceInvalideError
from apps.coran.importation import importer_corpus, lire_corpus
from apps.coran.models import Sourate, Verset
from apps.coran.passages import resoudre_passage
from apps.coran.tests.outils import creer_version

CHEMIN_TEXTE = settings.BASE_DIR / "data" / "corpus" / "quran-uthmani.xml"
CHEMIN_META = settings.BASE_DIR / "data" / "corpus" / "quran-data.xml"
FICHIERS_PRESENTS = CHEMIN_TEXTE.is_file() and CHEMIN_META.is_file()


@pytest.fixture
def version_reelle(db):
    """Importe les vrais fichiers Tanzil dans la base de test."""
    if not FICHIERS_PRESENTS:
        pytest.skip("Fichiers Tanzil absents de data/corpus")
    return importer_corpus(lire_corpus(CHEMIN_TEXTE, CHEMIN_META))


def remplir_version(version, plan):
    """Crée sourates et versets (textes neutres) d'après un plan {sourate: nombre de versets}."""
    sourates = Sourate.objects.bulk_create(
        [
            Sourate(
                version=version,
                numero=numero,
                nom_arabe=f"nom-arabe-{numero}",
                nom_translitteration=f"Translitteration-{numero}",
                nombre_versets=nombre,
                type_revelation=Sourate.TypeRevelation.MECQUOISE,
                ordre_revelation=numero,
            )
            for numero, nombre in plan.items()
        ]
    )
    Verset.objects.bulk_create(
        [
            Verset(sourate=sourate, numero=n, texte=f"texte-{sourate.numero}-{n}")
            for sourate in sourates
            for n in range(1, plan[sourate.numero] + 1)
        ]
    )


def references(versets):
    return [(v.sourate.numero, v.numero) for v in versets]


# --- Critères de recette sur les vrais fichiers ------------------------------


@pytest.mark.django_db
def test_rec04_passage_2_142_a_2_150_reconnait_9_versets_dans_l_ordre(version_reelle):
    versets = resoudre_passage((2, 142), (2, 150), version_reelle)

    assert references(versets) == [(2, n) for n in range(142, 151)]


@pytest.mark.django_db
def test_rec32_traversee_1_6_a_2_5(version_reelle):
    versets = resoudre_passage((1, 6), (2, 5), version_reelle)

    assert references(versets) == [(1, 6), (1, 7), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5)]
    assert len(versets) == 7
    assert all(v.numero >= 1 for v in versets)  # la basmala de la sourate 2 n'est pas numérotée


@pytest.mark.django_db
def test_rec32_traversee_113_5_a_114_6(version_reelle):
    versets = resoudre_passage((113, 5), (114, 6), version_reelle)

    assert references(versets) == [(113, 5)] + [(114, n) for n in range(1, 7)]
    assert len(versets) == 7


@pytest.mark.django_db
def test_rec33_un_seul_verset_2_282(version_reelle):
    versets = resoudre_passage((2, 282), (2, 282), version_reelle)

    assert references(versets) == [(2, 282)]
    assert versets[0].texte == Verset.objects.get(sourate__numero=2, numero=282).texte


@pytest.mark.django_db
@pytest.mark.parametrize(
    "debut, fin, morceaux",
    [
        ((2, 287), (2, 290), ["2:287", "286"]),
        ((115, 1), (115, 2), ["115:1", "114"]),
        ((0, 1), (1, 3), ["0:1"]),
        ((1, 0), (1, 3), ["1:0"]),
        ((2, 1), (2, 287), ["2:287", "286"]),  # c'est la FIN qui est invalide
        ((2, 150), (2, 142), ["2:150", "2:142"]),  # fin antérieure au début
        ((2, 1), (1, 7), ["1:7", "2:1"]),
    ],
)
def test_rec31_references_invalides_refusees_avec_message_explicite(
    version_reelle, debut, fin, morceaux
):
    with pytest.raises(ReferenceInvalideError) as erreur:
        resoudre_passage(debut, fin, version_reelle)

    for morceau in morceaux:
        assert morceau in str(erreur.value)


@pytest.mark.django_db
def test_regle_absolue_1_les_textes_du_passage_sont_ceux_du_fichier_tanzil(version_reelle):
    """Les textes viennent du corpus importé, jamais d'une reconstruction (§8.4)."""
    brut = CHEMIN_TEXTE.read_bytes().decode("utf-8")
    textes_fichier = re.findall(r'<aya index="\d+" text="([^"]*)"', brut)
    decalage = 7 + 141  # les 7 versets de la sourate 1, puis 141 versets avant 2:142

    versets = resoudre_passage((2, 142), (2, 150), version_reelle)

    assert [v.texte for v in versets] == textes_fichier[decalage : decalage + 9]


# --- Cas fins sur un petit corpus --------------------------------------------


@pytest.mark.django_db
def test_le_passage_reste_dans_la_version_demandee():
    version_a, version_b = creer_version(), creer_version()
    remplir_version(version_a, {1: 3, 2: 3})
    remplir_version(version_b, {1: 3, 2: 3})

    versets = resoudre_passage((1, 2), (2, 2), version_a)

    assert references(versets) == [(1, 2), (1, 3), (2, 1), (2, 2)]
    assert {v.sourate.version_id for v in versets} == {version_a.pk}


@pytest.mark.django_db
def test_corpus_incoherent_signale_explicitement():
    """La sourate 2 déclare 3 versets mais n'en contient que 2 : on refuse plutôt que de tronquer."""
    version = creer_version()
    remplir_version(version, {1: 3, 2: 3})
    Verset.objects.get(sourate__version=version, sourate__numero=2, numero=3).delete()

    with pytest.raises(CorpusInvalideError, match="2:3"):
        resoudre_passage((2, 1), (2, 3), version)


@pytest.mark.django_db
def test_version_sans_sourate_refusee():
    with pytest.raises(ReferenceInvalideError, match="aucune sourate"):
        resoudre_passage((1, 1), (1, 2), creer_version())


@pytest.mark.django_db
def test_nombre_de_requetes_constant(django_assert_max_num_queries):
    version = creer_version()
    remplir_version(version, {1: 7, 2: 30, 3: 20})

    with django_assert_max_num_queries(3):
        versets = resoudre_passage((1, 3), (3, 15), version)
        assert len(references(versets)) == 5 + 30 + 15  # .sourate est déjà chargée : pas de requête
```

## Étape C — Les règles et `resoudre_passage`

Remplacez `apps\coran\services.py` par ce fichier complet. Il contient les règles de validation, et `references_du_passage` **vide** (votre `TODO(human)`) :

**Fichier `apps\coran\services.py`**

```python
"""Règles métier du corpus (cf. §12.3 : versionnement et immutabilité).

Ces fonctions ne touchent pas à la base de données : elles reçoivent des
valeurs et lèvent ``CorpusImmuableError`` si l'opération est interdite.
Les modèles se chargent de lire l'état réel en base et d'appeler ces fonctions.
"""
from apps.coran.exceptions import CorpusImmuableError, ReferenceInvalideError  # noqa: F401


def verifier_transition_statut(ancien_statut, nouveau_statut, date_validation):
    """Refuse un changement de statut d'une version du corpus qui n'est pas autorisé.

    Statuts possibles : « importee », « validee », « active », « retiree ».

    TODO(human) : écrivez la règle.
    - Quelles transitions sont permises (par exemple importee -> validee) ?
    - Peut-on revenir en arrière (validee -> importee) ? Pourquoi serait-ce dangereux ?
    - Une version peut-elle devenir « validee » sans date de validation (PV du référent) ?
    Levez CorpusImmuableError avec un message explicite si la transition est refusée.
    """


def verifier_ecriture_autorisee(statut_version):
    """Refuse toute écriture sur le contenu d'une version dont le statut est figé.

    « Écriture » = création, modification ou suppression d'une sourate, d'un verset,
    ou modification des champs d'identité de la version (empreinte, fichier...).

    TODO(human) : écrivez la règle.
    - Pour quels statuts le contenu est-il figé ?
    Levez CorpusImmuableError avec un message explicite si l'écriture est refusée.
    """


def controler_corpus(corpus):
    """Contrôles automatiques du §12.2, point 3, appliqués AVANT toute écriture en base.

    ``corpus`` est un ``CorpusLu`` (cf. importation.py) : ``corpus.sourates`` est un tuple de
    ``SourateLue`` ; chacune porte ``numero``, ``nombre_versets`` (valeur déclarée par les
    métadonnées Tanzil) et ``versets`` (tuple de ``VersetLu`` avec ``numero`` et ``texte``).

    TODO(human) : écrivez les contrôles, en levant CorpusInvalideError avec un message
    explicite (quelle sourate, quel verset, quelle valeur attendue) :
    - exactement 114 sourates, numérotées de 1 à 114 sans trou ni doublon ;
    - exactement 6 236 versets au total ;
    - pour chaque sourate, le nombre de versets lus est égal à ``nombre_versets`` ;
    - dans chaque sourate, la numérotation des versets est continue (1, 2, 3, ...) ;
    - aucun verset vide (texte composé uniquement d'espaces compris).
    Vous choisissez : s'arrêter à la première erreur, ou les collecter toutes dans un seul message.
    """


# --- Passages coraniques (§8.4, §12.4) ------------------------------------------------
#
# Une référence est un couple (sourate, verset), par exemple (2, 255).
# Le « plan » du corpus est un dictionnaire {numéro de sourate: nombre de versets},
# dans l'ordre canonique des sourates.


def _ref(reference):
    return f"{reference[0]}:{reference[1]}"


def verifier_reference(plan, reference):
    """Refuse une référence qui n'existe pas dans le plan, avec un message explicite (REC-31)."""
    if not isinstance(reference, (tuple, list)) or len(reference) != 2:
        raise ReferenceInvalideError(
            f"Référence {reference!r} invalide : une référence est un couple (sourate, verset)."
        )
    sourate, verset = reference
    texte = _ref(reference)
    for valeur, nom in ((sourate, "sourate"), (verset, "verset")):
        if not isinstance(valeur, int) or isinstance(valeur, bool):
            raise ReferenceInvalideError(
                f"Référence {texte} invalide : le numéro de {nom} doit être un entier."
            )
    if sourate < 1:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : le numéro de sourate doit être supérieur ou égal à 1."
        )
    if sourate not in plan:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : la sourate {sourate} n'existe pas "
            f"dans cette version du corpus (sourates 1 à {max(plan)})."
        )
    if verset < 1:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : le numéro de verset doit être supérieur ou égal à 1."
        )
    if verset > plan[sourate]:
        raise ReferenceInvalideError(
            f"Référence {texte} invalide : la sourate {sourate} ne compte que "
            f"{plan[sourate]} versets (le verset {verset} n'existe pas)."
        )


def verifier_ordre_passage(debut, fin):
    """Refuse un passage dont la fin précède le début dans l'ordre canonique (§8.4, point 2).

    Un passage d'un seul verset (début = fin) est permis.
    """
    if tuple(fin) < tuple(debut):
        raise ReferenceInvalideError(
            f"Passage invalide : la fin du passage ({_ref(fin)}) précède son début ({_ref(debut)})."
        )


def references_du_passage(plan, debut, fin):
    """Liste, dans l'ordre canonique, les références de ``debut`` à ``fin`` INCLUSES.

    ``plan`` : {numéro de sourate: nombre de versets}, dans l'ordre des sourates.
    ``debut`` et ``fin`` : couples (sourate, verset), déjà validés (ils existent et
    ``debut`` <= ``fin``). Renvoie une liste de couples, par exemple pour le plan réel :
    references_du_passage(plan, (1, 6), (2, 5)) -> [(1, 6), (1, 7), (2, 1), ..., (2, 5)]

    TODO(human) : écrivez la gestion de la traversée de sourates.
    - Un passage dans une seule sourate : de debut[1] à fin[1].
    - Un passage sur plusieurs sourates : fin de la première, sourates du milieu EN ENTIER,
      début de la dernière. Les versets sont numérotés à partir de 1 (la basmala n'est pas un
      verset numéroté, §12.4) et le plan donne le dernier verset de chaque sourate.
    - Le résultat est trié, sans doublon, et ne modifie pas ``plan``.
    """
```

Le module qui lit la base :

**Fichier `apps\coran\passages.py`**

```python
"""Résolution d'un passage coranique en liste de versets (§8.4, §12.4).

Ce module est séparé de services.py parce qu'il lit la base de données, alors que
les modèles importent déjà services.py (import circulaire sinon). Les RÈGLES
(validation des références, traversée de sourates) restent dans services.py.

Règle absolue n°1 : les textes viennent uniquement du corpus importé, jamais d'une
reconstruction par concaténation (§8.4).
"""
from django.db.models import Q

from apps.coran import services
from apps.coran.exceptions import CorpusInvalideError, ReferenceInvalideError
from apps.coran.models import Sourate, Verset


def resoudre_passage(debut, fin, version):
    """Renvoie la liste ordonnée des ``Verset`` de ``debut`` à ``fin`` (bornes incluses).

    ``debut`` et ``fin`` sont des couples (sourate, verset), par exemple (2, 142) et (2, 150).
    ``version`` est la ``VersionCorpus`` dans laquelle on cherche (RM-27).
    Lève ``ReferenceInvalideError`` si une référence n'existe pas ou si la fin précède le début.
    """
    plan = dict(
        Sourate.objects.filter(version=version)
        .order_by("numero")
        .values_list("numero", "nombre_versets")
    )
    if not plan:
        raise ReferenceInvalideError(
            f"La version du corpus n° {version.pk} ne contient aucune sourate."
        )

    services.verifier_reference(plan, debut)
    services.verifier_reference(plan, fin)
    debut, fin = tuple(debut), tuple(fin)
    services.verifier_ordre_passage(debut, fin)

    references = services.references_du_passage(plan, debut, fin)
    _verifier_contrat(references, debut, fin)

    # Une seule requête : on regroupe les références par sourate en intervalles.
    bornes = {}
    for sourate, verset in references:
        bas, haut = bornes.get(sourate, (verset, verset))
        bornes[sourate] = (min(bas, verset), max(haut, verset))
    filtre = Q()
    for sourate, (bas, haut) in bornes.items():
        filtre |= Q(sourate__numero=sourate, numero__gte=bas, numero__lte=haut)
    versets = Verset.objects.filter(filtre, sourate__version=version).select_related("sourate")
    par_reference = {(v.sourate.numero, v.numero): v for v in versets}

    resultat = []
    for sourate, verset in references:
        if (sourate, verset) not in par_reference:
            raise CorpusInvalideError(
                f"Corpus incohérent : le verset {sourate}:{verset} est annoncé par les "
                f"métadonnées mais absent de la version n° {version.pk}."
            )
        resultat.append(par_reference[(sourate, verset)])
    return resultat


def _verifier_contrat(references, debut, fin):
    """Vérifie que la règle de traversée a rendu un résultat exploitable."""
    if (
        not references
        or tuple(references[0]) != debut
        or tuple(references[-1]) != fin
        or list(references) != sorted(set(map(tuple, references)))
    ):
        raise CorpusInvalideError(
            "La règle de traversée de sourates a renvoyé un résultat incohérent : "
            "la liste doit commencer au début du passage, finir à sa fin, "
            "être triée et sans doublon."
        )
```

## Étape D — Constater l'état « rouge »

```powershell
pytest -q
```

Attendu : mes règles de validation passent (**28 tests** dans `test_regles_passage.py`), et seule la traversée échoue : **9 tests de règles** et **8 tests en base**. Si vous n'avez pas encore écrit les règles des chapitres 4 et 6, il s'y ajoute 39 et 10 échecs : en tout **66 failed, 120 passed**.

## Étape E — À vous : la traversée de sourates (`TODO(human)`)

Dans `apps\coran\services.py`, écrivez le corps de `references_du_passage(plan, debut, fin)` :

- **Entrée** : le plan et deux références déjà validées (elles existent et `debut` ≤ `fin`).
- **Sortie** : la liste des couples `(sourate, verset)`, bornes incluses, triée, sans doublon.
- **Un passage dans une seule sourate** : de `debut[1]` à `fin[1]`.
- **Un passage sur plusieurs sourates** : fin de la première, sourates du milieu **en entier**, début de la dernière.
- La basmala n'est jamais un verset numéroté : il n'y a jamais de `(2, 0)`.

**Indice :** parcourez `plan.items()` ; pour chaque sourate comprise entre le début et la fin, calculez le premier verset (celui du début si c'est la première sourate, sinon 1) et le dernier (celui de la fin si c'est la dernière, sinon le dernier verset de la sourate).

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
# Dans apps/coran/services.py, remplacez le corps de references_du_passage par :

def references_du_passage(plan, debut, fin):
    """Liste, dans l'ordre canonique, les références de ``debut`` à ``fin`` INCLUSES."""
    (sourate_debut, verset_debut), (sourate_fin, verset_fin) = debut, fin
    references = []
    for sourate, nombre_de_versets in plan.items():
        if sourate < sourate_debut or sourate > sourate_fin:
            continue  # hors du passage
        # Première sourate : on part du verset de début ; les suivantes, du verset 1.
        premier = verset_debut if sourate == sourate_debut else 1
        # Dernière sourate : on s'arrête au verset de fin ; les précédentes, au dernier verset.
        dernier = verset_fin if sourate == sourate_fin else nombre_de_versets
        references.extend((sourate, numero) for numero in range(premier, dernier + 1))
    return references
```

</details>

```powershell
pytest apps\coran\tests\test_regles_passage.py apps\coran\tests\test_passages.py
pytest
```

Attendu (avec les règles des chapitres 4 et 6) : **186 passed**.

```powershell
git add apps
git commit -m "Corpus : passages coraniques (REC-04, REC-31, REC-32, REC-33)"
```

## Pour comprendre

- **Pourquoi `references_du_passage` ne touche pas à la base** : c'est une règle pure, testable en une fraction de seconde, qui ne dépend d'aucun modèle. `resoudre_passage` s'occupe de la base.
- **`resoudre_passage` vérifie le résultat de votre règle** (`_verifier_contrat`) : il doit commencer au début, finir à la fin, être trié et sans doublon. Une erreur dans la règle produit un message clair plutôt qu'un résultat faux silencieux.
- **Une seule requête** : les références sont regroupées en intervalles par sourate, puis une seule requête SQL lit tous les versets. Le test `test_nombre_de_requetes_constant` le garantit.
- **Corpus incohérent** : si les métadonnées annoncent 3 versets et que la base n'en contient que 2, on **refuse** (`CorpusInvalideError`) au lieu de tronquer le passage en silence.
- **Limites à connaître** : REC-30 demande un « export identique octet par octet » ; le projet compare les **textes des versets** de la base à ceux du fichier, sans régénérer un fichier XML complet. REC-33 (segmentation de 2:282 pour l'affichage) relève du diaporama : ici, on ne vérifie que la résolution d'un verset seul.

## Questions de compréhension

1. Pourquoi sépare-t-on `references_du_passage` (règle pure) de `resoudre_passage` (qui lit la base) ?
2. Pourquoi `resoudre_passage` vérifie-t-il le résultat de votre règle au lieu de lui faire confiance ?
3. Pourquoi les tests de la traversée utilisent-ils les nombres de versets **réels** (7, 286, 4, 5, 6) ?

<details>
<summary>Réponses</summary>

1. La règle pure se teste sans base de données (rapide, sans import circulaire) ; la lecture de la base se teste à part. Chacune a une seule responsabilité.
2. Une règle fausse (liste qui ne commence pas au début, doublons...) produirait des passages erronés présentés aux jurés. Un contrôle explicite transforme cette erreur silencieuse en erreur visible.
3. Les critères de recette REC-04 et REC-32 sont formulés avec ces nombres (1:6 à 2:5 donne 7 versets parce que la sourate 1 en a 7). Un plan fictif ne prouverait rien sur ces critères.
</details>

## Bilan de la phase 0 (code)

| Élément | État |
|---|---|
| Environnement Windows, Django, PostgreSQL, Channels en mémoire, pytest | fait |
| Modèles `VersionCorpus`, `Sourate`, `Verset` + contraintes | fait |
| Garde d'immuabilité | règles à écrire (chapitre 4) |
| Administration en lecture seule | fait |
| Import du corpus | fait, contrôles à écrire (chapitre 6) |
| Passages coraniques | fait, traversée à écrire (chapitre 7) |
| Jalon J0 : validation du corpus par le référent coranique | hors code : désigner le référent, faire valider l'échantillon du §12.2, signer le procès-verbal |

## Journal d'apprentissage

Notez comment vous avez raisonné pour la traversée de sourates, et ce que le contrôle du résultat dans `resoudre_passage` vous a appris sur la confiance entre fonctions.
