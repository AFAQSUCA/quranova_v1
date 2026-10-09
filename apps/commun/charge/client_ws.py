"""Client WebSocket minimal (RFC 6455) pour la simulation de charge : ni dépendance, ni bibliothèque tierce.

Il ne sait faire que ce dont le simulateur a besoin : poignée de main avec en-têtes ``Origin`` et ``Cookie``,
messages texte (JSON) masqués côté client, réponses aux ``ping`` du serveur, fermeture. L'heure d'arrivée de
chaque message est relevée DÈS sa lecture (``time.perf_counter``), pour mesurer la propagation.
"""
import asyncio
import base64
import hashlib
import json
import os
import struct
import time
from urllib.parse import urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TEXTE, BINAIRE, FERMETURE, PING, PONG = 0x1, 0x2, 0x8, 0x9, 0xA


class ErreurWebSocket(Exception):
    pass


def encoder_trame(opcode, charge, masque=None):
    """Une trame complète (FIN=1) ; ``masque`` (4 octets) est obligatoire côté client."""
    premier = 0x80 | opcode
    n = len(charge)
    bit_masque = 0x80 if masque else 0
    if n < 126:
        entete = struct.pack("!BB", premier, bit_masque | n)
    elif n < 1 << 16:
        entete = struct.pack("!BBH", premier, bit_masque | 126, n)
    else:
        entete = struct.pack("!BBQ", premier, bit_masque | 127, n)
    if masque:
        charge = bytes(b ^ masque[i % 4] for i, b in enumerate(charge))
        return entete + masque + charge
    return entete + charge


async def lire_trame(lecteur):
    """Lit une trame ; renvoie ``(fin, opcode, charge)`` (charge démasquée)."""
    octets = await lecteur.readexactly(2)
    fin, opcode = bool(octets[0] & 0x80), octets[0] & 0x0F
    masquee, n = bool(octets[1] & 0x80), octets[1] & 0x7F
    if n == 126:
        n = struct.unpack("!H", await lecteur.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", await lecteur.readexactly(8))[0]
    masque = await lecteur.readexactly(4) if masquee else None
    charge = await lecteur.readexactly(n)
    if masque:
        charge = bytes(b ^ masque[i % 4] for i, b in enumerate(charge))
    return fin, opcode, charge


class ClientWS:
    def __init__(self, nom, lecteur, ecrivain):
        self.nom = nom
        self._lecteur, self._ecrivain = lecteur, ecrivain
        self.messages = []          # [(heure d'arrivée, dict)]
        self.vues = {}              # version -> heure d'arrivée du PREMIER « etat » portant cette version
        self.acks = {}              # id de commande -> (heure, dict)
        self.version, self.diapositive = None, None   # dernier état connu
        self.code_fermeture = None
        self._tache = None

    @classmethod
    async def ouvrir(cls, nom, url, *, origine, cookie=None, delai=5):
        morceaux = urlsplit(url)
        port = morceaux.port or (443 if morceaux.scheme == "wss" else 80)
        lecteur, ecrivain = await asyncio.wait_for(asyncio.open_connection(morceaux.hostname, port), delai)
        cle = base64.b64encode(os.urandom(16)).decode()
        chemin = morceaux.path + (f"?{morceaux.query}" if morceaux.query else "")
        en_tetes = [
            f"GET {chemin} HTTP/1.1", f"Host: {morceaux.netloc}", "Upgrade: websocket", "Connection: Upgrade",
            f"Sec-WebSocket-Key: {cle}", "Sec-WebSocket-Version: 13", f"Origin: {origine}",
        ]
        if cookie:
            en_tetes.append(f"Cookie: {cookie}")
        ecrivain.write(("\r\n".join(en_tetes) + "\r\n\r\n").encode())
        await ecrivain.drain()
        reponse = await asyncio.wait_for(lecteur.readuntil(b"\r\n\r\n"), delai)
        lignes = reponse.decode("latin-1").split("\r\n")
        if " 101 " not in lignes[0]:
            ecrivain.close()
            raise ErreurWebSocket(f"{nom} : poignée de main refusée ({lignes[0]})")
        attendu = base64.b64encode(hashlib.sha1((cle + GUID).encode(), usedforsecurity=False).digest()).decode()  # SHA-1 imposé par la RFC 6455
        if f"sec-websocket-accept: {attendu}".lower() not in reponse.decode("latin-1").lower():
            ecrivain.close()
            raise ErreurWebSocket(f"{nom} : réponse Sec-WebSocket-Accept invalide")
        client = cls(nom, lecteur, ecrivain)
        client._tache = asyncio.create_task(client._boucle())
        return client

    async def _boucle(self):
        morceaux = b""
        try:
            while True:
                fin, opcode, charge = await lire_trame(self._lecteur)
                arrivee = time.perf_counter()
                if opcode == PING:
                    await self._envoyer_trame(PONG, charge)
                elif opcode == FERMETURE:
                    self.code_fermeture = struct.unpack("!H", charge[:2])[0] if len(charge) >= 2 else 1005
                    return
                elif opcode in (TEXTE, BINAIRE, 0x0):
                    morceaux += charge
                    if fin:
                        self._recu(arrivee, morceaux)
                        morceaux = b""
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            return

    def _recu(self, arrivee, octets):
        try:
            message = json.loads(octets.decode("utf-8"))
        except ValueError:
            return
        self.messages.append((arrivee, message))
        if message.get("type") == "etat" and message.get("prestation"):
            version = message.get("version")
            self.vues.setdefault(version, arrivee)
            self.version, self.diapositive = version, message.get("diapositive")
        elif message.get("type") == "ack":
            self.acks[message.get("id")] = (arrivee, message)

    async def _envoyer_trame(self, opcode, charge):
        self._ecrivain.write(encoder_trame(opcode, charge, masque=os.urandom(4)))
        await self._ecrivain.drain()

    async def envoyer_json(self, objet):
        await self._envoyer_trame(TEXTE, json.dumps(objet).encode("utf-8"))

    @property
    def ferme(self):
        return self.code_fermeture is not None or self._tache is None or self._tache.done()

    async def attendre(self, condition, delai):
        """Attend qu'une condition (fonction sans argument) devienne vraie ; ``False`` si le délai expire."""
        fin = time.perf_counter() + delai
        while time.perf_counter() < fin:
            if condition():
                return True
            if self.ferme:
                return condition()
            await asyncio.sleep(0.001)
        return condition()

    async def fermer(self):
        if self._tache is not None:
            self._tache.cancel()
        try:
            await self._envoyer_trame(FERMETURE, struct.pack("!H", 1000))
        except (ConnectionError, OSError):
            pass
        self._ecrivain.close()
