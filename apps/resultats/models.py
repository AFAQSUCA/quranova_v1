"""Classement définitif : un instantané figé, validé par le responsable client (RM-18, §11, §14.2).

Le classement PROVISOIRE n'est jamais stocké (il se recalcule). Seule la validation fige un classement : les lignes
ne changent plus ensuite. Une correction postérieure crée une NOUVELLE version, motivée et identifiée comme telle ;
les versions précédentes restent.
"""
from django.db import models
from django.db.models import Q

from apps.commun.models import ModeleDuClient
from apps.resultats.exceptions import ClassementInvalideError


class Classement(ModeleDuClient):
    PARENTS_CLIENT = ("epreuve",)

    epreuve = models.ForeignKey("concours.Epreuve", on_delete=models.PROTECT, related_name="classements")
    version = models.PositiveIntegerField(default=1)
    est_correction = models.BooleanField(default=False)
    motif_correction = models.TextField(blank=True)
    valide_par = models.ForeignKey("utilisateurs.Utilisateur", on_delete=models.PROTECT, related_name="+")
    valide_le = models.DateTimeField()
    regle_classement = models.CharField(max_length=20)
    regle_departage = models.CharField(max_length=30, blank=True)
    empreinte = models.CharField(max_length=64)

    class Meta:
        verbose_name = "classement définitif"
        verbose_name_plural = "classements définitifs"
        ordering = ["epreuve", "version"]
        constraints = [
            models.UniqueConstraint(fields=["epreuve", "version"], name="classement_version_unique_par_epreuve"),
            models.CheckConstraint(
                condition=(Q(est_correction=False, version=1, motif_correction="") | Q(est_correction=True, version__gt=1) & ~Q(motif_correction="")),
                name="classement_correction_motivee",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ClassementInvalideError("Un classement validé ne se modifie pas : une correction crée une nouvelle version.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ClassementInvalideError("Un classement validé ne se supprime pas.")

    def __str__(self):
        return f"Classement de {self.epreuve} — version {self.version}" + (" (corrigée)" if self.est_correction else "")


class LigneDeClassement(ModeleDuClient):
    PARENTS_CLIENT = ("classement", "participation")

    classement = models.ForeignKey(Classement, on_delete=models.PROTECT, related_name="lignes")
    participation = models.ForeignKey("candidats.Participation", on_delete=models.PROTECT, related_name="+")
    rang = models.PositiveIntegerField(null=True, blank=True)
    ex_aequo = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    complet = models.BooleanField(default=True)
    evaluations_validees = models.PositiveSmallIntegerField(default=0)
    evaluations_attendues = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "ligne de classement"
        verbose_name_plural = "lignes de classement"
        ordering = ["classement", "rang", "participation__numero_candidat"]
        constraints = [
            models.UniqueConstraint(fields=["classement", "participation"], name="ligne_unique_par_classement"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ClassementInvalideError("Une ligne d'un classement validé ne se modifie pas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ClassementInvalideError("Une ligne d'un classement validé ne se supprime pas.")
