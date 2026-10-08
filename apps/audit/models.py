"""Journal d'audit en ajout seul, à empreinte chaînée (§15.2, §14.1).

Chaque entrée porte l'empreinte SHA-256 de la précédente de sa chaîne : modifier ou supprimer une entrée
passée casse toute la suite, et ``verifier_chaine`` le détecte. Il y a une chaîne PAR CLIENT (RM-20 : l'extrait
remis à un client ne contient rien d'un autre) et une chaîne « système » pour ce qui ne dépend d'aucun client.
Un déclencheur PostgreSQL (migration 0002) refuse en plus tout UPDATE ou DELETE, même hors de Django (D45).
"""
import uuid

from django.db import models
from django.db.models import Q

from apps.audit.exceptions import AuditImmuableError


class QuerySetAjoutSeul(models.QuerySet):
    """Refuse aussi les modifications en masse, qui contourneraient ``save`` et ``delete``."""

    def update(self, **kwargs):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : aucune modification.")

    def delete(self):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : aucune suppression.")

    def bulk_update(self, *args, **kwargs):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : aucune modification.")


class ChaineAudit(models.Model):
    """La tête d'une chaîne : numéro et empreinte de sa dernière entrée. Verrouillée à chaque ajout."""

    organisation = models.ForeignKey(
        "clients.Organisation", null=True, on_delete=models.PROTECT, related_name="+",
        help_text="Vide pour la chaîne « système ».",
    )
    dernier_numero = models.PositiveIntegerField(default=0)
    derniere_empreinte = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "chaîne d'audit"
        verbose_name_plural = "chaînes d'audit"
        constraints = [
            models.UniqueConstraint(fields=["organisation"], condition=Q(organisation__isnull=False), name="chaine_une_par_organisation"),
            models.UniqueConstraint(fields=["organisation"], condition=Q(organisation__isnull=True), name="chaine_systeme_unique"),
        ]

    def __str__(self):
        return f"Chaîne {self.organisation or 'système'} (n° {self.dernier_numero})"


class EntreeAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chaine = models.ForeignKey(ChaineAudit, on_delete=models.PROTECT, related_name="entrees")
    organisation = models.ForeignKey(
        "clients.Organisation", null=True, on_delete=models.PROTECT, related_name="entrees_audit", db_index=True
    )
    numero = models.PositiveIntegerField()
    horodatage = models.DateTimeField()
    auteur = models.ForeignKey("utilisateurs.Utilisateur", null=True, on_delete=models.PROTECT, related_name="+")
    # Pour ce qui n'a pas de compte : « juré Awa Diallo », « terminal Tablette 1 », « commande importer_candidats »…
    auteur_libelle = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=60)
    objet_type = models.CharField(max_length=60, blank=True)
    objet_id = models.CharField(max_length=64, blank=True)
    terminal = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict)
    empreinte_precedente = models.CharField(max_length=64, blank=True)
    empreinte = models.CharField(max_length=64)

    objects = QuerySetAjoutSeul.as_manager()

    class Meta:
        verbose_name = "entrée d'audit"
        verbose_name_plural = "entrées d'audit"
        ordering = ["chaine", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["chaine", "numero"], name="audit_numero_unique_par_chaine"),
            models.UniqueConstraint(fields=["empreinte"], name="audit_empreinte_unique"),
        ]
        indexes = [models.Index(fields=["organisation", "action"]), models.Index(fields=["objet_type", "objet_id"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditImmuableError("Le journal d'audit est en ajout seul : une entrée ne se modifie pas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditImmuableError("Le journal d'audit est en ajout seul : une entrée ne se supprime pas.")

    def __str__(self):
        return f"#{self.numero} {self.action}"
