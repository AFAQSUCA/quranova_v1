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
