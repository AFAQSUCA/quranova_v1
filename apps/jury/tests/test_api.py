"""Tests de l'API du juré (§10.2 ; RM-15, REC-11, REC-12, REC-14, REC-25 ; D5)."""
import json
import uuid

import pytest
from django.urls import reverse

from apps.commun.tests.outils import creer_critere, creer_epreuve, creer_jure, creer_session
from apps.jury import connexion, services
from apps.jury.models import AffectationJury, Evaluation, Note
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage


@pytest.fixture
def poste(db):
    """(session, jure, en-têtes, prestation en notation, critères, épreuve)."""
    epreuve = creer_epreuve_ouverte(series=2)
    criteres = [creer_critere(epreuve, maximum=m) for m in (10, 10, 5)]
    session = creer_session(epreuve.categorie.concours)
    jure = creer_jure(epreuve.organisation)
    AffectationJury.objects.create(jure=jure, epreuve=epreuve)
    _, code = services.generer_code(jure, session)
    _, jeton = connexion.ouvrir_connexion(code, session)
    prestation = creer_prestation(epreuve, session=session, etat=Prestation.Etat.EN_NOTATION)
    creer_tirage(prestation, epreuve.lot.series.first())
    return session, jure, {"HTTP_AUTHORIZATION": f"Bearer {jeton}"}, prestation, criteres, epreuve


def url(nom, session, prestation=None):
    args = [session.pk] + ([prestation.pk] if prestation else [])
    return reverse(f"jury:{nom}", args=args)


def put(client, session, prestation, en_tetes, corps):
    return client.put(url("api_evaluation", session, prestation), data=json.dumps(corps), content_type="application/json", **en_tetes)


def post(client, adresse, en_tetes, corps=None):
    return client.post(adresse, data=json.dumps(corps or {}), content_type="application/json", **en_tetes)


# --- Connexion ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_code_donne_un_jeton(client):
    session = creer_session()
    jure = creer_jure(session.organisation)
    _, code = services.generer_code(jure, session)

    reponse = post(client, url("api_connexion", session), {}, {"code": code.lower()})

    corps = reponse.json()
    assert reponse.status_code == 200 and len(corps["jeton"]) >= 40
    assert corps["jure"] == {"prenom": jure.prenom, "nom": jure.nom}


@pytest.mark.django_db
def test_un_code_faux_donne_401_avec_un_message_vague(client):
    session = creer_session()

    reponse = post(client, url("api_connexion", session), {}, {"code": "ZZZZ-ZZZZ"})

    assert reponse.status_code == 401 and reponse.json()["code"] == "code_invalide"
    assert "inconnu" not in reponse.json()["message"].lower()


@pytest.mark.django_db
def test_d5_apres_cinq_essais_faux_429_meme_avec_le_bon_code(client):
    session = creer_session()
    _, code = services.generer_code(creer_jure(session.organisation), session)
    for _ in range(5):
        post(client, url("api_connexion", session), {}, {"code": "ZZZZ-ZZZZ"})

    reponse = post(client, url("api_connexion", session), {}, {"code": code})

    assert reponse.status_code == 429 and reponse.json()["attente_secondes"] > 0


@pytest.mark.django_db
@pytest.mark.parametrize("corps", [{}, {"code": 12}, []])
def test_connexion_requete_invalide(client, corps):
    assert post(client, url("api_connexion", creer_session()), {}, corps).status_code == 400


# --- Authentification ------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("en_tete", [{}, {"HTTP_AUTHORIZATION": "Bearer faux"}, {"HTTP_AUTHORIZATION": "Basic x"}])
def test_sans_jeton_valide_toutes_les_routes_repondent_401(client, poste, en_tete):
    session, _, _, prestation, _, _ = poste

    assert client.get(url("api_prestations", session), **en_tete).status_code == 401
    assert client.get(url("api_evaluation", session, prestation), **en_tete).status_code == 401
    assert post(client, url("api_valider", session, prestation), en_tete).status_code == 401


@pytest.mark.django_db
def test_le_jeton_d_une_session_n_ouvre_pas_une_autre_session(client, poste):
    session, _, en_tetes, _, _, epreuve = poste
    autre = creer_session(session.concours)

    assert client.get(url("api_prestations", autre), **en_tetes).status_code == 401


# --- Prestations et évaluation -----------------------------------------------------------------


@pytest.mark.django_db
def test_la_liste_ne_contient_que_les_prestations_des_epreuves_du_jure(client, poste):
    session, jure, en_tetes, prestation, _, epreuve = poste
    autre_epreuve = creer_epreuve(epreuve.categorie)  # une autre épreuve du même concours, sans ce juré
    creer_prestation(autre_epreuve, session=session, etat=Prestation.Etat.EN_NOTATION)  # épreuve non affectée
    creer_prestation(epreuve, session=session, etat=Prestation.Etat.EN_ATTENTE)  # pas encore affichée

    liste = client.get(url("api_prestations", session), **en_tetes).json()["prestations"]

    assert [p["id"] for p in liste] == [str(prestation.pk)]
    assert liste[0]["evaluation"] == "non_commencee"
    assert "nom" not in liste[0] and liste[0]["prenom"] == prestation.participation.candidat.prenom


@pytest.mark.django_db
def test_rec25_une_prestation_non_affectee_ou_d_une_autre_session_donne_404(client, poste):
    session, _, en_tetes, _, _, _ = poste
    autre_epreuve = creer_epreuve_ouverte(series=1)
    non_affectee = creer_prestation(autre_epreuve, session=creer_session(autre_epreuve.categorie.concours), etat=Prestation.Etat.EN_NOTATION)
    inexistante = type("P", (), {"pk": uuid.uuid4()})()

    assert client.get(url("api_evaluation", session, non_affectee), **en_tetes).status_code == 404
    assert client.get(url("api_evaluation", session, inexistante), **en_tetes).status_code == 404


