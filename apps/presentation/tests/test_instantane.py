"""Tests de l'instantané et de sa projection par rôle (protocole §3.1 ; RM-14, D15)."""
import pytest

from apps.concours.models import Epreuve
from apps.presentation import instantane
from apps.presentation.tests.outils import commande, creer_prestation_tiree, operateur_de, presentation_demarree, texte_du_verset


def avancer(session, operateur, version, n):
    for i in range(n):
        version = commande(session, "suivante", version + i, auteur=operateur).version - i
    return version


@pytest.mark.django_db
def test_sans_presentation_active(db):
    from apps.commun.tests.outils import creer_session

    message = instantane.construire_instantane(creer_session(), "operateur")

    assert message["prestation"] is None and message["version"] == 0 and message["diapositive"] is None


@pytest.mark.django_db
def test_presentation_preparee_pas_encore_de_diapositive():
    prestation, epreuve, _ = creer_prestation_tiree()
    operateur = operateur_de(epreuve)
    commande(prestation.session, "preparer", auteur=operateur, prestation=prestation)

    message = instantane.construire_instantane(prestation.session, "operateur")

    assert (message["phase"], message["version"], message["diapositive"]) == ("preparee", 1, None)
    assert message["prestation"]["candidat"] == {
        "numero": prestation.participation.numero_candidat, "prenom": prestation.participation.candidat.prenom,
    }
    assert message["prestation"]["serie"] == "Série 1" and message["instantane"] is True


@pytest.mark.django_db
def test_l_intercalaire_ne_contient_jamais_de_texte_coranique():
    prestation, session, operateur, _ = presentation_demarree()  # diapositive 0 : intercalaire

    message = instantane.construire_instantane(session, "operateur")

    diapositive = message["diapositive"]
    assert diapositive["type"] == "intercalaire_question" and "texte" not in diapositive
    assert diapositive["question"] == {"rang": 1, "total": 2, "libelle": "Sourate 2, versets 3 à 5"}
    assert (diapositive["index"], diapositive["total"]) == (0, 10)


@pytest.mark.django_db
def test_l_operateur_recoit_le_texte_du_corpus_et_la_reference():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)

    diapositive = instantane.construire_instantane(session, "operateur")["diapositive"]

    assert diapositive["type"] == "verset" and diapositive["reference"] == "2:3"
    assert diapositive["segment"] == {"rang": 1, "total": 1}
    assert diapositive["texte"] == texte_du_verset(2, 3)


@pytest.mark.django_db
def test_d15_la_scene_ne_recoit_pas_le_texte_si_l_epreuve_ne_l_affiche_pas():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)
    assert prestation.epreuve.affichage_scene is False  # défaut (D15)

    diapositive = instantane.construire_instantane(session, "scene")["diapositive"]

    assert diapositive["type"] == "verset" and "texte" not in diapositive


@pytest.mark.django_db
def test_la_scene_recoit_le_texte_quand_l_epreuve_l_affiche():
    prestation, session, operateur, _ = presentation_demarree()
    Epreuve.objects.filter(pk=prestation.epreuve_id).update(affichage_scene=True)
    commande(session, "suivante", 2, auteur=operateur)

    diapositive = instantane.construire_instantane(session, "scene")["diapositive"]

    assert diapositive["texte"] == texte_du_verset(2, 3)


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["candidat", "jury", "tirage", ""])
def test_rm14_aucun_autre_role_ne_recoit_de_texte(role):
    prestation, session, operateur, _ = presentation_demarree()
    Epreuve.objects.filter(pk=prestation.epreuve_id).update(affichage_scene=True)
    commande(session, "suivante", 2, auteur=operateur)

    diapositive = instantane.construire_instantane(session, role)["diapositive"]

    assert "texte" not in diapositive


@pytest.mark.django_db
def test_le_rejeu_et_la_version_sont_dans_l_instantane():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "reafficher", 2, auteur=operateur)

    message = instantane.construire_instantane(session, "operateur", instantane=False)

    assert (message["version"], message["rejeu"], message["instantane"]) == (3, 1, False)
