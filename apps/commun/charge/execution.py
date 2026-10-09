"""Exécution de la simulation de charge : des terminaux de tirage (HTTP) et des écrans (WebSocket) en même temps.

Journée accélérée : pendant que N candidats tirent leur série sur T tablettes, l'opérateur fait défiler une présentation
(commandes ``suivante`` / ``precedente``) et chaque écran de scène mesure le délai entre l'envoi de la commande et la
réception de l'état. Les verdicts reprennent §18.1 et REC-19/REC-20.
"""
import asyncio
import http.client
import json
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from asgiref.sync import sync_to_async

from apps.commun.charge.client_ws import ClientWS
from apps.commun.charge.mesures import Mesures, Objectif


class Simulation:
    def __init__(self, contexte, url, *, commandes, pause_terminal, intervalle_commandes, ecrire=print):
        self.c, self.url, self.ecrire = contexte, url.rstrip("/"), ecrire
        self.nb_commandes, self.pause_terminal, self.intervalle = commandes, pause_terminal, intervalle_commandes
        morceaux = urlsplit(self.url)
        self.hote, self.port = morceaux.hostname, morceaux.port or 80
        self.origine = f"{morceaux.scheme}://{morceaux.netloc}"
        self.ws_url = f"ws://{morceaux.netloc}/ws/presentation/{contexte.session.pk}/"
        self.http_tout = Mesures("HTTP : toutes les requêtes")
        self.http_etat = Mesures("HTTP : état du terminal")
        self.http_tirage = Mesures("HTTP : tirage")
        self.propagation = Mesures("WebSocket : commande → état sur chaque écran")
        self.aller_retour = Mesures("WebSocket : commande → accusé de réception")
        self.anomalies = []
        self.pool = ThreadPoolExecutor(max_workers=len(contexte.terminaux_tirage) + 2)

    # --- HTTP ---------------------------------------------------------------------------------------------------

    def _requete(self, connexion, methode, chemin, jeton, corps=None):
        en_tetes = {"Authorization": f"Bearer {jeton}"}
        if corps is not None:
            en_tetes["Content-Type"] = "application/json"
        debut = time.perf_counter()
        try:
            connexion.request(methode, chemin, body=json.dumps(corps) if corps is not None else None, headers=en_tetes)
            reponse = connexion.getresponse()
            donnees = reponse.read()
            statut = reponse.status
        except (OSError, http.client.HTTPException) as erreur:
            connexion.close()
            return time.perf_counter() - debut, 0, {"erreur": repr(erreur)}
        return time.perf_counter() - debut, statut, json.loads(donnees or b"{}")

    async def _http(self, mesure, connexion, methode, chemin, jeton, corps=None):
        duree, statut, donnees = await asyncio.get_running_loop().run_in_executor(
            self.pool, self._requete, connexion, methode, chemin, jeton, corps
        )
        mesure.ajouter(duree)
        self.http_tout.ajouter(duree)
        if statut != 200:
            mesure.echec()
            self.http_tout.echec()
            self.anomalies.append(f"{methode} {chemin} → {statut} {donnees}")
        return statut, donnees

    async def _terminal(self, terminal, jeton, file, series_tirees):
        connexion = http.client.HTTPConnection(self.hote, self.port, timeout=10)
        from apps.prestations import terminaux
        from apps.prestations.models import Prestation

        while True:
            try:
                prestation_id = file.get_nowait()
            except asyncio.QueueEmpty:
                break
            prestation = await sync_to_async(Prestation.objects.get)(pk=prestation_id)
            await sync_to_async(terminaux.appeler_prestation)(terminal, prestation, self.c.operateur)  # action de l'opérateur
            await self._http(self.http_etat, connexion, "GET", "/api/tirage/etat/", jeton)
            id_demande = str(uuid.uuid4())
            statut, donnees = await self._http(self.http_tirage, connexion, "POST", "/api/tirage/", jeton, {"id_demande": id_demande})
            if statut == 200:
                serie = donnees["tirage"]["serie"]
                series_tirees.append(serie)
                if len(series_tirees) % 10 == 0:  # double clic : même demande rejouée, même série attendue
                    statut2, donnees2 = await self._http(self.http_tirage, connexion, "POST", "/api/tirage/", jeton, {"id_demande": id_demande})
                    if statut2 == 200 and donnees2["tirage"]["serie"] != serie:
                        self.anomalies.append(f"REJEU : la demande {id_demande} a donné deux séries différentes")
            # simple désynchronisation de la simulation, rien de secret
            await asyncio.sleep(self.pause_terminal * random.uniform(0.5, 1.5))  # nosec B311
        connexion.close()

    # --- WebSocket ----------------------------------------------------------------------------------------------

    async def _ouvrir_ecrans(self):
        operateur = await ClientWS.ouvrir("opérateur", self.ws_url, origine=self.origine, cookie=self.c.cookie_operateur)
        scenes = []
        for terminal, jeton in self.c.terminaux_scene:
            scene = await ClientWS.ouvrir(terminal.nom, self.ws_url, origine=self.origine)
            await scene.envoyer_json({"type": "auth", "jeton": jeton})
            scenes.append(scene)
        for ecran in [operateur, *scenes]:
            if not await ecran.attendre(lambda e=ecran: any(m.get("type") == "etat" for _, m in e.messages), 5):
                raise RuntimeError(f"{ecran.nom} : pas d'instantané reçu à la connexion (fermeture {ecran.code_fermeture}).")
        return operateur, scenes

    async def _commande(self, operateur, ecrans, action, **plus):
        identifiant = str(uuid.uuid4())
        version_attendue = operateur.version
        message = {"type": "commande", "id": identifiant, "action": action, **plus}
        if action != "preparer":
            message["version_attendue"] = version_attendue
        depart = time.perf_counter()
        await operateur.envoyer_json(message)
        if not await operateur.attendre(lambda: identifiant in operateur.acks, 5):
            self.anomalies.append(f"{action} : pas d'accusé de réception en 5 s")
            self.aller_retour.echec()
            return None
        arrivee, ack = operateur.acks[identifiant]
        if ack.get("statut") != "appliquee":
            self.anomalies.append(f"{action} refusée : {ack}")
            self.aller_retour.echec()
            return None
        self.aller_retour.ajouter(arrivee - depart)
        version = ack["version"]
        for ecran in (operateur, *ecrans):
            if await ecran.attendre(lambda e=ecran: version in e.vues, 3):
                self.propagation.ajouter(ecran.vues[version] - depart)
            else:
                self.propagation.echec()  # commande perdue pour cet écran
                self.anomalies.append(f"{ecran.nom} n'a jamais reçu la version {version} ({action})")
        return version

    async def _presentation(self, operateur, scenes):
        await self._commande(operateur, scenes, "preparer", prestation=str(self.c.prestation_presentation.pk))
        await self._commande(operateur, scenes, "demarrer")
        sens, envoyees = +1, 0
        while envoyees < self.nb_commandes and not operateur.ferme:
            diapositive = operateur.diapositive or {}
            index, total = diapositive.get("index", 0), diapositive.get("total", 1)
            if sens > 0 and index >= total - 1:
                sens = -1
            elif sens < 0 and index <= 0:
                sens = +1
            if await self._commande(operateur, scenes, "suivante" if sens > 0 else "precedente") is None:
                break
            envoyees += 1
            await asyncio.sleep(self.intervalle)
        return envoyees

    # --- ensemble -----------------------------------------------------------------------------------------------

    async def lancer(self):
        self.ecrire("Connexion des écrans (opérateur + scènes)…")
        operateur, scenes = await self._ouvrir_ecrans()
        file = asyncio.Queue()
        for prestation_id in self.c.prestations:
            file.put_nowait(prestation_id)
        series_tirees = []
        debut = time.perf_counter()
        self.ecrire(f"Départ : {len(self.c.prestations)} tirages sur {len(self.c.terminaux_tirage)} terminaux, "
                    f"{self.nb_commandes} commandes sur {len(scenes)} scènes.")
        resultats = await asyncio.gather(
            *[self._terminal(t, j, file, series_tirees) for t, j in self.c.terminaux_tirage],
            self._presentation(operateur, scenes),
            return_exceptions=True,
        )
        duree = time.perf_counter() - debut
        for r in resultats:
            if isinstance(r, Exception):
                self.anomalies.append(f"Exception : {r!r}")
        for ecran in (operateur, *scenes):
            if ecran.code_fermeture is not None:
                self.anomalies.append(f"{ecran.nom} fermé par le serveur (code {ecran.code_fermeture})")
            await ecran.fermer()
        self.duree = duree
        self.series_tirees = series_tirees
        return duree

    def objectifs(self):
        return [
            Objectif("REC-19 : 95 % des requêtes HTTP", self.http_tout, 0.300, p=95),
            Objectif("REC-19 : tirage (99 %)", self.http_tirage, 1.0, p=99),
            Objectif("REC-20 : propagation d'une commande à tous les écrans", self.propagation, 0.300, p=95),
        ]

    def mesures(self):
        return [self.http_etat, self.http_tirage, self.http_tout, self.aller_retour, self.propagation]
