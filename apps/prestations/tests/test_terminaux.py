"""Tests des terminaux de tirage : jeton, appel d'un candidat par l'opérateur, état affiché (§8.6, §15 ; D31, D34)."""
import json
import uuid

import pytest
from django.utils import timezone

from apps.commun.tests.outils import creer_mission, creer_session, creer_utilisateur
from apps.prestations import terminaux
from apps.prestations.exceptions import AppelInvalideError, PasDAppelError, TerminalInvalideError
from apps.prestations.models import Prestation, TerminalTirage, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.fixture
def terminal(epreuve):
    session = creer_session(epreuve.categorie.concours)
    objet, jeton = terminaux.creer_terminal(session, "Tablette 1")
    objet.jeton_de_test = jeton
    return objet


def operateur_de(epreuve):
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    return operateur


def prestation_pour(epreuve, terminal, **champs):
    return creer_prestation(epreuve, session=terminal.session, **champs)


# --- Jeton (D31) ---------------------------------------------------------------


@pytest.mark.django_db
def test_d31_le_jeton_n_est_jamais_stocke_en_clair(epreuve):
    terminal, jeton = terminaux.creer_terminal(creer_session(epreuve.categorie.concours), "T")

    assert len(jeton) >= 40
    assert jeton not in terminal.empreinte and len(terminal.empreinte) == 64
    assert TerminalTirage.objects.filter(empreinte=jeton).count() == 0
    assert terminal.organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_deux_terminaux_ont_des_jetons_differents(epreuve):
    session = creer_session(epreuve.categorie.concours)

    (_, premier), (_, second) = terminaux.creer_terminal(session, "A"), terminaux.creer_terminal(session, "B")

    assert premier != second


@pytest.mark.django_db
def test_un_jeton_valide_identifie_le_terminal_et_note_l_activite(terminal):
    trouve = terminaux.authentifier_terminal(terminal.jeton_de_test)

    assert trouve == terminal
    terminal.refresh_from_db()
    assert terminal.derniere_activite is not None


@pytest.mark.django_db
@pytest.mark.parametrize("jeton", ["", None, "n-importe-quoi", "a" * 43])
def test_un_jeton_inconnu_ou_absent_est_refuse(terminal, jeton):
    with pytest.raises(TerminalInvalideError):
        terminaux.authentifier_terminal(jeton)


@pytest.mark.django_db
def test_un_terminal_revoque_est_refuse(terminal):
    terminaux.revoquer_terminal(terminal)

    with pytest.raises(TerminalInvalideError):
        terminaux.authentifier_terminal(terminal.jeton_de_test)


# --- Appel d'un candidat par l'opérateur ----------------------------------------


@pytest.mark.django_db
def test_l_operateur_appelle_un_candidat_sur_le_terminal(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)

    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))

    terminal.refresh_from_db()
    assert terminal.prestation_appelee == prestation


@pytest.mark.django_db
def test_appeler_un_autre_candidat_remplace_le_precedent(epreuve, terminal):
    operateur = operateur_de(epreuve)
    premiere, seconde = prestation_pour(epreuve, terminal), prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, premiere, operateur)

    terminaux.appeler_prestation(terminal, seconde, operateur)

    terminal.refresh_from_db()
    assert terminal.prestation_appelee == seconde


@pytest.mark.django_db
def test_rm20_un_operateur_sans_acces_a_la_mission_ne_peut_pas_appeler(epreuve, terminal):
    etranger = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=creer_mission(), utilisateur=etranger)

    with pytest.raises(AppelInvalideError, match="accès"):
        terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), etranger)

    terminal.refresh_from_db()
    assert terminal.prestation_appelee is None


@pytest.mark.django_db
def test_un_responsable_client_n_appelle_pas_un_candidat(epreuve, terminal):
    responsable = creer_utilisateur(
        Utilisateur.Role.RESPONSABLE_CLIENT, organisation=epreuve.organisation
    )

    with pytest.raises(AppelInvalideError, match="prestataire"):
        terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), responsable)


