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
