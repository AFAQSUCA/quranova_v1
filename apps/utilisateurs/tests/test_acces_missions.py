"""Tests des règles d'accès aux missions (§6.3, REC-29, RM-20).

Un opérateur n'accède qu'aux missions qui lui sont affectées ; un responsable client
n'accède qu'aux missions de son organisation ; l'administrateur accède à toutes.
"""
import pytest
from django.contrib.auth.models import AnonymousUser

from apps.commun.tests.outils import creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs import services
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

Role = Utilisateur.Role


@pytest.fixture
def deux_clients(db):
    """Deux clients (A et B), chacun avec une mission."""
    organisation_a, organisation_b = creer_organisation(), creer_organisation()
    return {
        "organisation_a": organisation_a,
        "organisation_b": organisation_b,
        "mission_a": creer_mission(organisation_a),
        "mission_b": creer_mission(organisation_b),
    }


def test_rec29_un_operateur_n_accede_qu_aux_missions_qui_lui_sont_affectees(deux_clients):
    operateur = creer_utilisateur(Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=deux_clients["mission_a"], utilisateur=operateur)

    accessibles = services.missions_accessibles(operateur)

    assert list(accessibles) == [deux_clients["mission_a"]]


def test_rec29_un_operateur_sans_affectation_n_accede_a_rien(deux_clients):
    assert list(services.missions_accessibles(creer_utilisateur(Role.OPERATEUR))) == []


def test_rec29_un_responsable_client_n_accede_qu_aux_missions_de_son_organisation(deux_clients):
    responsable_a = creer_utilisateur(Role.RESPONSABLE_CLIENT, deux_clients["organisation_a"])

    accessibles = services.missions_accessibles(responsable_a)

    assert list(accessibles) == [deux_clients["mission_a"]]


def test_l_administrateur_accede_a_toutes_les_missions(deux_clients):
    administrateur = creer_utilisateur(Role.ADMINISTRATEUR)

    assert set(services.missions_accessibles(administrateur)) == {
        deux_clients["mission_a"],
        deux_clients["mission_b"],
    }


def test_un_utilisateur_desactive_n_accede_a_rien(deux_clients):
    administrateur = creer_utilisateur(Role.ADMINISTRATEUR, is_active=False)

    assert list(services.missions_accessibles(administrateur)) == []


def test_un_visiteur_anonyme_n_accede_a_rien(deux_clients):
    assert list(services.missions_accessibles(AnonymousUser())) == []
