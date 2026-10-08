"""Tests du consumer WebSocket (§9.4, §13.5 ; REC-10, REC-14, REC-15, REC-24, REC-25).

Vraies transactions et vraie base : le consumer lit et écrit dans des threads distincts.
"""
import asyncio
import uuid
from datetime import date

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.commun.tests.outils import creer_session, creer_utilisateur
from apps.concours.models import Epreuve
from apps.prestations import terminaux
from apps.prestations.models import Terminal
from apps.presentation import consumers
from apps.presentation.routing import websocket_urlpatterns
from apps.presentation.tests.outils import creer_prestation_tiree, operateur_de, texte_du_verset
from apps.utilisateurs.models import Utilisateur

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]

APPLICATION = URLRouter(websocket_urlpatterns)


@pytest.fixture
def poste():
    """(prestation, session, opérateur, jeton de scène) : une prestation tirée, prête à être préparée."""
    prestation, epreuve, _ = creer_prestation_tiree()
    operateur = operateur_de(epreuve)
    _, jeton = terminaux.creer_terminal(prestation.session, "Scène 1", Terminal.Type.SCENE)
    return prestation, prestation.session, operateur, jeton


def communicateur(session, utilisateur=None, session_id=None):
    comm = WebsocketCommunicator(APPLICATION, f"/ws/presentation/{session_id or session.pk}/")
    comm.scope["user"] = utilisateur or AnonymousUser()
    return comm


async def operateur_connecte(session, operateur):
    comm = communicateur(session, operateur)
    connecte, _ = await comm.connect()
    assert connecte
    return comm, await comm.receive_json_from()


async def scene_connectee(session, jeton):
    comm = communicateur(session)
    assert (await comm.connect())[0]
    await comm.send_json_to({"type": "auth", "jeton": jeton})
    return comm, await comm.receive_json_from()


def commande(action, version=None, **champs):
    return {"type": "commande", "id": str(uuid.uuid4()), "version_attendue": version, "action": action, **champs}


async def preparer_et_demarrer(comm, prestation):
    await comm.send_json_to(commande("preparer", prestation=str(prestation.pk)))
    ack = await comm.receive_json_from()
    etat = await comm.receive_json_from()
    await comm.send_json_to(commande("demarrer", 1))
    return ack, etat


# --- Connexion et authentification ------------------------------------------------


async def test_l_operateur_recoit_l_instantane_des_la_connexion(poste):
    _, session, operateur, _ = poste

    comm, message = await operateur_connecte(session, operateur)

    assert message["type"] == "etat" and message["instantane"] is True
    assert message["prestation"] is None and message["version"] == 0
    await comm.disconnect()


async def test_la_scene_s_authentifie_par_son_premier_message_puis_recoit_l_instantane(poste):
    _, session, _, jeton = poste

    comm, message = await scene_connectee(session, jeton)

    assert message["type"] == "etat" and message["session"] == str(session.pk)
    await comm.disconnect()


async def test_la_scene_ne_recoit_rien_avant_de_s_authentifier(poste):
    _, session, _, _ = poste
    comm = communicateur(session)
    await comm.connect()

    assert await comm.receive_nothing(timeout=0.3)
    await comm.disconnect()


async def test_un_jeton_invalide_ferme_la_connexion_4401(poste):
    _, session, _, _ = poste
    comm = communicateur(session)
    await comm.connect()

    await comm.send_json_to({"type": "auth", "jeton": "n-importe-quoi"})

    assert (await comm.receive_output())["code"] == consumers.CODE_NON_AUTHENTIFIE


async def test_le_jeton_d_une_tablette_de_tirage_n_ouvre_pas_la_presentation(poste):
    prestation, session, _, _ = poste
    _, jeton_tirage = await asyncio.to_thread(terminaux.creer_terminal, session, "Tablette")
    comm = communicateur(session)
    await comm.connect()

    await comm.send_json_to({"type": "auth", "jeton": jeton_tirage})

    assert (await comm.receive_output())["code"] == consumers.CODE_NON_AUTHENTIFIE


async def test_rec25_le_jeton_d_une_autre_session_est_refuse_4403(poste):
    _, session, _, _ = poste
    autre = await asyncio.to_thread(lambda: creer_session(session.concours))
    _, jeton_autre = await asyncio.to_thread(terminaux.creer_terminal, autre, "Scène autre", Terminal.Type.SCENE)
    comm = communicateur(session)
    await comm.connect()

    await comm.send_json_to({"type": "auth", "jeton": jeton_autre})

    assert (await comm.receive_output())["code"] == consumers.CODE_INTERDIT


