"""Modèles du corpus coranique (cf. §12 et §14 du cahier des charges).

Le texte coranique vient uniquement du fichier Tanzil importé : il n'est jamais
saisi, corrigé ni normalisé depuis l'application (règle absolue n°1).
"""
from django.db import models
from django.db.models import Q


class VersionCorpus(models.Model):
    """Une version identifiée du corpus : source, empreinte, statut (§12.3).

    Une fois validée, une version est immuable (RM-27) : toute correction
    donne lieu à une nouvelle version, jamais à une modification de l'ancienne.
    """

    class Riwaya(models.TextChoices):
        HAFS = "hafs", "Hafs ʿan ʿĀṣim"

    class Statut(models.TextChoices):
        IMPORTEE = "importee", "Importée"
        VALIDEE = "validee", "Validée"
        ACTIVE = "active", "Active"
        RETIREE = "retiree", "Retirée"

    source = models.CharField(max_length=100, default="Tanzil")
    version_source = models.CharField(
        max_length=50,
        help_text="Version indiquée dans l'en-tête du fichier Tanzil.",
    )
    riwaya = models.CharField(
        max_length=20, choices=Riwaya.choices, default=Riwaya.HAFS
    )
    nom_fichier = models.CharField(max_length=255)
    empreinte_sha256 = models.CharField(
        max_length=64,
        unique=True,
        help_text="Empreinte SHA-256 du fichier source (64 caractères hexadécimaux).",
    )
    date_import = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.IMPORTEE
    )
    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date du procès-verbal de validation du référent coranique.",
    )

    class Meta:
        verbose_name = "version du corpus"
        verbose_name_plural = "versions du corpus"
        ordering = ["-date_import"]
        constraints = [
            # Au plus une version active par riwāya (§12.3 : activation pour
            # les nouveaux concours ; les anciens gardent leur version).
            models.UniqueConstraint(
                fields=["riwaya"],
                condition=Q(statut="active"),
                name="une_seule_version_active_par_riwaya",
            ),
            # SHA-256 = 64 caractères hexadécimaux en minuscules.
            models.CheckConstraint(
                condition=Q(empreinte_sha256__regex=r"^[0-9a-f]{64}$"),
                name="empreinte_sha256_valide",
            ),
        ]

    def __str__(self):
        return f"{self.source} {self.version_source} ({self.get_riwaya_display()}) — {self.get_statut_display()}"
