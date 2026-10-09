"""Tests de l'affectation d'un opérateur à une mission (§6.3, §14.1)."""
import pytest
from django.db import IntegrityError, transaction

from apps.commun.tests.outils import creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs.exceptions import AffectationInvalideError
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

Role = Utilisateur.Role


@pytest.mark.django_db
def test_un_operateur_peut_etre_affecte_a_une_mission():
    mission, operateur = creer_mission(), creer_utilisateur(Role.OPERATEUR)

    affectation = AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

    assert affectation in mission.affectations.all()


@pytest.mark.django_db
def test_un_operateur_n_est_affecte_qu_une_fois_a_une_mission():
    mission, operateur = creer_mission(), creer_utilisateur(Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

    with pytest.raises(IntegrityError), transaction.atomic():
        AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.ADMINISTRATEUR, Role.RESPONSABLE_CLIENT])
def test_seul_un_operateur_peut_etre_affecte_a_une_mission(role):
    mission = creer_mission()
    utilisateur = creer_utilisateur(role, creer_organisation() if role == Role.RESPONSABLE_CLIENT else None)

    with pytest.raises(AffectationInvalideError):
        AffectationOperateur.objects.create(mission=mission, utilisateur=utilisateur)

    assert AffectationOperateur.objects.count() == 0
