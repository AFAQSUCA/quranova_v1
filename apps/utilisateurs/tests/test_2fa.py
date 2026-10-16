"""Authentification à deux facteurs (§15.1) : obligatoire pour l'administrateur et les opérateurs, TOTP (application d'authentification).

Elle est active en production (``EXIGER_2FA``), coupée en développement et dans les autres tests ; ici on l'active explicitement.
"""
import time
import uuid

import pytest
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_utilisateur
from apps.utilisateurs import otp
from apps.utilisateurs.models import Utilisateur

PERSONNEL = [Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR]


@pytest.fixture(autouse=True)
def avec_2fa(settings):
    settings.EXIGER_2FA = True


def jeton(appareil, decalage=0):
    """Le code à 6 chiffres que afficherait l'application d'authentification."""
    totp = TOTP(appareil.bin_key, appareil.step, appareil.t0, appareil.digits, appareil.drift)
    totp.time = time.time() + decalage
    return f"{totp.token():06d}"


def compte(role=Utilisateur.Role.OPERATEUR, confirme=True):
    utilisateur = creer_utilisateur(role, is_staff=True)
    appareil = TOTPDevice.objects.create(user=utilisateur, name="test", confirmed=confirme) if confirme is not None else None
    return utilisateur, appareil


def verifier(client, appareil, valeur, suivant="/admin/"):
    return client.post(reverse("utilisateurs:verification_2fa") + f"?next={suivant}", {"jeton": valeur})


# --- Obligation -------------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role", PERSONNEL)
def test_15_1_sans_deuxieme_facteur_l_administration_renvoie_vers_la_verification(client, role):
    utilisateur, _ = compte(role)
    client.force_login(utilisateur)

    reponse = client.get(reverse("admin:index"))

    assert reponse.status_code == 302 and reponse.url.startswith(reverse("utilisateurs:verification_2fa"))
    assert "next=" in reponse.url


@pytest.mark.django_db
def test_15_1_les_ecrans_et_documents_de_l_operateur_sont_aussi_proteges(client):
    utilisateur, _ = compte()
    client.force_login(utilisateur)
    inconnu = uuid.uuid4()

    for nom in ("presentation:ecran_commande", "resultats:proces_verbal", "resultats:proces_verbal_pdf", "resultats:export"):
        argument = inconnu
        reponse = client.get(reverse(nom, args=[argument]))
        assert reponse.status_code == 302 and "/compte/2fa/" in reponse.url, nom


@pytest.mark.django_db
def test_15_1_une_api_de_session_repond_403_json_sans_deuxieme_facteur(client):
    utilisateur, _ = compte()
    client.force_login(utilisateur)

    reponse = client.get(reverse("presentation:prestations", args=[uuid.uuid4()]))

    assert reponse.status_code == 403 and reponse.json()["code"] == "2fa_requise"


