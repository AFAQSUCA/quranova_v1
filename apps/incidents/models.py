"""Journal des incidents en salle (§13.6) : ce qui s'est passé pendant le concours, et ce qui a été fait."""
from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient


class Incident(ModeleDuClient):
    """Un incident survenu pendant un concours : coupure, panne, Wi-Fi, contestation…

    Consigné par le personnel du prestataire (jamais supprimé). Il alimente la section « Incidents » du procès-verbal et le bilan du pilote.
    """

    PARENTS_CLIENT = ("concours",)

    class Type(models.TextChoices):
        COUPURE_ELECTRICITE = "coupure_electricite", "Coupure d'électricité"
        PANNE_ROUTEUR = "panne_routeur", "Panne du routeur Wi-Fi"
        WIFI_COUPE = "wifi_coupe", "Coupure du Wi-Fi"
        PANNE_TABLETTE_JURE = "panne_tablette_jure", "Panne d'une tablette de juré"
        PANNE_TABLETTE_TIRAGE = "panne_tablette_tirage", "Panne d'une tablette de tirage"
        PANNE_ECRAN_SCENE = "panne_ecran_scene", "Panne de l'écran de scène"
        PANNE_SERVEUR = "panne_serveur", "Panne du serveur de salle"
        PANNE_DOUBLE = "panne_double", "Panne simultanée des deux ordinateurs"
        ERREUR_TIRAGE = "erreur_tirage", "Erreur ou contestation de tirage"
        CONTESTATION = "contestation", "Contestation d'une note ou d'un résultat"
        AUTRE = "autre", "Autre"

    class Gravite(models.TextChoices):
        MINEURE = "mineure", "Mineure"
        BLOQUANTE = "bloquante", "Bloquante"

    concours = models.ForeignKey("concours.Concours", on_delete=models.PROTECT, related_name="incidents")
    session = models.ForeignKey("concours.Session", null=True, blank=True, on_delete=models.PROTECT, related_name="incidents")
    prestation = models.ForeignKey("prestations.Prestation", null=True, blank=True, on_delete=models.PROTECT, related_name="incidents")
    type = models.CharField(max_length=30, choices=Type.choices)
    gravite = models.CharField(max_length=10, choices=Gravite.choices, default=Gravite.MINEURE, help_text="Bloquante : le concours a dû s'interrompre ou basculer en secours.")
    survenu_le = models.DateTimeField(help_text="Heure réelle de l'incident (peut être saisie après coup).")
    description = models.TextField(help_text="Ce qui s'est passé, factuellement.")
    declare_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    resolu_le = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True, help_text="Ce qui a été fait pour y remédier.")

    class Meta:
        verbose_name = "incident"
        verbose_name_plural = "incidents"
        ordering = ["-survenu_le"]
        constraints = [
            models.CheckConstraint(condition=Q(resolu_le__isnull=True) | Q(resolu_le__gte=F("survenu_le")), name="incident_resolution_apres_incident"),
            # Résolu = on sait ce qui a été fait : pas de date de résolution sans texte.
            models.CheckConstraint(condition=Q(resolu_le__isnull=True) | ~Q(resolution=""), name="incident_resolu_exige_une_resolution"),
        ]

    @property
    def duree(self):
        """Durée de l'incident, ou ``None`` tant qu'il n'est pas résolu."""
        return None if self.resolu_le is None else self.resolu_le - self.survenu_le

    def __str__(self):
        return f"{self.get_type_display()} — {self.survenu_le:%d/%m/%Y %H:%M}"
