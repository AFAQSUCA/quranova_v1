"""Politique de mots de passe (§15.1) : au moins 12 caractères ; hachage PBKDF2 ou Argon2 ; appliquée à la création de compte."""
import importlib

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.commun.tests.outils import creer_utilisateur
from apps.utilisateurs.models import Utilisateur


@pytest.mark.parametrize("mot_de_passe", ["court", "onze-signes", "12345678901", "Abcdefg-123"])
def test_15_1_un_mot_de_passe_de_moins_de_12_caracteres_est_refuse(mot_de_passe):
    with pytest.raises(ValidationError) as erreur:
        validate_password(mot_de_passe)
    assert any("12" in m for m in erreur.value.messages)


def test_15_1_un_mot_de_passe_de_12_caracteres_non_banal_est_accepte():
    validate_password("Cl3-de-sallE-9x")  # ne lève rien


def test_15_1_un_mot_de_passe_uniquement_numerique_reste_refuse_meme_a_12_chiffres():
    with pytest.raises(ValidationError):
        validate_password("123456789012")


def test_15_1_le_hachage_est_pbkdf2_ou_argon2_en_production():
    """conftest.py accélère le hachage pour les tests ; ici on lit les réglages RÉELS de base.py."""
    base = importlib.import_module("config.settings.base")
    assert "PASSWORD_HASHERS" not in vars(base)  # on garde la liste par défaut de Django, dont la tête est PBKDF2
    from django.conf import global_settings

    assert global_settings.PASSWORD_HASHERS[0].endswith(("PBKDF2PasswordHasher", "Argon2PasswordHasher"))


@pytest.mark.django_db
def test_15_1_l_administration_refuse_de_creer_un_compte_avec_un_mot_de_passe_court(client):
    administrateur = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True)
    client.force_login(administrateur)

    reponse = client.post(reverse("admin:utilisateurs_utilisateur_add"), {
        "username": "nouvel-operateur", "password1": "Court-9x", "password2": "Court-9x", "role": "operateur",
    })

    assert reponse.status_code == 200 and "12" in reponse.content.decode()
    assert not Utilisateur.objects.filter(username="nouvel-operateur").exists()
