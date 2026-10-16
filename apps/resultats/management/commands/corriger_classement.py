"""Commande : corrige un classement définitif (nouvelle version motivée) au nom d'un responsable client (RM-18)."""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.concours.models import Epreuve
from apps.resultats import validation
from apps.resultats.exceptions import ClassementInvalideError
from apps.utilisateurs.models import Utilisateur


class Command(BaseCommand):
    help = "Crée une nouvelle version, motivée, du classement définitif d'une épreuve (réservé au responsable client)."

    def add_arguments(self, parser):
        parser.add_argument("epreuve", help="Identifiant (UUID) de l'épreuve.")
        parser.add_argument("--utilisateur", required=True, help="Nom d'utilisateur du responsable client.")
        parser.add_argument("--motif", required=True, help="Motif de la correction (obligatoire).")
        parser.add_argument("--confirmer-egalites", action="store_true", help="Valider avec les ex aequo restants.")

    def handle(self, *args, **options):
        try:
            epreuve = Epreuve.objects.get(pk=options["epreuve"])
        except (Epreuve.DoesNotExist, ValidationError, ValueError):
            raise CommandError(f"Épreuve introuvable : {options['epreuve']}") from None
        utilisateur = Utilisateur.objects.filter(username=options["utilisateur"]).first()
        if utilisateur is None:
            raise CommandError(f"Utilisateur introuvable : {options['utilisateur']}")
        try:
            classement = validation.corriger_classement(epreuve, utilisateur, options["motif"], options["confirmer_egalites"])
        except ClassementInvalideError as erreur:
            raise CommandError(str(erreur)) from None
        self.stdout.write(self.style.SUCCESS(f"Classement corrigé : version {classement.version} (la précédente est conservée)."))
