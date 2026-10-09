"""Commande : importe un fichier CSV de candidats dans un concours (§7.3)."""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.candidats.importation import importer_candidats
from apps.concours.models import Concours


class Command(BaseCommand):
    help = (
        "Importe des candidats depuis un fichier CSV (colonnes : nom, prenom, categorie ; "
        "facultatives : date_naissance, sexe, ville, structure). Tout ou rien."
    )

    def add_arguments(self, parser):
        parser.add_argument("concours", help="Identifiant (UUID) du concours.")
        parser.add_argument("fichier", help="Chemin du fichier CSV.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Contrôle le fichier et affiche le rapport, sans rien enregistrer.",
        )

    def handle(self, *args, **options):
        try:
            concours = Concours.objects.get(pk=options["concours"])
        except (Concours.DoesNotExist, ValidationError, ValueError):
            raise CommandError(f"Concours introuvable : {options['concours']}") from None
        chemin = Path(options["fichier"])
        if not chemin.is_file():
            raise CommandError(f"Fichier introuvable : {chemin}")

        rapport = importer_candidats(concours, chemin, simuler=options["dry_run"])
        if not rapport.ok:
            raise CommandError(f"Import refusé, rien n'a été enregistré :\n{rapport.texte()}")
        self.stdout.write(self.style.SUCCESS(rapport.texte()))
