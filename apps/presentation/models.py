"""État de présentation d'une prestation et journal des commandes (§9.3, §13.5, RM-30)."""
from django.db import models
from django.db.models import Q

from apps.commun.models import ModeleDuClient


class EtatPresentation(ModeleDuClient):
    """L'état du diaporama d'une prestation. C'est le SERVEUR qui le détient (règle absolue n°7).

    ``version`` croît à chaque changement ; une commande n'est appliquée que si elle porte la version
    courante (RM-30). ``plan`` ne contient que des références, figées à « Préparer l'affichage » (D39).
    """

    PARENTS_CLIENT = ("prestation", "session")

    class Phase(models.TextChoices):
        PREPAREE = "preparee", "Préparée"
        AFFICHAGE = "affichage", "En affichage"
        PAUSE = "pause", "En pause"
        TERMINEE = "terminee", "Terminée"

    prestation = models.OneToOneField("prestations.Prestation", on_delete=models.PROTECT, related_name="presentation")
    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="presentations")
    active = models.BooleanField(default=False, help_text="La présentation suivie par les écrans de la session (D41).")
    version = models.PositiveIntegerField(default=1)
    phase = models.CharField(max_length=10, choices=Phase.choices, default=Phase.PREPAREE)
    index = models.PositiveIntegerField(null=True, blank=True, help_text="Diapositive courante (0 = la première).")
    rejeu = models.PositiveIntegerField(default=0, help_text="Incrémenté par « Réafficher la diapositive ».")
    plan = models.JSONField(default=list)

    class Meta:
        verbose_name = "état de présentation"
        verbose_name_plural = "états de présentation"
        constraints = [
            # Une seule présentation active par session (D41).
            models.UniqueConstraint(fields=["session"], condition=Q(active=True), name="presentation_une_active_par_session"),
            models.CheckConstraint(condition=Q(version__gte=1), name="presentation_version_au_moins_1"),
            models.CheckConstraint(
                condition=(Q(phase="preparee", index__isnull=True) | (~Q(phase="preparee") & Q(index__isnull=False))),
                name="presentation_index_selon_la_phase",
            ),
        ]

    def __str__(self):
        return f"Présentation de {self.prestation} (v{self.version}, {self.get_phase_display()})"


class CommandePresentation(ModeleDuClient):
    """Journal des commandes reçues : appliquées OU rejetées, avec leur auteur (§9.3, §15.2).

    L'identifiant de commande, unique, est ce qui rend une commande rejouable sans effet (RM-30).
    Le retour à la diapositive précédente y est donc toujours tracé.
    """

    PARENTS_CLIENT = ("session",)

    class Statut(models.TextChoices):
        APPLIQUEE = "appliquee", "Appliquée"
        REJETEE = "rejetee", "Rejetée"

    id_commande = models.UUIDField(unique=True)
    session = models.ForeignKey("concours.Session", on_delete=models.PROTECT, related_name="commandes_presentation")
    prestation = models.ForeignKey(
        "prestations.Prestation", null=True, blank=True, on_delete=models.PROTECT, related_name="commandes_presentation"
    )
    action = models.CharField(max_length=20)
    version_attendue = models.PositiveIntegerField(null=True, blank=True)
    version_apres = models.PositiveIntegerField(null=True, blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices)
    raison = models.CharField(max_length=40, blank=True)
    auteur = models.ForeignKey("utilisateurs.Utilisateur", null=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = "commande de présentation"
        verbose_name_plural = "commandes de présentation"
        ordering = ["cree_le"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(statut="appliquee", raison="") | (Q(statut="rejetee") & ~Q(raison=""))),
                name="commande_raison_si_rejetee",
            ),
        ]

    def __str__(self):
        return f"{self.action} ({self.get_statut_display()})"
