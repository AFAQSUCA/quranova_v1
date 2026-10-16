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
