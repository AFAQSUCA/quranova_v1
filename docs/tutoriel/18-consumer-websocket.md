# Chapitre 18 — Le consumer WebSocket (itération 3, étape 3c)

> **Commit de référence :** `c63d1dc` · **Durée :** 4 à 5 heures · **Résultat :** les écrans se connectent en WebSocket, s'authentifient, reçoivent l'instantané, envoient des commandes et se synchronisent. **26 tests** du consumer.

## Objectif

Brancher les services du chapitre 17 sur le temps réel. Le consumer **ne détient aucun état** : il authentifie, vérifie, appelle les services, puis diffuse.

| Règle | Où elle est appliquée |
|---|---|
| **Règle absolue n°4** : permissions à chaque message | le rôle est fixé à la connexion ; chaque commande est revérifiée |
| **REC-14** : la scène ne commande jamais | `_commande` refuse tout ce qui ne vient pas de l'opérateur |
| **REC-25** : jeton d'une autre session refusé | `terminal.session_id` comparé à celle de l'URL (code 4403) |
| **D38** : le jeton ne passe jamais dans l'URL | premier message `auth` dans les 5 s (sinon 4408) |
| **REC-10, 15, 23** : synchronisation et reprise | diffusion à un groupe par rôle ; instantané à chaque connexion |
| **Contre le détournement de WebSocket** | `AllowedHostsOriginValidator` : une page d'un autre site est refusée |

## Étape A — La dépendance de test (D36)

`pytest-asyncio` permet de tester du code asynchrone. Ajoutez-la à `requirements\dev.txt` :

```text
pytest-asyncio>=1.0,<2
```

```powershell
pip install -r requirements\dev.txt
```

## Étape B — Les tests d'abord

Les tests utilisent de **vraies transactions** (`transaction=True`) : le consumer lit et écrit dans d'autres threads, qui ne voient pas une transaction de test non validée.

**Fichier `apps\presentation\tests\test_consumer.py`**

```python
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
```

## Étape C — Le consumer, le routage, ASGI

**Fichier `apps\presentation\consumers.py`**