async def test_sans_authentification_dans_le_delai_la_connexion_est_fermee_4408(poste, monkeypatch):
    monkeypatch.setattr(consumers, "DELAI_AUTHENTIFICATION_S", 0.2)
    _, session, _, _ = poste
    comm = communicateur(session)
    await comm.connect()

    assert (await comm.receive_output(timeout=2))["code"] == consumers.CODE_DELAI


async def test_un_autre_message_avant_l_authentification_ferme_la_connexion(poste):
    _, session, _, _ = poste
    comm = communicateur(session)
    await comm.connect()

    await comm.send_json_to(commande("suivante", 1))

    assert (await comm.receive_output())["code"] == consumers.CODE_NON_AUTHENTIFIE


async def test_un_responsable_client_connecte_n_a_pas_le_droit_de_commander(poste):
    prestation, session, _, _ = poste
    responsable = await asyncio.to_thread(
        lambda: creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, session.organisation)
    )
    comm = communicateur(session, responsable)
    await comm.connect()

    await comm.send_json_to(commande("preparer", prestation=str(prestation.pk)))

    assert (await comm.receive_output())["code"] == consumers.CODE_NON_AUTHENTIFIE  # traité comme anonyme


async def test_une_session_inconnue_est_refusee_4403(poste):
    _, session, operateur, _ = poste
    comm = communicateur(session, operateur, session_id=uuid.uuid4())
    await comm.connect()

    assert (await comm.receive_output())["code"] == consumers.CODE_INTERDIT


# --- Commandes et synchronisation ---------------------------------------------------


async def test_rec10_la_scene_suit_l_operateur_diapositive_par_diapositive(poste):
    prestation, session, operateur, jeton = poste
    op, _ = await operateur_connecte(session, operateur)
    scene, _ = await scene_connectee(session, jeton)

    ack, etat_op = await preparer_et_demarrer(op, prestation)
    assert ack["statut"] == "appliquee" and etat_op["phase"] == "preparee"
    assert (await scene.receive_json_from())["phase"] == "preparee"
    assert (await op.receive_json_from())["type"] == "ack"  # ack de « demarrer »
    assert (await op.receive_json_from())["phase"] == "affichage"
    assert (await scene.receive_json_from())["diapositive"]["index"] == 0

    await op.send_json_to(commande("suivante", 2))
    await op.receive_json_from()  # ack
    vu_operateur = await op.receive_json_from()
    vu_scene = await scene.receive_json_from()

    assert vu_operateur["version"] == vu_scene["version"] == 3
    assert vu_operateur["diapositive"]["index"] == vu_scene["diapositive"]["index"] == 1
    assert vu_scene["instantane"] is False  # diffusion : l'écran anime la transition
    await op.disconnect()
    await scene.disconnect()


async def test_rm14_la_scene_ne_recoit_pas_le_texte_mais_l_operateur_oui(poste):
    prestation, session, operateur, jeton = poste
    op, _ = await operateur_connecte(session, operateur)
    scene, _ = await scene_connectee(session, jeton)
    await preparer_et_demarrer(op, prestation)
    for _ in range(2):  # ack + diffusion pour l'opérateur ; deux diffusions pour la scène
        await scene.receive_json_from()
        await op.receive_json_from()
    await op.send_json_to(commande("suivante", 2))
    await op.receive_json_from()

    vu_operateur = await op.receive_json_from()
    vu_scene = await scene.receive_json_from()

    assert vu_operateur["diapositive"]["texte"] == texte_du_verset(2, 3)
    assert "texte" not in vu_scene["diapositive"] and vu_scene["diapositive"]["reference"] == "2:3"
    await op.disconnect()
    await scene.disconnect()


async def test_rec24_deux_suivante_avec_la_meme_version_une_seule_diapositive_est_franchie(poste):
    prestation, session, operateur, jeton = poste
    op, _ = await operateur_connecte(session, operateur)
    await preparer_et_demarrer(op, prestation)
    for _ in range(2):  # ack et diffusion de « demarrer »
        await op.receive_json_from()

    await op.send_json_to(commande("suivante", 2))
    await op.send_json_to(commande("suivante", 2))  # double clic
    acks = []
    while len(acks) < 2:
        message = await op.receive_json_from()
        if message["type"] == "ack":
            acks.append(message)

    assert [a["statut"] for a in acks] == ["appliquee", "rejetee"]
    assert acks[1]["raison"] == "version_obsolete" and acks[1]["version"] == 3
    await op.disconnect()


async def test_rec14_la_scene_ne_peut_pas_commander_et_reste_connectee(poste):
    prestation, session, operateur, jeton = poste
    scene, _ = await scene_connectee(session, jeton)

    await scene.send_json_to(commande("preparer", prestation=str(prestation.pk)))
    ack = await scene.receive_json_from()

    assert (ack["statut"], ack["raison"]) == ("rejetee", "non_autorise")
    await scene.send_json_to({"type": "ping"})
    assert (await scene.receive_json_from())["type"] == "pong"  # toujours connectée
    await scene.disconnect()


