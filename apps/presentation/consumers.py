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
from apps.jury import connexion as connexion_jure
from apps.jury.exceptions import JetonInvalideError as JetonJureInvalideError
from apps.jury.models import CodeAccesJure, ConnexionJure
from apps.prestations import terminaux
from apps.prestations.exceptions import TerminalInvalideError
from apps.prestations.models import Prestation, Terminal
from apps.presentation import instantane, services
from apps.presentation.instantane import JURY, OPERATEUR, SCENE

DELAI_AUTHENTIFICATION_S = 5
SEUIL_PRESENCE = timedelta(seconds=30)

CODE_NON_AUTHENTIFIE, CODE_INTERDIT, CODE_DELAI = 4401, 4403, 4408


def groupe(session_id, role):
    return f"presentation.{session_id}.{role}"


class PresentationConsumer(AsyncJsonWebsocketConsumer):
    role = None
    session = None
    terminal = None
    connexion = None  # connexion d'un juré

    # --- connexion ----------------------------------------------------------------

    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.session = await self._charger_session()
        await self.accept()
        if self.session is None:
            await self.close(code=CODE_INTERDIT)
            return
        utilisateur = self.scope.get("user")
        if utilisateur is not None and await database_sync_to_async(services.peut_commander_en_ligne)(utilisateur, self.session, self.scope.get("session")):
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
            if type_message == "auth" and contenu.get("jeton_jure") is not None:
                await self._authentifier_jure(contenu.get("jeton_jure"))
            elif type_message == "auth":
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

    async def _authentifier_jure(self, jeton):
        """Un juré s'authentifie avec le jeton obtenu en échange de son code (D44, D46) : il reçoit le texte."""
        try:
            conn = await database_sync_to_async(connexion_jure.authentifier_jeton)(jeton, self.session)
        except JetonJureInvalideError:
            await self.close(code=CODE_NON_AUTHENTIFIE)
            return
        self.connexion = conn
        tache = getattr(self, "_attente_auth", None)
        if tache is not None:
            tache.cancel()
        await self._entrer(JURY)

    async def _ping(self):
        if self.terminal is not None or self.connexion is not None:
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
        if self.terminal is not None:
            Terminal.objects.filter(pk=self.terminal.pk).update(derniere_activite=timezone.now())
        if self.connexion is not None:
            ConnexionJure.objects.filter(pk=self.connexion.pk).update(derniere_activite=timezone.now())

    def _ecrans(self):
        limite = timezone.now() - SEUIL_PRESENCE
        ecrans = [
            {"nom": t.nom, "type": t.type, "connecte": t.derniere_activite is not None and t.derniere_activite >= limite}
            for t in Terminal.objects.filter(session=self.session, type=Terminal.Type.SCENE, revoque_le__isnull=True)
        ]
        jures = {}
        for acces in CodeAccesJure.objects.filter(session=self.session, revoque_le__isnull=True).select_related("jure"):
            actif = acces.connexions.filter(
                revoque_le__isnull=True, derniere_activite__gte=limite
            ).exists()
            jures[acces.jure_id] = {"nom": acces.jure.nom_complet, "connecte": actif}
        return {"type": "ecrans", "ecrans": ecrans, "jures": list(jures.values())}

    def _instantane(self, role, instantane_complet):
        return instantane.construire_instantane(self.session, role, instantane=instantane_complet)

    # --- envois ---------------------------------------------------------------------

    async def _envoyer_instantane(self):
        await self.send_json(await database_sync_to_async(self._instantane)(self.role, True))

    async def _diffuser(self):
        """Après une commande appliquée : chaque rôle reçoit SA projection de l'état (RM-14)."""
        for role in (OPERATEUR, SCENE, JURY):
            message = await database_sync_to_async(self._instantane)(role, False)
            await self.channel_layer.group_send(
                groupe(self.session_id, role), {"type": "diffuser.etat", "message": message}
            )

    async def diffuser_etat(self, evenement):
        await self.send_json(evenement["message"])