```python
"""Consumer WebSocket de la présentation (§9.4, §13.5 ; protocole : docs/conception/protocole-temps-reel.md).

Un consumer par écran connecté. Il ne détient AUCUN état : l'état est en base, géré par les services. Le
canal ne sert qu'à diffuser vite ; un message perdu se rattrape par l'instantané (numéro de version).

Chaque message reçu est contrôlé (règle absolue n°4) : le rôle est fixé à la connexion et vérifié à chaque
commande, jamais déduit d'une valeur envoyée par le client.
"""
import asyncio
import uuid
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from apps.concours.models import Session
from apps.prestations import terminaux
from apps.prestations.exceptions import TerminalInvalideError
from apps.prestations.models import Prestation, Terminal
from apps.presentation import instantane, services
from apps.presentation.instantane import OPERATEUR, SCENE

DELAI_AUTHENTIFICATION_S = 5
SEUIL_PRESENCE = timedelta(seconds=30)

CODE_NON_AUTHENTIFIE, CODE_INTERDIT, CODE_DELAI = 4401, 4403, 4408


def groupe(session_id, role):
    return f"presentation.{session_id}.{role}"


class PresentationConsumer(AsyncJsonWebsocketConsumer):
    role = None
    session = None
    terminal = None

    # --- connexion ----------------------------------------------------------------

    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.session = await self._charger_session()
        await self.accept()
        if self.session is None:
            await self.close(code=CODE_INTERDIT)
            return
        utilisateur = self.scope.get("user")
        if utilisateur is not None and await database_sync_to_async(services.peut_commander)(utilisateur, self.session):
            await self._entrer(OPERATEUR)  # authentifié par son cookie de session Django
            return
        self._attente_auth = asyncio.create_task(self._delai_authentification())

    async def _delai_authentification(self):
        await asyncio.sleep(DELAI_AUTHENTIFICATION_S)
        if self.role is None:
            await self.close(code=CODE_DELAI)

    async def disconnect(self, code):
        tache = getattr(self, "_attente_auth", None)
        if tache is not None:
            tache.cancel()
        if self.role is not None:
            await self.channel_layer.group_discard(groupe(self.session_id, self.role), self.channel_name)

    async def _entrer(self, role):
        self.role = role
        await self.channel_layer.group_add(groupe(self.session_id, role), self.channel_name)
        await self._envoyer_instantane()

    # --- réception ----------------------------------------------------------------

    async def receive_json(self, contenu, **kwargs):
        if not isinstance(contenu, dict) or not isinstance(contenu.get("type"), str):
            await self.send_json({"type": "erreur", "code": "requete_invalide"})
            return
        type_message = contenu["type"]
        if self.role is None:
            if type_message == "auth":
                await self._authentifier(contenu.get("jeton"))
            else:
                await self.close(code=CODE_NON_AUTHENTIFIE)  # rien d'autre avant l'authentification
            return
        if type_message == "ping":
            await self._ping()
        elif type_message == "snapshot":
            await self._envoyer_instantane()
        elif type_message == "commande":
            await self._commande(contenu)
        elif type_message == "auth":
            pass  # déjà authentifié
        else:
            await self.send_json({"type": "erreur", "code": "message_inconnu"})

    async def _authentifier(self, jeton):
        try:
            terminal = await database_sync_to_async(terminaux.authentifier_terminal)(jeton, Terminal.Type.SCENE)
        except TerminalInvalideError:
            await self.close(code=CODE_NON_AUTHENTIFIE)
            return
        if terminal.session_id != self.session.pk:
            await self.close(code=CODE_INTERDIT)  # le jeton d'une autre session ne donne rien ici
            return
        self.terminal = terminal
        tache = getattr(self, "_attente_auth", None)
        if tache is not None:
            tache.cancel()
        await self._entrer(SCENE)

    async def _ping(self):
        if self.terminal is not None:
            await database_sync_to_async(self._noter_activite)()
        await self.send_json({"type": "pong"})
        if self.role == OPERATEUR:
            await self.send_json(await database_sync_to_async(self._ecrans)())

    async def _commande(self, contenu):
        identifiant = contenu.get("id")
        try:
            id_commande = uuid.UUID(str(identifiant))
            action = contenu["action"]
            version = contenu.get("version_attendue")
            if not isinstance(action, str) or not (version is None or (isinstance(version, int) and not isinstance(version, bool))):
                raise ValueError
            prestation_id = uuid.UUID(str(contenu["prestation"])) if contenu.get("prestation") else None
        except (ValueError, KeyError, TypeError):
            await self.send_json({"type": "erreur", "code": "requete_invalide"})
            return
        if self.role != OPERATEUR:
            # REC-14 : un écran de scène ne commande jamais, quoi qu'il envoie.
            await self.send_json({"type": "ack", "id": str(id_commande), "statut": "rejetee",
                                  "raison": "non_autorise", "version": await database_sync_to_async(self._version)()})
            return
        resultat = await database_sync_to_async(self._executer)(id_commande, action, version, prestation_id)
        ack = {"type": "ack", "id": str(id_commande), "statut": resultat.statut, "version": resultat.version}
        if resultat.raison:
            ack["raison"] = resultat.raison
        await self.send_json(ack)
        if resultat.statut == "appliquee":
            await self._diffuser()

    # --- accès à la base (synchrone, dans un thread) --------------------------------

    @database_sync_to_async
    def _charger_session(self):
        return Session.objects.select_related("concours").filter(pk=self.session_id).first()

    def _executer(self, id_commande, action, version, prestation_id):
        prestation = Prestation.objects.filter(pk=prestation_id).first() if prestation_id else None
        return services.appliquer_commande(
            self.session, id_commande, action, version, auteur=self.scope["user"], prestation=prestation
        )

    def _version(self):
        return services._version_courante(self.session)

    def _noter_activite(self):
        Terminal.objects.filter(pk=self.terminal.pk).update(derniere_activite=timezone.now())

    def _ecrans(self):
        limite = timezone.now() - SEUIL_PRESENCE
        ecrans = [
            {"nom": t.nom, "type": t.type, "connecte": t.derniere_activite is not None and t.derniere_activite >= limite}
            for t in Terminal.objects.filter(session=self.session, type=Terminal.Type.SCENE, revoque_le__isnull=True)
        ]
        return {"type": "ecrans", "ecrans": ecrans}

    def _instantane(self, role, instantane_complet):
        return instantane.construire_instantane(self.session, role, instantane=instantane_complet)

    # --- envois ---------------------------------------------------------------------

    async def _envoyer_instantane(self):
        await self.send_json(await database_sync_to_async(self._instantane)(self.role, True))

    async def _diffuser(self):
        """Après une commande appliquée : chaque rôle reçoit SA projection de l'état (RM-14)."""
        for role in (OPERATEUR, SCENE):
            message = await database_sync_to_async(self._instantane)(role, False)
            await self.channel_layer.group_send(
                groupe(self.session_id, role), {"type": "diffuser.etat", "message": message}
            )

    async def diffuser_etat(self, evenement):
        await self.send_json(evenement["message"])
```

