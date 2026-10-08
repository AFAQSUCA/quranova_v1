"""Clients du prestataire et leurs missions (§7.1, §14.1)."""
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient, ModeleHorodate

# Une couleur est vide (aucune personnalisation) ou au format « #RRGGBB ».
FORMAT_COULEUR = r"^(#[0-9A-Fa-f]{6})?$"


class Organisation(ModeleHorodate):
    """Un client du prestataire (association, école coranique, mosquée...).

    C'est la seule table client SANS clé ``organisation`` : elle est l'organisation.
    """

    class Statut(models.TextChoices):
        ACTIF = "actif", "Actif"
        ARCHIVE = "archive", "Archivé"

    nom = models.CharField(max_length=200, unique=True)
    logo = models.FileField(upload_to="logos/", blank=True)
    couleur_principale = models.CharField(max_length=7, blank=True, default="")
    couleur_secondaire = models.CharField(max_length=7, blank=True, default="")
    adresse = models.TextField(blank=True)
    telephone = models.CharField(max_length=50, blank=True)
    courriel = models.EmailField(blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.ACTIF)

    class Meta:
        verbose_name = "organisation"
        verbose_name_plural = "organisations"
        ordering = ["nom"]
        constraints = [
            models.CheckConstraint(
                condition=Q(couleur_principale__regex=FORMAT_COULEUR),
                name="organisation_couleur_principale_valide",
            ),
            models.CheckConstraint(
                condition=Q(couleur_secondaire__regex=FORMAT_COULEUR),
                name="organisation_couleur_secondaire_valide",
            ),
        ]

    def __str__(self):
        return self.nom


class Mission(ModeleDuClient):
    """Une prestation du prestataire chez un client : lieu, dates, formule (§14.1, §22)."""

    class Statut(models.TextChoices):
        EN_PREPARATION = "en_preparation", "En préparation"
        EN_COURS = "en_cours", "En cours"
        TERMINEE = "terminee", "Terminée"
        ARCHIVEE = "archivee", "Archivée"

    nom = models.CharField(max_length=200)
    lieu = models.CharField(max_length=200)
    date_debut = models.DateField()
    date_fin = models.DateField()
    formule = models.CharField(max_length=100, blank=True, help_text="Formule commerciale retenue.")
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.EN_PREPARATION
    )

    class Meta:
        verbose_name = "mission"
        verbose_name_plural = "missions"
        ordering = ["-date_debut"]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="mission_date_fin_apres_date_debut",
            ),
        ]

    def __str__(self):
        return f"{self.nom} ({self.organisation})"