async def test_une_commande_rejouee_avec_le_meme_id_donne_deja_traitee(poste):
    prestation, session, operateur, _ = poste
    op, _ = await operateur_connecte(session, operateur)
    message = commande("preparer", prestation=str(prestation.pk))
    await op.send_json_to(message)
    assert (await op.receive_json_from())["statut"] == "appliquee"
    await op.receive_json_from()  # diffusion

    await op.send_json_to(message)  # coupure réseau : l'écran renvoie la même commande
    rejeu = await op.receive_json_from()

    assert (rejeu["statut"], rejeu["version"]) == ("deja_traitee", 1)
    assert await op.receive_nothing(timeout=0.3)  # et rien n'est rediffusé
    await op.disconnect()


# --- Reprise d'état -------------------------------------------------------------------


async def test_rec15_rec23_une_scene_qui_se_reconnecte_retrouve_la_diapositive_courante(poste):
    prestation, session, operateur, jeton = poste
    op, _ = await operateur_connecte(session, operateur)
    scene, _ = await scene_connectee(session, jeton)
    await preparer_et_demarrer(op, prestation)
    for _ in range(2):  # ack et diffusion de « demarrer »
        await op.receive_json_from()
    await op.send_json_to(commande("suivante", 2))
    await op.receive_json_from()
    await op.receive_json_from()
    await scene.disconnect()  # coupure Wi-Fi : la scène disparaît

    nouvelle_scene, instantane = await scene_connectee(session, jeton)

    assert instantane["instantane"] is True and instantane["version"] == 3
    assert instantane["diapositive"]["index"] == 1 and instantane["phase"] == "affichage"
    await op.disconnect()
    await nouvelle_scene.disconnect()


async def test_un_snapshot_demande_renvoie_l_etat_complet(poste):
    prestation, session, operateur, jeton = poste
    op, _ = await operateur_connecte(session, operateur)
    await op.send_json_to(commande("preparer", prestation=str(prestation.pk)))
    await op.receive_json_from()
    await op.receive_json_from()

    await op.send_json_to({"type": "snapshot"})
    message = await op.receive_json_from()

    assert message["instantane"] is True and message["version"] == 1
    await op.disconnect()


# --- Présence --------------------------------------------------------------------------


async def test_l_operateur_voit_si_la_scene_est_connectee(poste):
    _, session, operateur, jeton = poste
    op, _ = await operateur_connecte(session, operateur)
    await op.send_json_to({"type": "ping"})
    await op.receive_json_from()  # pong
    assert (await op.receive_json_from())["ecrans"] == [{"nom": "Scène 1", "type": "scene", "connecte": False}]

    scene, _ = await scene_connectee(session, jeton)
    await op.send_json_to({"type": "ping"})
    await op.receive_json_from()

    assert (await op.receive_json_from())["ecrans"][0]["connecte"] is True
    await op.disconnect()
    await scene.disconnect()


# --- Robustesse -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [{"type": "commande"}, {"type": "commande", "id": "pas-un-uuid", "action": "suivante"},
     {"type": "commande", "id": str(uuid.uuid4()), "action": 12}, {"type": 12}, {"truc": 1},
     {"type": "commande", "id": str(uuid.uuid4()), "action": "suivante", "version_attendue": "x"}],
)
async def test_un_message_mal_forme_donne_une_erreur_sans_fermer_la_connexion(poste, message):
    _, session, operateur, _ = poste
    op, _ = await operateur_connecte(session, operateur)

    await op.send_json_to(message)
    reponse = await op.receive_json_from()

    assert reponse == {"type": "erreur", "code": "requete_invalide"}
    await op.send_json_to({"type": "ping"})
    assert (await op.receive_json_from())["type"] == "pong"
    await op.disconnect()


async def test_un_type_de_message_inconnu(poste):
    _, session, operateur, _ = poste
    op, _ = await operateur_connecte(session, operateur)

    await op.send_json_to({"type": "bidule"})

    assert (await op.receive_json_from())["code"] == "message_inconnu"
    await op.disconnect()


# --- Protection de l'origine ---------------------------------------------------------------


async def test_une_page_d_un_autre_site_ne_peut_pas_ouvrir_le_websocket(poste):
    from config.asgi import application

    _, session, _, _ = poste
    chemin = f"/ws/presentation/{session.pk}/"

    etranger = WebsocketCommunicator(application, chemin, headers=[(b"origin", b"http://pirate.example")])
    connecte, _ = await etranger.connect()
    assert connecte is False

    local = WebsocketCommunicator(application, chemin, headers=[(b"origin", b"http://127.0.0.1:8000")])
    connecte, _ = await local.connect()
    assert connecte is True
    await local.disconnect()
