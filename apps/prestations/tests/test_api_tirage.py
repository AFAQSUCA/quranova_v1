"""Tests de l'API de l'écran de tirage (§8.5 ; REC-06, REC-07, REC-14, REC-25 ; D31, D34)."""
import json
import uuid
from datetime import date

import pytest
from django.urls import reverse

from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_participation, creer_utilisateur
from apps.prestations import terminaux
from apps.prestations.models import Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_terminal_de_test
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

URL_ETAT, URL_TIRER = reverse("prestations:api_etat"), reverse("prestations:api_tirer")


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.fixture
def poste(epreuve):
    """(épreuve, terminal, en-têtes d'authentification, opérateur)."""
    terminal, jeton, _ = creer_terminal_de_test(epreuve)
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    return epreuve, terminal, {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}, operateur


def appeler(epreuve, terminal, operateur, **champs):
    prestation = creer_prestation(epreuve, session=terminal.session, **champs)
    terminaux.appeler_prestation(terminal, prestation, operateur)
    return prestation


def tirer(client, en_tetes, corps=None):
    corps = {"id_demande": str(uuid.uuid4())} if corps is None else corps
    return client.post(URL_TIRER, data=json.dumps(corps), content_type="application/json", **en_tetes)


# --- Authentification (D31) ----------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("en_tete", [{}, {"HTTP_AUTHORIZATION": "Bearer faux"}, {"HTTP_AUTHORIZATION": "Basic abc"},
                                      {"HTTP_AUTHORIZATION": "Bearer "}])
def test_sans_jeton_valide_les_deux_routes_repondent_401(client, en_tete):
    assert client.get(URL_ETAT, **en_tete).status_code == 401
    reponse = client.post(URL_TIRER, data="{}", content_type="application/json", **en_tete)
    assert reponse.status_code == 401 and reponse.json()["code"] == "terminal_inconnu"


@pytest.mark.django_db
def test_un_terminal_revoque_est_refuse(client, poste):
    _, terminal, en_tetes, _ = poste
    terminaux.revoquer_terminal(terminal)

    assert client.get(URL_ETAT, **en_tetes).status_code == 401


@pytest.mark.django_db
def test_un_compte_connecte_sans_jeton_n_a_aucun_acces(client, poste):
    """Un cookie de session (opérateur, responsable...) ne remplace pas le jeton du terminal."""
    client.force_login(creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True))

    assert client.get(URL_ETAT).status_code == 401


@pytest.mark.django_db
def test_les_methodes_non_prevues_sont_refusees(client, poste):
    _, _, en_tetes, _ = poste

    assert client.post(URL_ETAT, **en_tetes).status_code == 405
    assert client.get(URL_TIRER, **en_tetes).status_code == 405


# --- État ----------------------------------------------------------------------


@pytest.mark.django_db
def test_l_etat_sans_appel(client, poste):
    _, _, en_tetes, _ = poste

    reponse = client.get(URL_ETAT, **en_tetes)

    assert reponse.status_code == 200 and reponse.json() == {"terminal": "Tablette 1", "appel": None}
    assert "no-store" in reponse["Cache-Control"]


@pytest.mark.django_db
def test_l_etat_apres_l_appel_de_l_operateur(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    prestation = appeler(epreuve, terminal, operateur)

    appel = client.get(URL_ETAT, **en_tetes).json()["appel"]

    assert appel["prenom"] == prestation.participation.candidat.prenom
    assert appel["peut_tirer"] is True and "nom" not in appel


# --- Tirage ----------------------------------------------------------------------


@pytest.mark.django_db
def test_rec06_un_tirage_renvoie_le_libelle_de_la_serie(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)

    reponse = tirer(client, en_tetes)

    corps = reponse.json()
    assert reponse.status_code == 200
    assert corps["tirage"]["serie"].startswith("Série ") and corps["tirage"]["rang"] == 1
    assert corps["etat"]["appel"]["peut_tirer"] is False
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_rec07_deux_envois_de_la_meme_demande_ne_creent_qu_un_tirage(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)
    demande = {"id_demande": str(uuid.uuid4())}

    premier, second = tirer(client, en_tetes, demande), tirer(client, en_tetes, demande)

    assert premier.status_code == second.status_code == 200
    assert premier.json()["tirage"] == second.json()["tirage"]
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_rec25_le_client_ne_peut_pas_designer_une_autre_prestation(client, poste):
    """Même si le corps contient un identifiant de prestation, seul le candidat appelé tire."""
    epreuve, terminal, en_tetes, operateur = poste
    appelee = appeler(epreuve, terminal, operateur)
    autre = creer_prestation(epreuve, session=terminal.session)

    tirer(client, en_tetes, {"id_demande": str(uuid.uuid4()), "prestation": str(autre.pk), "prestation_id": str(autre.pk)})

    assert appelee.tirages.count() == 1 and autre.tirages.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("corps", [{}, {"id_demande": "pas-un-uuid"}, {"id_demande": 12}, {"id_demande": None}, []])
def test_requete_invalide_400(client, poste, corps):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)

    reponse = tirer(client, en_tetes, corps)

    assert reponse.status_code == 400 and reponse.json()["code"] == "requete_invalide"
    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_corps_qui_n_est_pas_du_json(client, poste):
    _, _, en_tetes, _ = poste

    reponse = client.post(URL_TIRER, data="pas du json", content_type="application/json", **en_tetes)

    assert reponse.status_code == 400


@pytest.mark.django_db
def test_sans_candidat_appele_409_pas_d_appel(client, poste):
    _, _, en_tetes, _ = poste

    reponse = tirer(client, en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "pas_d_appel"


@pytest.mark.django_db
def test_lot_epuise_409(client):
    epreuve = creer_epreuve_ouverte(series=1)
    terminal, jeton, _ = creer_terminal_de_test(epreuve)
    en_tetes = {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}
    operateur = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR)
    appeler(epreuve, terminal, operateur)
    from apps.prestations.services import effectuer_tirage

    effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())  # un autre candidat prend l'unique série

    reponse = tirer(client, en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "lot_epuise"


@pytest.mark.django_db
def test_rm28_mineur_sans_consentement_409(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    mineur = creer_candidat(epreuve.organisation, date_naissance=date(2015, 5, 1))
    participation = creer_participation(epreuve.categorie, mineur, statut=Participation.Statut.ADMIS)
    appeler(epreuve, terminal, operateur, participation=participation)

    reponse = tirer(client, en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "consentement_manquant"
    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_la_reponse_ne_contient_aucun_texte_de_verset_ni_de_question(client, poste):
    epreuve, terminal, en_tetes, operateur = poste
    appeler(epreuve, terminal, operateur)

    texte = tirer(client, en_tetes).content.decode()

    assert "Question de test" not in texte and "enonce" not in texte and "texte" not in texte


# --- Page ----------------------------------------------------------------------


@pytest.mark.django_db
def test_la_page_de_tirage_se_charge_sans_authentification(client):
    """La page est publique et vide ; toutes les données passent par l'API, protégée par le jeton."""
    reponse = client.get(reverse("prestations:ecran_tirage"))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200 and 'id="app"' in contenu and "tirage.js" in contenu