@pytest.mark.django_db
def test_15_1_le_responsable_client_n_est_pas_soumis_au_deuxieme_facteur(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    client.force_login(responsable)

    assert client.get(reverse("admin:index")).status_code == 200


@pytest.mark.django_db
def test_le_deuxieme_facteur_est_coupe_quand_le_reglage_est_faux(client, settings):
    settings.EXIGER_2FA = False
    utilisateur, _ = compte()
    client.force_login(utilisateur)

    assert client.get(reverse("admin:index")).status_code == 200


@pytest.mark.django_db
def test_les_pages_de_connexion_et_de_verification_restent_accessibles(client):
    utilisateur, _ = compte()
    client.force_login(utilisateur)

    assert client.get(reverse("utilisateurs:verification_2fa")).status_code == 200
    assert client.post(reverse("admin:logout")).status_code in (200, 302)


# --- Vérification -------------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_bon_code_ouvre_l_acces_et_redirige_vers_la_page_demandee(client):
    utilisateur, appareil = compte()
    client.force_login(utilisateur)

    reponse = verifier(client, appareil, jeton(appareil))

    assert reponse.status_code == 302 and reponse.url == "/admin/"
    assert client.get(reverse("admin:index")).status_code == 200
    assert client.session[DEVICE_ID_SESSION_KEY] == appareil.persistent_id


@pytest.mark.django_db
def test_un_mauvais_code_est_refuse_et_l_acces_reste_ferme(client):
    utilisateur, appareil = compte()
    client.force_login(utilisateur)

    reponse = verifier(client, appareil, "000000" if jeton(appareil) != "000000" else "111111")

    assert reponse.status_code == 200 and "incorrect" in reponse.content.decode().lower()
    assert client.get(reverse("admin:index")).status_code == 302


@pytest.mark.django_db
@pytest.mark.parametrize("valeur", ["", "abcdef", "12345", "1234567", "12 34"])
def test_un_code_mal_forme_est_refuse_sans_erreur_serveur(client, valeur):
    utilisateur, appareil = compte()
    client.force_login(utilisateur)

    assert verifier(client, appareil, valeur).status_code == 200


@pytest.mark.django_db
def test_un_code_deja_utilise_ne_sert_pas_une_seconde_fois(client):
    """Anti-rejeu : quelqu'un qui aurait vu le code par-dessus l'épaule ne peut pas le réutiliser."""
    utilisateur, appareil = compte()
    code = jeton(appareil)
    premier, second = client, client.__class__()
    premier.force_login(utilisateur)
    second.force_login(utilisateur)

    assert verifier(premier, appareil, code).status_code == 302
    rejeu = verifier(second, appareil, code)

    assert rejeu.status_code == 200 and second.get(reverse("admin:index")).status_code == 302


@pytest.mark.django_db
def test_apres_plusieurs_echecs_meme_le_bon_code_est_refuse_un_court_instant(client):
    utilisateur, appareil = compte()
    client.force_login(utilisateur)
    for _ in range(4):
        verifier(client, appareil, "000000")

    reponse = verifier(client, appareil, jeton(appareil))

    assert reponse.status_code == 200 and "patienter" in reponse.content.decode().lower()
    assert client.get(reverse("admin:index")).status_code == 302


@pytest.mark.django_db
def test_l_adresse_de_retour_externe_est_ignoree(client):
    utilisateur, appareil = compte()
    client.force_login(utilisateur)

    reponse = verifier(client, appareil, jeton(appareil), suivant="https://pirate.example/")

    assert reponse.status_code == 302 and reponse.url == "/admin/"


# --- Enrôlement ---------------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_au_premier_passage_la_page_propose_un_qr_code_et_la_cle_de_saisie_manuelle(client):
    utilisateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    client.force_login(utilisateur)

    page = client.get(reverse("utilisateurs:verification_2fa")).content.decode()

    appareil = TOTPDevice.objects.get(user=utilisateur)
    assert not appareil.confirmed
    assert "<svg" in page and 'role="img"' in page
    from base64 import b32encode
    assert b32encode(appareil.bin_key).decode().rstrip("=") in page.replace(" ", "")


@pytest.mark.django_db
def test_recharger_la_page_d_enrolement_ne_change_pas_la_cle(client):
    utilisateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    client.force_login(utilisateur)

    client.get(reverse("utilisateurs:verification_2fa"))
    cle = TOTPDevice.objects.get(user=utilisateur).key
    client.get(reverse("utilisateurs:verification_2fa"))

    assert TOTPDevice.objects.filter(user=utilisateur).count() == 1 and TOTPDevice.objects.get(user=utilisateur).key == cle


@pytest.mark.django_db
def test_l_enrolement_n_est_confirme_que_par_un_bon_code_et_il_est_journalise(client):
    utilisateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    client.force_login(utilisateur)
    client.get(reverse("utilisateurs:verification_2fa"))
    appareil = TOTPDevice.objects.get(user=utilisateur)

    mauvais = verifier(client, appareil, "000000")
    assert mauvais.status_code == 200 and not TOTPDevice.objects.get(pk=appareil.pk).confirmed

    TOTPDevice.objects.get(pk=appareil.pk).throttle_reset()  # sinon l'échec précédent ralentit l'essai suivant (voir le test de ralentissement)
    bon = verifier(client, appareil, jeton(appareil))
    assert bon.status_code == 302 and TOTPDevice.objects.get(pk=appareil.pk).confirmed
    assert client.get(reverse("admin:index")).status_code == 200
    assert EntreeAudit.objects.filter(action="2fa.activee").count() == 1


@pytest.mark.django_db
def test_un_appareil_non_confirme_ne_donne_aucun_acces(client):
    """Quelqu'un qui connaîtrait le mot de passe ne peut pas s'enrôler à la place du titulaire : il faut encore passer la page, mais surtout
    un appareil jamais confirmé n'ouvre pas la session vérifiée par lui-même."""
    utilisateur, appareil = compte(confirme=False)
    client.force_login(utilisateur)

    assert client.get(reverse("admin:index")).status_code == 302
    assert not otp.session_verifiee(utilisateur, {DEVICE_ID_SESSION_KEY: appareil.persistent_id})


# --- Réinitialisation par un administrateur ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_administrateur_reinitialise_le_deuxieme_facteur_d_un_collegue_qui_perd_son_telephone(client):
    admin = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True)
    admin_appareil = TOTPDevice.objects.create(user=admin, name="a", confirmed=True)
    operateur, _ = compte()
    client.force_login(admin)
    verifier(client, admin_appareil, jeton(admin_appareil))

    reponse = client.post(reverse("admin:utilisateurs_utilisateur_changelist"), {
        "action": "reinitialiser_2fa", "_selected_action": [str(operateur.pk)],
    })

    assert reponse.status_code == 302
    assert not TOTPDevice.objects.filter(user=operateur).exists()  # il devra s'enrôler de nouveau à sa prochaine connexion
    assert EntreeAudit.objects.filter(action="2fa.reinitialisee").count() == 1


@pytest.mark.django_db
def test_un_operateur_ne_peut_pas_reinitialiser_le_deuxieme_facteur(client):
    operateur, appareil = compte()
    cible, _ = compte()
    client.force_login(operateur)
    verifier(client, appareil, jeton(appareil))

    client.post(reverse("admin:utilisateurs_utilisateur_changelist"), {
        "action": "reinitialiser_2fa", "_selected_action": [str(cible.pk)],
    })

    assert TOTPDevice.objects.filter(user=cible).exists()


# --- WebSocket de commande ---------------------------------------------------------------------------------------------------------


def test_la_production_exige_le_deuxieme_facteur():
    import importlib

    assert importlib.import_module("config.settings.base").EXIGER_2FA is True
