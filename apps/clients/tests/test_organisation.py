"""Tests du modèle Organisation (§7.1, §14.1)."""
import pytest
from django.db import DataError, IntegrityError, transaction
from django.db.models import ProtectedError

from apps.clients.models import Organisation
from apps.commun.tests.outils import creer_mission, creer_organisation


@pytest.mark.django_db
def test_statut_initial_est_actif():
    assert creer_organisation().statut == Organisation.Statut.ACTIF


@pytest.mark.django_db
def test_le_nom_d_une_organisation_est_unique():
    creer_organisation(nom="Association Test")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_organisation(nom="Association Test")


@pytest.mark.django_db
@pytest.mark.parametrize("couleur", ["", "#0A7B5C", "#ffffff"])
def test_couleurs_valides_acceptees(couleur):
    organisation = creer_organisation(couleur_principale=couleur, couleur_secondaire=couleur)

    assert organisation.couleur_principale == couleur


@pytest.mark.django_db
@pytest.mark.parametrize("couleur", ["rouge", "#12345", "#GGGGGG", "123456", "#1234567"])
def test_couleurs_invalides_refusees_par_la_base(couleur):
    # Trop longue : refusée par la colonne (DataError) ; mal formée : par la contrainte (IntegrityError).
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        creer_organisation(couleur_principale=couleur)


@pytest.mark.django_db
def test_une_organisation_ne_peut_pas_etre_supprimee_si_elle_a_des_missions():
    mission = creer_mission()

    with pytest.raises(ProtectedError):
        mission.organisation.delete()
