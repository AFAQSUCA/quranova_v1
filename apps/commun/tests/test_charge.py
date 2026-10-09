"""Outils de la simulation de charge (phase 3, REC-19/20) : percentiles, trames WebSocket, client contre un faux serveur."""
import asyncio
import base64
import hashlib
import json
import struct

import pytest

from apps.commun.charge import client_ws, mesures


def test_percentile_rang_le_plus_proche():
    valeurs = list(range(1, 101))  # 1..100
    assert mesures.percentile(valeurs, 95) == 95
    assert mesures.percentile(valeurs, 50) == 50
    assert mesures.percentile(valeurs, 100) == 100
    assert mesures.percentile([7], 95) == 7
    assert mesures.percentile([], 95) is None


def test_percentile_ne_fait_pas_la_moyenne_des_extremes():
    assert mesures.percentile([0.1] * 19 + [5.0], 95) == 0.1  # 19 mesures sur 20 = 95 %
    assert mesures.percentile([0.1] * 18 + [5.0, 5.0], 95) == 5.0


def test_objectif_non_atteint_si_p95_au_dessus_du_seuil_ou_si_echec():
    m = mesures.Mesures("x", durees=[0.1] * 90 + [0.5] * 10)
    assert mesures.Objectif("t", m, 0.3).verdict()["atteint"] is False
    m2 = mesures.Mesures("y", durees=[0.1] * 100)
    assert mesures.Objectif("t", m2, 0.3).verdict()["atteint"] is True
    m2.echec()
    assert mesures.Objectif("t", m2, 0.3).verdict()["atteint"] is False  # « aucune erreur serveur »


def test_trame_masquee_aller_retour():
    masque = b"\x01\x02\x03\x04"
    for charge in (b"", b"a" * 125, b"b" * 126, b"c" * 70000):
        trame = encoder_et_lire(charge, masque)
        assert trame == (True, client_ws.TEXTE, charge)


def encoder_et_lire(charge, masque):
    async def passer():
        lecteur = asyncio.StreamReader()
        lecteur.feed_data(client_ws.encoder_trame(client_ws.TEXTE, charge, masque=masque))
        lecteur.feed_eof()
        return await client_ws.lire_trame(lecteur)

    return asyncio.run(passer())


@pytest.mark.asyncio
async def test_le_client_fait_la_poignee_de_main_et_releve_les_versions():
    """Faux serveur WebSocket : accepte, envoie deux « etat » (versions 1 et 2) puis un « ack »."""

    async def serveur(lecteur, ecrivain):
        requete = (await lecteur.readuntil(b"\r\n\r\n")).decode()
        cle = next(l.split(": ")[1] for l in requete.split("\r\n") if l.lower().startswith("sec-websocket-key"))
        assert "Origin: http://127.0.0.1" in requete and "Cookie: sessionid=abc" in requete
        accept = base64.b64encode(hashlib.sha1((cle + client_ws.GUID).encode()).digest()).decode()
        ecrivain.write(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n".encode())
        for version in (1, 2):
            etat = {"type": "etat", "version": version, "prestation": {"id": "p"}, "diapositive": {"index": version, "total": 3}}
            ecrivain.write(client_ws.encoder_trame(client_ws.TEXTE, json.dumps(etat).encode()))
        ecrivain.write(client_ws.encoder_trame(client_ws.TEXTE, json.dumps({"type": "ack", "id": "k", "statut": "appliquee"}).encode()))
        ecrivain.write(client_ws.encoder_trame(client_ws.FERMETURE, struct.pack("!H", 4403)))
        await ecrivain.drain()
        await asyncio.sleep(0.2)
        ecrivain.close()

    srv = await asyncio.start_server(serveur, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    async with srv:
        client = await client_ws.ClientWS.ouvrir("t", f"ws://127.0.0.1:{port}/ws/x/", origine="http://127.0.0.1", cookie="sessionid=abc")
        assert await client.attendre(lambda: client.code_fermeture is not None, 2)
        assert client.code_fermeture == 4403
        assert set(client.vues) == {1, 2} and client.version == 2 and client.diapositive["index"] == 2
        assert client.acks["k"][1]["statut"] == "appliquee"
        await client.fermer()


@pytest.mark.asyncio
async def test_le_client_refuse_une_poignee_de_main_sans_101():
    async def serveur(lecteur, ecrivain):
        await lecteur.readuntil(b"\r\n\r\n")
        ecrivain.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        await ecrivain.drain()
        ecrivain.close()

    srv = await asyncio.start_server(serveur, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    async with srv:
        with pytest.raises(client_ws.ErreurWebSocket):
            await client_ws.ClientWS.ouvrir("t", f"ws://127.0.0.1:{port}/", origine="http://x")


@pytest.mark.django_db
def test_la_simulation_refuse_de_tourner_sans_confirmation_de_base_jetable():
    from django.core.management import CommandError, call_command

    with pytest.raises(CommandError, match="confirmer-base-jetable"):
        call_command("simuler_charge")