**Fichier `apps\presentation\routing.py`**

```python
from django.urls import path

from apps.presentation.consumers import PresentationConsumer

websocket_urlpatterns = [
    path("ws/presentation/<uuid:session_id>/", PresentationConsumer.as_asgi()),
]
```

**Fichier `config\asgi.py`**

```python
"""Point d'entrée ASGI : HTTP classique et WebSocket (Django Channels, §13.5).

Le WebSocket passe par deux protections : le contrôle d'origine (``AllowedHostsOriginValidator``, qui refuse
une page d'un autre site, contre le détournement de WebSocket) et l'authentification par cookie de session.
"""
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Django doit être initialisé AVANT d'importer le routage (qui importe des modèles).
application_http = get_asgi_application()

from apps.presentation.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": application_http,
        "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
    }
)
```

```powershell
pytest apps\presentation\tests\test_consumer.py
```

Attendu : `26 passed` (avec vos règles de transition écrites).

## Ce qu'il faut comprendre

- **`connect`** accepte, puis soit reconnaît l'opérateur (cookie de session Django), soit attend le message `auth` d'une scène. Rien d'autre n'est accepté avant l'authentification.
- **`receive_json`** est le seul point d'entrée des messages : il valide la forme, puis aiguille (`ping`, `snapshot`, `commande`).
- **`database_sync_to_async`** exécute le code Django (synchrone) dans un thread, pour ne pas bloquer la boucle asynchrone.
- **Groupes** : `presentation.<session>.operateur` et `.scene`. Après une commande appliquée, chaque groupe reçoit **sa** projection (RM-14).
- **La présence** (`ecrans`) se lit en base (dernière activité), pas dans la mémoire du bus : elle reste juste avec plusieurs processus.

## Questions de compréhension

1. Pourquoi deux groupes (opérateur, scène) plutôt qu'un seul ?
2. Que se passerait-il si le jeton passait dans l'URL (`?jeton=…`) ?
3. Pourquoi `AllowedHostsOriginValidator` est-il nécessaire alors que le WebSocket exige déjà un jeton ou un cookie ?

<details>
<summary>Réponses</summary>

1. Parce que les deux rôles ne reçoivent pas le même contenu : la scène n'a pas le texte si l'épreuve ne l'autorise pas. Un groupe unique ferait fuiter le texte.
2. Les adresses sont écrites dans les journaux du serveur et des intermédiaires : le jeton y serait lisible.
3. Un site pirate ouvert dans le navigateur de l'opérateur pourrait ouvrir un WebSocket vers le serveur **avec le cookie de l'opérateur**. Le contrôle d'origine refuse les pages qui ne viennent pas du serveur.
</details>

## Journal d'apprentissage

Notez ce qui arrive, étape par étape, quand le Wi-Fi coupe 30 secondes en pleine présentation (lisez le §7 du protocole).

## Commit proposé

```text
Itération 3 : consumer WebSocket de la présentation
```
