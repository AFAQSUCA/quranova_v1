"""Jurés, affectations aux épreuves et codes d'accès de session (§7.4, §14.1).

Les jurés n'ont PAS de compte Django (D4) : ils se connectent sur leur tablette avec un
code personnel à usage limité à la session, généré par l'opérateur. Aucune adresse
électronique n'est exigée.
"""
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient


class Jure(ModeleDuClient):
    """Un juré désigné par le client (RM-04)."""

    class Role(models.TextChoices):
        PRESIDENT = "president", "Président du jury"
        MEMBRE = "membre", "Membre du jury"

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBRE)
    competences = models.CharField(
        max_length=200, blank=True, help_text="Catégories ou disciplines de compétence (information)."
    )
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "juré"
        verbose_name_plural = "jurés"
        ordering = ["nom", "prenom"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "nom", "prenom"], name="jure_nom_prenom_uniques_par_organisation"
            ),
        ]

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return self.nom_complet


class AffectationJury(ModeleDuClient):
    """Un juré est affecté à une épreuve : il ne note que les prestations de ses épreuves (§6.3).

    D5 : l'affectation est toujours au niveau de l'épreuve. « Affecter à tout le concours » ou
    « à une catégorie » crée simplement une ligne par épreuve (cf. services.affecter).
    """

    PARENTS_CLIENT = ("jure", "epreuve")

    jure = models.ForeignKey(Jure, on_delete=models.PROTECT, related_name="affectations")
    epreuve = models.ForeignKey(
        "concours.Epreuve", on_delete=models.PROTECT, related_name="affectations_jury"
    )

    class Meta:
        verbose_name = "affectation de juré"
        verbose_name_plural = "affectations de jurés"
        constraints = [
            models.UniqueConstraint(fields=["jure", "epreuve"], name="affectation_jury_unique"),
        ]

    def __str__(self):
        return f"{self.jure} — {self.epreuve}"


class CodeAccesJure(ModeleDuClient):
    """Code d'accès d'un juré à une session. Seule son EMPREINTE est stockée, jamais le code (D4).

    Ce modèle vit dans l'application ``jury`` et non dans ``utilisateurs`` (comme le suggère le §13.8) :
    ``concours`` dépend déjà de ``utilisateurs`` ; l'inverse créerait une dépendance circulaire.
    """

    PARENTS_CLIENT = ("jure", "session")

    jure = models.ForeignKey(Jure, on_delete=models.PROTECT, related_name="codes")
    session = models.ForeignKey(
        "concours.Session", on_delete=models.PROTECT, related_name="codes_jures"
    )
    empreinte = models.CharField(max_length=64, unique=True, help_text="HMAC-SHA256 du code.")
    valide_du = models.DateTimeField()
    valide_jusqu_au = models.DateTimeField()
    revoque_le = models.DateTimeField(null=True, blank=True)
    derniere_utilisation = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "code d'accès de juré"
        verbose_name_plural = "codes d'accès de jurés"
        ordering = ["-valide_du"]
        constraints = [
            models.CheckConstraint(
                condition=Q(valide_jusqu_au__gt=F("valide_du")), name="code_jure_fin_apres_debut"
            ),
            # Un seul code actif par juré et par session ; les codes révoqués restent (traçabilité).
            models.UniqueConstraint(
                fields=["jure", "session"],
                condition=Q(revoque_le__isnull=True),
                name="code_jure_un_seul_actif",
            ),
        ]

    def __str__(self):
        return f"Code de {self.jure} pour {self.session}"
