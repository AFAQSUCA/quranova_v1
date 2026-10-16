"""Commande : vérifie l'intégrité des chaînes du journal d'audit (§15.2)."""
from django.core.management.base import BaseCommand, CommandError

from apps.audit.models import ChaineAudit
from apps.audit.services import verifier_chaine


class Command(BaseCommand):
    help = "Vérifie les empreintes chaînées du journal d'audit, chaîne par chaîne."

    def handle(self, *args, **options):
        total, anomalies = 0, []
        for chaine in ChaineAudit.objects.select_related("organisation").order_by("organisation__nom"):
            problemes = verifier_chaine(chaine.organisation)
            total += 1
            self.stdout.write(f"{chaine.organisation or 'Système'} : {chaine.dernier_numero} entrée(s), "
                              f"{'intacte' if not problemes else str(len(problemes)) + ' problème(s)'}")
            anomalies += [f"{chaine.organisation or 'Système'} : {p}" for p in problemes]
        if anomalies:
            raise CommandError("Journal d'audit ALTÉRÉ :\n" + "\n".join(anomalies))
        self.stdout.write(self.style.SUCCESS(f"{total} chaîne(s) vérifiée(s) : aucune anomalie."))
