"""Commande : restaure une sauvegarde dans une NOUVELLE base, puis vérifie sa cohérence (§15.5, REC-18)."""
from django.core.management.base import BaseCommand, CommandError

from apps.commun import sauvegarde


class Command(BaseCommand):
    help = "Restaure une sauvegarde dans une base (créée) et vérifie le journal d'audit restauré."

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Fichier .dump à restaurer.")
        parser.add_argument("--vers-base", required=True, help="Nom de la base à créer (jamais la base en service).")
        parser.add_argument("--ecraser", action="store_true", help="Remplace la base de destination si elle existe.")

    def handle(self, *args, **options):
        try:
            sauvegarde.restaurer(options["fichier"], options["vers_base"], ecraser=options["ecraser"])
        except sauvegarde.SauvegardeError as erreur:
            raise CommandError(str(erreur)) from None
        self.stdout.write(self.style.SUCCESS(
            f"Base « {options['vers_base']} » restaurée et vérifiée. Pour l'utiliser : DB_NAME={options['vers_base']} dans .env."
        ))
