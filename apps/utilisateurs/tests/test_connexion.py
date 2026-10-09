"""Limitation des tentatives de connexion du personnel et désactivation immédiate d'un compte (§15.1).

Règles : 5 échecs d'un même compte en 15 minutes verrouillent ce compte (même avec le bon mot de passe) ; 20 échecs d'une même adresse
verrouillent l'adresse ; une connexion réussie remet le compteur du compte à zéro ; le verrou expire seul ; il est journalisé une fois.
"""
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.commun.reseau import adresse_du_client
from apps.commun.tests.outils import creer_utilisateur
from apps.utilisateurs import connexion
from apps.utilisateurs.exceptions import TropDEssaisConnexionError
from apps.utilisateurs.models import TentativeConnexion, Utilisateur

MOT_DE_PASSE = "mot-de-passe-de-test"
URL_CONNEXION = "admin:login"


def echecs(identifiant, n, adresse="10.0.0.1", maintenant=None):
    for _ in range(n):
        connexion.noter(identifiant, adresse, reussie=False, maintenant=maintenant)


def tenter(client, username, mot_de_passe, adresse="10.0.0.1"):
    return client.post(reverse(URL_CONNEXION), {"username": username, "password": mot_de_passe, "next": "/admin/"}, REMOTE_ADDR=adresse)


@pytest.fixture
def personnel(db):
    return creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)


# --- Service ------------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_cinq_echecs_verrouillent_le_compte_et_le_message_donne_l_attente():
    echecs("awa", 5)

    with pytest.raises(TropDEssaisConnexionError) as erreur:
        connexion.verifier_limite("awa", "10.0.0.2")

    assert 0 < erreur.value.attente_secondes <= 15 * 60 and "minute" in str(erreur.value)


@pytest.mark.django_db
def test_quatre_echecs_ne_verrouillent_pas():
    echecs("awa", 4)
    connexion.verifier_limite("awa", "10.0.0.2")  # ne lève rien


@pytest.mark.django_db
def test_le_verrou_expire_apres_quinze_minutes():
    ancien = timezone.now() - timedelta(minutes=16)
    echecs("awa", 5, maintenant=ancien)

    connexion.verifier_limite("awa", "10.0.0.2")  # les échecs sont sortis de la fenêtre


@pytest.mark.django_db
def test_une_connexion_reussie_remet_le_compteur_du_compte_a_zero():
    echecs("awa", 4)
    connexion.noter("awa", "10.0.0.1", reussie=True)
    echecs("awa", 4)

    connexion.verifier_limite("awa", "10.0.0.1")  # 4 échecs depuis la dernière réussite : pas de verrou


@pytest.mark.django_db
def test_le_verrou_d_un_compte_ne_touche_pas_un_autre_compte():
    echecs("awa", 5)

    connexion.verifier_limite("moussa", "10.0.0.2")


@pytest.mark.django_db
def test_vingt_echecs_d_une_meme_adresse_verrouillent_l_adresse_quel_que_soit_le_compte():
    for i in range(20):
        connexion.noter(f"compte{i}", "10.0.0.9", reussie=False)

    with pytest.raises(TropDEssaisConnexionError):
        connexion.verifier_limite("tout-nouveau-compte", "10.0.0.9")
    connexion.verifier_limite("tout-nouveau-compte", "10.0.0.10")  # une autre adresse n'est pas touchée


@pytest.mark.django_db
def test_les_identifiants_sont_compares_sans_tenir_compte_de_la_casse():
    echecs("Awa", 3)
    echecs("AWA", 2)

    with pytest.raises(TropDEssaisConnexionError):
        connexion.verifier_limite("awa", "10.0.0.2")


@pytest.mark.django_db
def test_le_verrou_est_journalise_une_seule_fois():
    echecs("awa", 5)
    for _ in range(3):
        with pytest.raises(TropDEssaisConnexionError):
            connexion.verifier_limite("awa", "10.0.0.2")

    assert EntreeAudit.objects.filter(action="connexion.verrouillee").count() == 1


# --- Formulaire de connexion de l'administration ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_apres_cinq_echecs_le_bon_mot_de_passe_est_refuse_avec_un_message_clair(client, personnel):
    for _ in range(5):
        tenter(client, personnel.username, "mauvais-mot-de-passe")

    reponse = tenter(client, personnel.username, MOT_DE_PASSE)

    assert reponse.status_code == 200 and "Trop d" in reponse.content.decode() and "minute" in reponse.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_avant_le_verrou_le_bon_mot_de_passe_ouvre_la_session_et_remet_le_compteur_a_zero(client, personnel):
    for _ in range(4):
        tenter(client, personnel.username, "mauvais-mot-de-passe")

    reponse = tenter(client, personnel.username, MOT_DE_PASSE)

    assert reponse.status_code == 302 and "_auth_user_id" in client.session
    assert TentativeConnexion.objects.filter(identifiant=personnel.username, reussie=True).count() == 1


@pytest.mark.django_db
def test_une_authentification_hors_formulaire_est_aussi_limitee(personnel):
    """Défense en profondeur : le verrou est dans le backend d'authentification, pas seulement dans le formulaire."""
    from django.contrib.auth import authenticate

    echecs(personnel.username, 5)

    assert authenticate(username=personnel.username, password=MOT_DE_PASSE) is None


# --- Désactivation immédiate ---------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_desactiver_un_compte_coupe_sa_session_en_cours_immediatement(client, personnel):
    client.force_login(personnel)
    assert client.get(reverse("admin:index")).status_code == 200

    Utilisateur.objects.filter(pk=personnel.pk).update(is_active=False)

    reponse = client.get(reverse("admin:index"))
    assert reponse.status_code == 302 and "login" in reponse.url


@pytest.mark.django_db
def test_un_compte_desactive_ne_se_connecte_pas(client, personnel):
    Utilisateur.objects.filter(pk=personnel.pk).update(is_active=False)

    reponse = tenter(client, personnel.username, MOT_DE_PASSE)

    assert reponse.status_code == 200 and "_auth_user_id" not in client.session


# --- Adresse réelle du client derrière Nginx ---------------------------------------------------------------------------------------


def test_sans_proxy_de_confiance_l_adresse_est_remote_addr_et_l_en_tete_est_ignore(settings):
    settings.PROXY_DE_CONFIANCE = False
    requete = RequestFactory().get("/", REMOTE_ADDR="192.168.1.20", HTTP_X_REAL_IP="1.2.3.4")

    assert adresse_du_client(requete) == "192.168.1.20"  # un client ne peut pas se faire passer pour une autre adresse


def test_derriere_nginx_l_adresse_est_celle_que_nginx_transmet(settings):
    settings.PROXY_DE_CONFIANCE = True
    requete = RequestFactory().get("/", REMOTE_ADDR="172.18.0.5", HTTP_X_REAL_IP="192.168.50.23")

    assert adresse_du_client(requete) == "192.168.50.23"


def test_derriere_nginx_sans_en_tete_on_retombe_sur_remote_addr(settings):
    settings.PROXY_DE_CONFIANCE = True
    assert adresse_du_client(RequestFactory().get("/", REMOTE_ADDR="172.18.0.5")) == "172.18.0.5"
