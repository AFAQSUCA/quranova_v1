"""Tests de l'administration du corpus : lecture seule pour tout le monde (§12.3).

« Aucun compte d'organisation ne peut importer ni modifier de texte coranique »
(§12.1) et « les données du corpus ne peuvent pas être modifiées depuis
l'application » (§14.2). Même un superutilisateur ne peut ni ajouter, ni modifier,
ni supprimer : le texte vient uniquement de la commande d'import.

Aucun texte coranique n'est saisi dans ces tests.
"""
import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from apps.coran.models import Sourate, Verset, VersionCorpus
from apps.coran.tests.outils import creer_verset

MODELES = [VersionCorpus, Sourate, Verset]


def _requete(utilisateur):
    requete = RequestFactory().get("/admin/")
    requete.user = utilisateur
    return requete


def _nom_url(modele, action):
    return f"admin:{modele._meta.app_label}_{modele._meta.model_name}_{action}"


@pytest.fixture
def verset(db):
    return creer_verset()


@pytest.mark.parametrize("modele", MODELES)
def test_modele_enregistre_dans_l_administration(modele):
    assert modele in admin.site._registry


@pytest.mark.django_db
@pytest.mark.parametrize("modele", MODELES)
def test_aucune_permission_d_ecriture_meme_pour_un_superutilisateur(modele, admin_user):
    modele_admin = admin.site._registry[modele]
    requete = _requete(admin_user)

    assert admin_user.is_superuser
    assert modele_admin.has_view_permission(requete) is True
    assert modele_admin.has_add_permission(requete) is False
    assert modele_admin.has_change_permission(requete) is False
    assert modele_admin.has_delete_permission(requete) is False


@pytest.mark.django_db
@pytest.mark.parametrize("modele", MODELES)
def test_la_liste_est_consultable(modele, admin_client, verset):
    reponse = admin_client.get(reverse(_nom_url(modele, "changelist")))

    assert reponse.status_code == 200


@pytest.mark.django_db
def test_la_fiche_d_un_verset_est_consultable(admin_client, verset):
    reponse = admin_client.get(reverse(_nom_url(Verset, "change"), args=[verset.pk]))

    assert reponse.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("modele", MODELES)
def test_la_page_d_ajout_est_refusee(modele, admin_client):
    reponse = admin_client.get(reverse(_nom_url(modele, "add")))

    assert reponse.status_code == 403


@pytest.mark.django_db
def test_la_modification_est_refusee_et_le_texte_reste_intact(admin_client, verset):
    texte_avant = verset.texte

    reponse = admin_client.post(
        reverse(_nom_url(Verset, "change"), args=[verset.pk]),
        {"sourate": verset.sourate_id, "numero": verset.numero, "texte": "modifie"},
    )
    verset.refresh_from_db()

    assert reponse.status_code == 403
    assert verset.texte == texte_avant


@pytest.mark.django_db
def test_la_suppression_est_refusee(admin_client, verset):
    url = reverse(_nom_url(Verset, "delete"), args=[verset.pk])

    assert admin_client.get(url).status_code == 403
    assert admin_client.post(url, {"post": "yes"}).status_code == 403
    assert Verset.objects.filter(pk=verset.pk).exists()


@pytest.mark.django_db
def test_pas_d_action_de_suppression_en_masse(admin_client, admin_user, verset):
    modele_admin = admin.site._registry[Verset]
    assert "delete_selected" not in modele_admin.get_actions(_requete(admin_user))

    admin_client.post(
        reverse(_nom_url(Verset, "changelist")),
        {"action": "delete_selected", "_selected_action": [verset.pk], "post": "yes"},
    )

    assert Verset.objects.filter(pk=verset.pk).exists()
