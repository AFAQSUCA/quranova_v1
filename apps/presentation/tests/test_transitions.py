"""Tests des transitions de la présentation (§9.3, RM-10, RM-11) — fonction à écrire par vous."""
import pytest

from apps.presentation.exceptions import TransitionInterditeError
from apps.presentation.transitions import AFFICHAGE, PAUSE, PREPAREE, TERMINEE, Position, appliquer_transition

TOTAL = 5  # diapositives 0 à 4


def p(phase, index=None, rejeu=0):
    return Position(phase, index, rejeu)


@pytest.mark.parametrize(
    "avant, action, apres",
    [
        (p(PREPAREE), "demarrer", p(AFFICHAGE, 0)),
        (p(AFFICHAGE, 0), "suivante", p(AFFICHAGE, 1)),
        (p(AFFICHAGE, 3), "suivante", p(AFFICHAGE, 4)),
        (p(AFFICHAGE, 4), "precedente", p(AFFICHAGE, 3)),
        (p(AFFICHAGE, 1), "precedente", p(AFFICHAGE, 0)),
        (p(AFFICHAGE, 2), "pause", p(PAUSE, 2)),
        (p(PAUSE, 2), "reprendre", p(AFFICHAGE, 2)),
        (p(AFFICHAGE, 2, rejeu=1), "reafficher", p(AFFICHAGE, 2, rejeu=2)),
        (p(AFFICHAGE, 4), "terminer", p(TERMINEE, 4)),
        (p(AFFICHAGE, 1), "terminer", p(TERMINEE, 1)),  # fin anticipée (incident) possible
        (p(PAUSE, 3), "terminer", p(TERMINEE, 3)),
    ],
)
def test_transitions_autorisees(avant, action, apres):
    assert appliquer_transition(avant, TOTAL, action) == apres


@pytest.mark.parametrize(
    "avant, action",
    [
        (p(PREPAREE), "suivante"),  # RM-11 : rien n'avance avant « démarrer »
        (p(PREPAREE), "precedente"),
        (p(PREPAREE), "pause"),
        (p(PREPAREE), "terminer"),
        (p(AFFICHAGE, 4), "suivante"),  # jamais au-delà de la dernière diapositive
        (p(AFFICHAGE, 0), "precedente"),  # pas de retour avant la première
        (p(AFFICHAGE, 0), "demarrer"),  # déjà démarrée
        (p(AFFICHAGE, 1), "reprendre"),  # ce n'est pas en pause
        (p(PAUSE, 2), "suivante"),  # la pause bloque l'avancement (§9.3)
        (p(PAUSE, 2), "precedente"),
        (p(PAUSE, 2), "pause"),
        (p(PAUSE, 2), "reafficher"),
        (p(PAUSE, 2), "demarrer"),
        (p(TERMINEE, 4), "suivante"),
        (p(TERMINEE, 4), "precedente"),
        (p(TERMINEE, 4), "reprendre"),
        (p(TERMINEE, 4), "terminer"),
        (p(TERMINEE, 4), "reafficher"),
        (p(AFFICHAGE, 2), "preparer"),  # « préparer » crée l'état : ce n'est pas une transition
        (p(AFFICHAGE, 2), "n_importe_quoi"),
        (p(AFFICHAGE, 2), ""),
    ],
)
def test_transitions_interdites_avec_un_message(avant, action):
    with pytest.raises(TransitionInterditeError) as erreur:
        appliquer_transition(avant, TOTAL, action)

    assert str(erreur.value)  # un message explicite pour l'opérateur


def test_une_presentation_d_une_seule_diapositive():
    debut = appliquer_transition(p(PREPAREE), 1, "demarrer")

    assert debut == p(AFFICHAGE, 0)
    with pytest.raises(TransitionInterditeError):
        appliquer_transition(debut, 1, "suivante")
    assert appliquer_transition(debut, 1, "terminer") == p(TERMINEE, 0)


def test_la_position_recue_n_est_jamais_modifiee():
    avant = p(AFFICHAGE, 2)

    appliquer_transition(avant, TOTAL, "suivante")

    assert avant == p(AFFICHAGE, 2)


def test_parcours_complet_de_la_premiere_a_la_derniere_diapositive():
    position = appliquer_transition(p(PREPAREE), TOTAL, "demarrer")
    for attendu in range(1, TOTAL):
        position = appliquer_transition(position, TOTAL, "suivante")
        assert position.index == attendu

    assert appliquer_transition(position, TOTAL, "terminer").phase == TERMINEE
