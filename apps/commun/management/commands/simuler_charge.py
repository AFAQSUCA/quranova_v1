"""Commande : simulation de charge du serveur de salle (REC-19, REC-20 ; objectifs §18.1).

Crée un concours de charge (par défaut 500 candidats, 20 tablettes de tirage, 10 écrans de scène = 30 terminaux), puis
fait tirer tous les candidats par HTTP pendant que l'opérateur fait défiler une présentation par WebSocket. Mesure les
latences et vérifie la cohérence (aucun double tirage, aucune série réutilisée, journal d'audit intact).

À lancer sur une base JETABLE, avec le serveur déjà démarré (la commande lui parle par le réseau) :
    python manage.py simuler_charge --confirmer-base-jetable --url http://127.0.0.1:8000
    docker compose exec web python manage.py simuler_charge --confirmer-base-jetable --url http://nginx
"""
import asyncio
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.commun.charge import execution, preparation
from apps.commun.charge.mesures import rapport_texte


class Command(BaseCommand):
    help = "Simule la charge d'un concours (500 candidats, 30 terminaux) et mesure les latences (REC-19, REC-20)."

    def add_arguments(self, parser):
        parser.add_argument("--url", default="http://127.0.0.1:8000", help="Adresse du serveur à tester (HTTP).")
        parser.add_argument("--confirmer-base-jetable", action="store_true",
                            help="Obligatoire : la commande crée des données de charge qui ne se suppriment pas.")
        parser.add_argument("--candidats", type=int, default=500)
        parser.add_argument("--terminaux-tirage", type=int, default=20)
        parser.add_argument("--ecrans-scene", type=int, default=10)
        parser.add_argument("--commandes", type=int, default=200, help="Commandes de diaporama envoyées (suivante/précédente).")
        parser.add_argument("--pause-terminal", type=float, default=3.0,
                            help="Pause moyenne d'un terminal entre deux candidats, en secondes (±50 %%). 3 s ≈ une journée accélérée ×20 ; 0 = rafale.")
        parser.add_argument("--intervalle-commandes", type=float, default=0.1, help="Pause entre deux commandes, en secondes.")
        parser.add_argument("--rapport", help="Écrit le rapport Markdown dans ce fichier.")

    def handle(self, *args, **o):
        if not o["confirmer_base_jetable"]:
            raise CommandError("Ajoutez --confirmer-base-jetable : cette commande crée des centaines de lignes de charge "
                               "(jamais sur la base d'un vrai concours).")
        if o["candidats"] < 1 or o["terminaux_tirage"] < 1 or o["ecrans_scene"] < 1:
            raise CommandError("Il faut au moins 1 candidat, 1 terminal de tirage et 1 écran de scène.")
        try:
            contexte = preparation.preparer(o["candidats"], o["terminaux_tirage"], o["ecrans_scene"], ecrire=self.stdout.write)
        except RuntimeError as erreur:
            raise CommandError(str(erreur)) from None

        simulation = execution.Simulation(
            contexte, o["url"], commandes=o["commandes"], pause_terminal=o["pause_terminal"],
            intervalle_commandes=o["intervalle_commandes"], ecrire=self.stdout.write,
        )
        duree = asyncio.run(simulation.lancer())

        coherence = self._coherence(contexte, simulation)
        rapport = self._rapport(o, simulation, duree, coherence)
        self.stdout.write("\n" + rapport)
        if o["rapport"]:
            Path(o["rapport"]).write_text(rapport + "\n", encoding="utf-8")
            self.stdout.write(f"Rapport écrit : {o['rapport']}")
        tout_bon = all(ob.verdict()["atteint"] for ob in simulation.objectifs()) and all(ok for _, ok in coherence) and not simulation.anomalies
        if not tout_bon:
            raise CommandError("Simulation : au moins un objectif ou un contrôle n'est pas atteint (voir le rapport).")
        self.stdout.write(self.style.SUCCESS("Simulation réussie : tous les objectifs sont atteints."))

    def _coherence(self, contexte, simulation):
        from apps.audit.services import verifier_chaine
        from apps.prestations.models import Prestation, Tirage

        tirages = Tirage.objects.filter(prestation__session=contexte.session, statut=Tirage.Statut.VALIDE,
                                        prestation__epreuve__nom="Tirages")
        n = contexte.nombre_candidats
        problemes = verifier_chaine(contexte.organisation)
        return [
            (f"{n} candidats ont exactement un tirage valide", tirages.count() == n and tirages.values("prestation").distinct().count() == n),
            ("aucune série tirée deux fois (RM-21)", tirages.values("serie").distinct().count() == tirages.count()),
            ("toutes les prestations sont « tirées »",
             Prestation.objects.filter(session=contexte.session, epreuve__nom="Tirages", etat=Prestation.Etat.TIRE).count() == n),
            ("journal d'audit : chaîne intacte", not problemes),
        ]

    def _rapport(self, o, simulation, duree, coherence):
        lignes = [
            "# Rapport de simulation de charge", "",
            f"Serveur : {simulation.url} · {o['candidats']} candidats · {o['terminaux_tirage']} terminaux de tirage · "
            f"{o['ecrans_scene']} écrans de scène (+ l'opérateur) · {o['commandes']} commandes · durée {duree:.1f} s.", "",
            rapport_texte(simulation.objectifs(), simulation.mesures()), "",
            "## Contrôles de cohérence", "",
        ]
        lignes += [f"- {'OK' if ok else 'ÉCHEC'} : {libelle}" for libelle, ok in coherence]
        lignes += ["", "## Anomalies", ""]
        lignes += [f"- {a}" for a in simulation.anomalies[:30]] or ["- aucune"]
        if len(simulation.anomalies) > 30:
            lignes.append(f"- … et {len(simulation.anomalies) - 30} autres")
        return "\n".join(lignes)
