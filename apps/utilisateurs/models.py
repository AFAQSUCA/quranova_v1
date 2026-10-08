"""Comptes du prestataire et du client, et affectation des opérateurs aux missions (§6, §14.1).

Les jurés n'ont PAS de compte : ils se connectent par un code de session (§7.4).
"""
import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models import Q

from apps.commun.models import ModeleDuClient
from apps.utilisateurs.exceptions import AffectationInvalideError


class GestionnaireUtilisateur(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Un superutilisateur Django est l'administrateur QURANOVA.
        extra_fields.setdefault("role", self.model.Role.ADMINISTRATEUR)
        return super().create_superuser(username, email, password, **extra_fields)


class Utilisateur(AbstractUser):
    """Compte nominatif : administrateur ou opérateur (prestataire), responsable client."""

    class Role(models.TextChoices):
        ADMINISTRATEUR = "administrateur", "Administrateur QURANOVA"
        OPERATEUR = "operateur", "Opérateur"
        RESPONSABLE_CLIENT = "responsable_client", "Responsable client"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.OPERATEUR)
    # Renseignée pour un responsable client, vide pour le personnel du prestataire.
    organisation = models.ForeignKey(
        "clients.Organisation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="utilisateurs",
    )

    objects = GestionnaireUtilisateur()

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        constraints = [
            # Un responsable client appartient à un client ; le personnel du prestataire à aucun.
            models.CheckConstraint(
                condition=(
                    Q(role="responsable_client", organisation__isnull=False)
                    | (~Q(role="responsable_client") & Q(organisation__isnull=True))
                ),
                name="utilisateur_role_et_organisation_coherents",
            ),
        ]


class AffectationOperateur(ModeleDuClient):
    """Un opérateur est affecté à une mission : il n'accède qu'aux missions affectées (§6.3)."""

    PARENTS_CLIENT = ("mission",)

    mission = models.ForeignKey(
        "clients.Mission", on_delete=models.PROTECT, related_name="affectations"
    )
    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.PROTECT, related_name="affectations"
    )

    class Meta:
        verbose_name = "affectation d'opérateur"
        verbose_name_plural = "affectations d'opérateurs"
        constraints = [
            models.UniqueConstraint(
                fields=["mission", "utilisateur"], name="affectation_unique_par_mission"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.utilisateur.role != Utilisateur.Role.OPERATEUR:
            raise AffectationInvalideError(
                f"Seul un opérateur peut être affecté à une mission (rôle : {self.utilisateur.role})."
            )
        super().save(*args, **kwargs)
