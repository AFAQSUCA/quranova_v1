"""Tests des pages de scène et de commande et de la liste des prestations (§9, REC-25, REC-29)."""
import pytest
from django.urls import reverse

from apps.commun.tests.outils import creer_mission, creer_session, creer_utilisateur
from apps.presentation.tests.outils import creer_prestation_tiree, operateur_de
from apps.prestations.tests.outils import creer_prestation
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def poste(db):
    prestation, epreuve, _ = creer_prestation_tiree()
    return prestation, prestation.session, operateur_de(epreuve)


def url(nom, session):
    return reverse(f"presentation:{nom}", args=[session.pk])


@pytest.mark.django_db
def test_la_page_de_scene_est_publique_et_vide(client, poste):
    _, session, _ = poste

    reponse = client.get(url("ecran_scene", session))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200 and 'id="app"' in contenu and "scene.js" in contenu


@pytest.mark.django_db
def test_la_commande_renvoie_un_anonyme_vers_la_connexion(client, poste):
    _, session, _ = poste

    reponse = client.get(url("ecran_commande", session))

    assert reponse.status_code == 302 and "login" in reponse.url


@pytest.mark.django_db
def test_la_commande_s_ouvre_pour_l_operateur_affecte(client, poste):
    _, session, operateur = poste
    client.force_login(operateur)

    reponse = client.get(url("ecran_commande", session))

    assert reponse.status_code == 200 and "commande.js" in reponse.content.decode()


@pytest.mark.django_db
def test_rec29_un_operateur_sans_acces_a_la_mission_obtient_404(client, poste):
    _, session, _ = poste
    etranger = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=creer_mission(), utilisateur=etranger)
    client.force_login(etranger)

    assert client.get(url("ecran_commande", session)).status_code == 404
    assert client.get(url("prestations", session)).status_code == 404


@pytest.mark.django_db
def test_un_responsable_client_ne_commande_pas_le_diaporama(client, poste):
    _, session, _ = poste
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=session.organisation))

    assert client.get(url("ecran_commande", session)).status_code == 404


@pytest.mark.django_db
def test_une_session_inexistante_donne_404(client, poste):
    _, _, operateur = poste
    client.force_login(operateur)

    reponse = client.get(reverse("presentation:ecran_commande", args=["00000000-0000-0000-0000-000000000000"]))

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_la_liste_des_prestations_exige_une_connexion(client, poste):
    _, session, _ = poste

    assert client.get(url("prestations", session)).status_code == 401


@pytest.mark.django_db
def test_la_liste_des_prestations_donne_le_numero_et_le_prenom_sans_nom_de_famille(client, poste):
    prestation, session, operateur = poste
    client.force_login(operateur)

    reponse = client.get(url("prestations", session))

    (ligne,) = reponse.json()["prestations"]
    assert ligne["id"] == str(prestation.pk) and ligne["etat"] == "tire"
    assert ligne["prenom"] == prestation.participation.candidat.prenom
    assert prestation.participation.candidat.nom not in reponse.content.decode()
    assert "no-store" in reponse["Cache-Control"]


@pytest.mark.django_db
def test_la_liste_ne_contient_que_les_prestations_de_la_session(client, poste):
    prestation, session, operateur = poste
    creer_prestation(prestation.epreuve, session=creer_session(session.concours))  # autre session du même concours
    client.force_login(operateur)

    assert len(client.get(url("prestations", session)).json()["prestations"]) == 1
