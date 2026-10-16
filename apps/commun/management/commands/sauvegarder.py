"""Commande : sauvegarde la base PostgreSQL (§15.5) — à planifier toutes les 15 minutes pendant un concours."""
from django.core.management.base import BaseCommand, CommandError

from apps.audit.services import journaliser
from apps.commun import sauvegarde


class Command(BaseCommand):
    help = "Écrit une sauvegarde PostgreSQL horodatée (avec son empreinte SHA-256) puis fait tourner les anciennes."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", required=True, help="Dossier de sauvegarde (idéalement un disque externe).")
        parser.add_argument("--conserver", type=int, default=96, help="Nombre de sauvegardes conservées (défaut : 96, soit 24 h à 15 min).")

    def handle(self, *args, **options):
        try:
            fichier = sauvegarde.sauvegarder(options["dossier"], options["conserver"])
        except sauvegarde.SauvegardeError as erreur:
            raise CommandError(str(erreur)) from None  # code de sortie non nul : le planificateur voit l'échec
        journaliser("sauvegarde.effectuee", details={"fichier": fichier.name, "octets": fichier.stat().st_size})
        self.stdout.write(self.style.SUCCESS(f"Sauvegarde écrite : {fichier} ({fichier.stat().st_size} octets)."))
