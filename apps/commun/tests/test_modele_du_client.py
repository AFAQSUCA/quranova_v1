"""Tests des classes de base : séparation des clients (règle absolue n°3, RM-20, §13.4)."""
import uuid

import pytest
from django.apps import apps
from django.db import models

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.models import ModeleDuClient, ModeleHorodate
from apps.commun.tests.outils import creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs.models import AffectationOperateur


def modeles_du_client():
    return [m for m in apps.get_models() if issubclass(m, ModeleDuClient)]


def test_il_existe_au_moins_un_modele_du_client():
    assert modeles_du_client(), "Aucun modèle ne dérive de ModeleDuClient : le test ci-dessous serait vide."


@pytest.mark.parametrize("modele", modeles_du_client(), ids=lambda m: m.__name__)
def test_regle_3_toute_table_client_a_une_organisation_obligatoire_indexee_et_protegee(modele):
    champ = modele._meta.get_field("organisation")

    assert champ.many_to_one
    assert champ.related_model._meta.label == "clients.Organisation"
    assert champ.null is False
    assert champ.db_index is True
    assert champ.remote_field.on_delete is models.PROTECT


@pytest.mark.parametrize("modele", modeles_du_client(), ids=lambda m: m.__name__)
def test_toute_table_client_a_une_cle_primaire_uuid_et_des_horodatages(modele):
    assert issubclass(modele, ModeleHorodate)
    assert isinstance(modele._meta.pk, models.UUIDField)
    assert {"cree_le", "modifie_le"} <= {f.name for f in modele._meta.get_fields()}


@pytest.mark.django_db
def test_la_cle_primaire_est_un_uuid_genere_automatiquement():
    mission = creer_mission()

    assert isinstance(mission.pk, uuid.UUID)


@pytest.mark.django_db
def test_rm20_pour_organisation_ne_renvoie_que_les_donnees_du_client():
    organisation_a, organisation_b = creer_organisation(), creer_organisation()
    mission_a = creer_mission(organisation_a)
    creer_mission(organisation_b)

    resultat = type(mission_a).objects.pour_organisation(organisation_a)

    assert list(resultat) == [mission_a]


@pytest.mark.django_db
def test_organisation_deduite_du_parent_quand_elle_est_absente():
    mission = creer_mission()
    operateur = creer_utilisateur()

    affectation = AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)

    assert affectation.organisation_id == mission.organisation_id


@pytest.mark.django_db
def test_organisation_incoherente_avec_le_parent_refusee():
    """Une affectation d'une mission du client A ne peut pas être rangée dans le client B."""
    mission = creer_mission()
    autre_organisation = creer_organisation()
    operateur = creer_utilisateur()

    with pytest.raises(IncoherenceOrganisationError):
        AffectationOperateur.objects.create(
            mission=mission, utilisateur=operateur, organisation=autre_organisation
        )