@pytest.mark.django_db
def test_une_prestation_d_une_autre_session_ne_peut_pas_etre_appelee(epreuve, terminal):
    autre = creer_prestation(epreuve, session=creer_session(epreuve.categorie.concours))

    with pytest.raises(AppelInvalideError, match="session"):
        terminaux.appeler_prestation(terminal, autre, operateur_de(epreuve))


@pytest.mark.django_db
def test_seule_une_prestation_en_attente_peut_etre_appelee(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal, etat=Prestation.Etat.EN_NOTATION)

    with pytest.raises(AppelInvalideError, match="attente"):
        terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))


@pytest.mark.django_db
def test_un_terminal_revoque_ne_peut_plus_appeler(epreuve, terminal):
    terminaux.revoquer_terminal(terminal)

    with pytest.raises(AppelInvalideError, match="révoqué"):
        terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), operateur_de(epreuve))


@pytest.mark.django_db
def test_liberer_le_terminal(epreuve, terminal):
    operateur = operateur_de(epreuve)
    terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), operateur)

    terminaux.liberer_terminal(terminal)

    terminal.refresh_from_db()
    assert terminal.prestation_appelee is None


# --- Ce que voit la tablette ------------------------------------------------------


@pytest.mark.django_db
def test_l_etat_sans_appel(terminal):
    assert terminaux.etat_du_terminal(terminal) == {"terminal": "Tablette 1", "appel": None}


@pytest.mark.django_db
def test_d34_l_etat_montre_le_numero_et_le_prenom_mais_ni_le_nom_ni_aucun_verset(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))

    etat = terminaux.etat_du_terminal(terminal)

    assert etat["appel"]["numero_candidat"] == prestation.participation.numero_candidat
    assert etat["appel"]["prenom"] == prestation.participation.candidat.prenom
    assert etat["appel"]["epreuve"] == epreuve.nom
    assert etat["appel"]["tirages_prevus"] == 1 and etat["appel"]["tirages"] == []
    texte = json.dumps(etat, ensure_ascii=False)
    assert prestation.participation.candidat.nom not in texte  # RGPD : écran visible de la salle
    assert not ({"texte", "versets", "questions", "enonce"} & set(texte.replace('"', " ").split()))


@pytest.mark.django_db
def test_l_etat_apres_tirage_donne_le_libelle_de_la_serie(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))
    terminaux.tirer_pour_terminal(terminal, uuid.uuid4())

    appel = terminaux.etat_du_terminal(terminal)["appel"]

    assert appel["etat"] == "tire" and appel["peut_tirer"] is False
    assert appel["tirages"][0]["serie"].startswith("Série ")


@pytest.mark.django_db
def test_peut_tirer_tant_qu_il_reste_un_tirage(epreuve, terminal):
    prestation = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, prestation, operateur_de(epreuve))

    assert terminaux.etat_du_terminal(terminal)["appel"]["peut_tirer"] is True


# --- Tirage depuis le terminal ------------------------------------------------------


@pytest.mark.django_db
def test_sans_appel_le_terminal_ne_peut_pas_tirer(terminal):
    with pytest.raises(PasDAppelError):
        terminaux.tirer_pour_terminal(terminal, uuid.uuid4())

    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_le_tirage_concerne_seulement_le_candidat_appele_et_note_le_terminal(epreuve, terminal):
    appele = prestation_pour(epreuve, terminal)
    autre = prestation_pour(epreuve, terminal)
    terminaux.appeler_prestation(terminal, appele, operateur_de(epreuve))

    tirage = terminaux.tirer_pour_terminal(terminal, uuid.uuid4())

    assert tirage.prestation == appele and tirage.terminal == "Tablette 1"
    assert autre.tirages.count() == 0


@pytest.mark.django_db
def test_rec07_la_meme_demande_renvoie_le_meme_tirage(epreuve, terminal):
    terminaux.appeler_prestation(terminal, prestation_pour(epreuve, terminal), operateur_de(epreuve))
    demande = uuid.uuid4()

    premier = terminaux.tirer_pour_terminal(terminal, demande)
    second = terminaux.tirer_pour_terminal(terminal, demande)

    assert premier == second and Tirage.objects.count() == 1
