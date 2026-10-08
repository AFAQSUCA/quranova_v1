"""Tests du modèle Utilisateur personnalisé et de ses rôles (§6.1, D1)."""
import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.commun.tests.outils import creer_organisation, creer_utilisateur
from apps.utilisateurs.models import Utilisateur

Role = Utilisateur.Role


def test_le_modele_utilisateur_du_projet_est_personnalise():
    assert settings.AUTH_USER_MODEL == "utilisateurs.Utilisateur"
    assert get_user_model() is Utilisateur


@pytest.mark.django_db
def test_la_cle_primaire_de_l_utilisateur_est_un_uuid():
    assert isinstance(creer_utilisateur().pk, uuid.UUID)


@pytest.mark.django_db
def test_un_responsable_client_a_une_organisation():
    organisation = creer_organisation()

    responsable = creer_utilisateur(Role.RESPONSABLE_CLIENT, organisation)

    assert responsable.organisation == organisation


@pytest.mark.django_db
def test_un_responsable_client_sans_organisation_est_refuse():
    with pytest.raises(IntegrityError), transaction.atomic():
        Utilisateur.objects.create_user(
            username="sans-organisation", password="x", role=Role.RESPONSABLE_CLIENT
        )


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.OPERATEUR, Role.ADMINISTRATEUR])
def test_un_utilisateur_du_prestataire_n_a_pas_d_organisation(role):
    assert creer_utilisateur(role).organisation is None

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_utilisateur(role, organisation=creer_organisation())


@pytest.mark.django_db
def test_le_role_par_defaut_est_operateur():
    utilisateur = Utilisateur.objects.create_user(username="par-defaut", password="x")

    assert utilisateur.role == Role.OPERATEUR


@pytest.mark.django_db
def test_un_superutilisateur_est_administrateur():
    superutilisateur = Utilisateur.objects.create_superuser(
        username="chef", email="chef@example.org", password="x"
    )

    assert superutilisateur.role == Role.ADMINISTRATEUR
    assert superutilisateur.is_superuser and superutilisateur.is_staff
