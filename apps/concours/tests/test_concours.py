"""Tests du modèle Concours (§7.2, §14.1 ; RM-01, RM-27, RM-31)."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.commun.tests.outils import (
    creer_concours,
    creer_mission,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours.models import Concours
from apps.utilisateurs.models import Utilisateur

Etat = Concours.Etat


@pytest.mark.django_db
def test_etat_initial_est_brouillon_et_format_presentiel():
    concours = creer_concours()

    assert concours.etat == Etat.BROUILLON
    assert concours.format == Concours.Format.PRESENTIEL
    assert concours.version_corpus is None
    assert concours.configuration_validee_le is None


@pytest.mark.django_db
def test_rm01_le_concours_prend_l_organisation_de_sa_mission():
    mission = creer_mission()

    concours = creer_concours(mission)

    assert concours.organisation_id == mission.organisation_id


@pytest.mark.django_db
def test_une_mission_peut_regrouper_plusieurs_concours():
    mission = creer_mission()
    creer_concours(mission, nom="Concours A")
    creer_concours(mission, nom="Concours B")

    assert mission.concours.count() == 2


@pytest.mark.django_db
def test_la_date_de_fin_ne_peut_pas_preceder_la_date_de_debut():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(date_debut=date(2027, 1, 21), date_fin=date(2027, 1, 20))


@pytest.mark.django_db
def test_nom_et_edition_uniques_par_organisation():
    mission = creer_mission()
    creer_concours(mission, nom="Grand concours", edition="2027")

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(mission, nom="Grand concours", edition="2027")


@pytest.mark.django_db
def test_meme_nom_possible_pour_deux_editions_ou_deux_clients():
    mission = creer_mission()
    creer_concours(mission, nom="Grand concours", edition="2027")
    creer_concours(mission, nom="Grand concours", edition="2028")
    creer_concours(creer_mission(), nom="Grand concours", edition="2027")

    assert Concours.objects.filter(nom="Grand concours").count() == 3


@pytest.mark.django_db
@pytest.mark.parametrize(
    "etat", [Etat.OUVERT, Etat.EN_COURS, Etat.SUSPENDU, Etat.TERMINE, Etat.ARCHIVE]
)
def test_rm27_rm31_un_concours_non_brouillon_exige_corpus_et_validation(etat):
    """Un concours ouvert a un corpus figé (RM-27) et une configuration validée (RM-31)."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(etat=etat)


@pytest.mark.django_db
def test_un_concours_non_brouillon_avec_corpus_et_validation_est_accepte():
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)
    mission = creer_mission(responsable.organisation)

    concours = creer_concours(
        mission,
        etat=Etat.OUVERT,
        version_corpus=creer_version_validee(),
        configuration_validee_par=responsable,
        configuration_validee_le=timezone.now(),
        configuration_empreinte="a" * 64,
    )

    assert concours.etat == Etat.OUVERT


@pytest.mark.django_db
def test_la_validation_de_configuration_est_complete_ou_absente():
    """Qui, quand et quelle configuration : les trois ensemble, ou aucun des trois."""
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(configuration_validee_par=responsable)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(configuration_validee_le=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_concours(configuration_empreinte="a" * 64)


@pytest.mark.django_db
def test_une_mission_ne_peut_pas_etre_supprimee_si_elle_a_des_concours():
    concours = creer_concours()

    with pytest.raises(ProtectedError):
        concours.mission.delete()