@pytest.mark.django_db
def test_rec11_rec12_brouillon_serveur_et_note_manquante_distincte_de_zero(client, poste):
    session, jure, en_tetes, prestation, criteres, _ = poste

    reponse = put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): "0", str(criteres[1].pk): "7,5"}, "observation": "RAS"})

    etat = reponse.json()
    valeurs = {c["critere"]: c["valeur"] for c in etat["criteres"]}
    assert reponse.status_code == 200
    assert valeurs[str(criteres[0].pk)] == "0.00"  # un zéro est une note
    assert valeurs[str(criteres[1].pk)] == "7.50"
    assert valeurs[str(criteres[2].pk)] is None  # manquante : null, pas zéro
    assert etat["complete"] is False and etat["manquants"] == [criteres[2].libelle]
    assert etat["observation"] == "RAS" and etat["peut_valider"] is False
    # Le brouillon est côté serveur : un autre appel (tablette redémarrée, REC-23) le retrouve.
    relu = client.get(url("api_evaluation", session, prestation), **en_tetes).json()
    assert relu["criteres"] == etat["criteres"]


@pytest.mark.django_db
def test_une_note_hors_bareme_donne_400(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste

    reponse = put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): "11"}})

    assert reponse.status_code == 400 and reponse.json()["code"] == "note_invalide"
    assert Note.objects.count() == 0


@pytest.mark.django_db
def test_l_api_ne_lit_jamais_d_identifiant_de_jure_dans_le_corps(client, poste):
    """REC-25 : même si le corps désigne un autre juré, seule l'évaluation du juré authentifié est écrite."""
    session, jure, en_tetes, prestation, criteres, epreuve = poste
    autre = creer_jure(epreuve.organisation)
    AffectationJury.objects.create(jure=autre, epreuve=epreuve)

    put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): 5}, "jure": str(autre.pk), "jure_id": autre.pk if False else str(autre.pk)})

    assert Evaluation.objects.get().jure == jure


@pytest.mark.django_db
def test_validation_incomplete_409_avec_la_liste_puis_complete_200(client, poste):
    session, jure, en_tetes, prestation, criteres, _ = poste
    put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): 9}})

    refus = post(client, url("api_valider", session, prestation), en_tetes)
    assert refus.status_code == 409 and refus.json()["code"] == "evaluation_incomplete"
    assert refus.json()["manquants"] == [criteres[1].libelle, criteres[2].libelle]

    complet = put(client, session, prestation, en_tetes, {"notes": {str(criteres[1].pk): 8, str(criteres[2].pk): 4}})
    assert complet.json()["peut_valider"] is True
    ok = post(client, url("api_valider", session, prestation), en_tetes)
    assert ok.status_code == 200 and ok.json()["statut"] == "validee" and ok.json()["peut_saisir"] is False


@pytest.mark.django_db
def test_apres_validation_la_modification_est_refusee_409(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste
    put(client, session, prestation, en_tetes, {"notes": {str(c.pk): 3 for c in criteres}})
    post(client, url("api_valider", session, prestation), en_tetes)

    reponse = put(client, session, prestation, en_tetes, {"notes": {str(criteres[0].pk): 1}})

    assert reponse.status_code == 409 and reponse.json()["code"] == "evaluation_validee"


@pytest.mark.django_db
def test_la_validation_avant_la_fin_de_la_prestation_est_refusee(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste
    Prestation.objects.filter(pk=prestation.pk).update(etat=Prestation.Etat.EN_AFFICHAGE)
    put(client, session, prestation, en_tetes, {"notes": {str(c.pk): 3 for c in criteres}})

    reponse = post(client, url("api_valider", session, prestation), en_tetes)

    assert reponse.status_code == 409 and reponse.json()["code"] == "pas_encore"


@pytest.mark.django_db
def test_demande_de_correction_via_l_api(client, poste):
    session, _, en_tetes, prestation, criteres, _ = poste
    put(client, session, prestation, en_tetes, {"notes": {str(c.pk): 3 for c in criteres}})
    post(client, url("api_valider", session, prestation), en_tetes)

    reponse = post(client, url("api_correction", session, prestation), en_tetes,
                   {"critere": str(criteres[0].pk), "valeur": "5", "motif": "Erreur de saisie"})
    sans_motif = post(client, url("api_correction", session, prestation), en_tetes, {"critere": str(criteres[1].pk), "valeur": "5", "motif": ""})

    assert reponse.status_code == 201
    assert reponse.json()["corrections"][0]["statut"] == "demandee" and reponse.json()["corrections"][0]["ancienne"] == "3.00"
    assert sans_motif.status_code == 400


@pytest.mark.django_db
def test_les_methodes_non_prevues_sont_refusees(client, poste):
    session, _, en_tetes, prestation, _, _ = poste

    assert client.post(url("api_prestations", session), **en_tetes).status_code == 405
    assert client.get(url("api_valider", session, prestation), **en_tetes).status_code == 405


@pytest.mark.django_db
def test_la_page_du_jure_est_publique_et_vide(client, poste):
    session = poste[0]

    reponse = client.get(reverse("jury:ecran_jury", args=[session.pk]))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200 and 'id="app"' in contenu and "jury.js" in contenu
    assert client.get(reverse("jury:ecran_jury", args=[uuid.uuid4()])).status_code == 404
