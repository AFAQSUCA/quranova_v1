"""Candidats, participations et consentements parentaux (§7.3, §14.1, §16.2)."""
from django.db import models
from django.db.models import Q

from apps.candidats.exceptions import ParticipationInvalideError
from apps.commun.models import ModeleDuClient


class Candidat(ModeleDuClient):
    """Une personne inscrite par l'opérateur à partir des informations du client (RM-05).

    Minimisation (§16.1) : seuls le nom et le prénom sont obligatoires ; aucune pièce
    d'identité, aucune photographie, aucune donnée de santé.
    """

    class Sexe(models.TextChoices):
        MASCULIN = "M", "Masculin"
        FEMININ = "F", "Féminin"

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    date_naissance = models.DateField(
        null=True, blank=True, help_text="Nécessaire si la catégorie dépend de l'âge ou pour reconnaître un mineur."
    )
    sexe = models.CharField(max_length=1, choices=Sexe.choices, blank=True, default="")
    ville = models.CharField(max_length=100, blank=True)
    structure = models.CharField(max_length=200, blank=True, help_text="Structure représentée.")

    class Meta:
        verbose_name = "candidat"
        verbose_name_plural = "candidats"
        ordering = ["nom", "prenom"]

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    def __str__(self):
        return self.nom_complet


class Participation(ModeleDuClient):
    """L'inscription d'un candidat à une catégorie d'un concours, avec son numéro (§14.1)."""

    PARENTS_CLIENT = ("candidat", "concours", "categorie")

    class Statut(models.TextChoices):
        INSCRIT = "inscrit", "Inscrit"
        ADMIS = "admis", "Admis à concourir"
        RETIRE = "retire", "Retiré"

    candidat = models.ForeignKey(Candidat, on_delete=models.PROTECT, related_name="participations")
    concours = models.ForeignKey(
        "concours.Concours", on_delete=models.PROTECT, related_name="participations"
    )
    categorie = models.ForeignKey(
        "concours.Categorie", on_delete=models.PROTECT, related_name="participations"
    )
    numero_candidat = models.PositiveIntegerField()
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.INSCRIT)

    class Meta:
        verbose_name = "participation"
        verbose_name_plural = "participations"
        ordering = ["concours", "numero_candidat"]
        constraints = [
            models.UniqueConstraint(
                fields=["concours", "numero_candidat"], name="participation_numero_unique_par_concours"
            ),
            models.UniqueConstraint(
                fields=["candidat", "categorie"], name="participation_unique_par_categorie"
            ),
            models.CheckConstraint(
                condition=Q(numero_candidat__gte=1), name="participation_numero_au_moins_1"
            ),
        ]

    def save(self, *args, **kwargs):
        if self.categorie.concours_id != self.concours_id:
            raise ParticipationInvalideError(
                "La catégorie de la participation n'appartient pas au concours indiqué."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"n° {self.numero_candidat} — {self.candidat}"


class Consentement(ModeleDuClient):
    """Formulaire de consentement parental d'un candidat mineur (§16.2, RM-28).

    Trois consentements distincts et jamais précochés : (1) participation et traitement
    des données, (2) publication du nom dans les classements, (3) image ou voix.
    Le retrait prend effet pour l'avenir : le formulaire est marqué « retiré » et conservé.
    Un retrait partiel se fait en retirant ce formulaire puis en en enregistrant un nouveau.
    """

    class Statut(models.TextChoices):
        VALIDE = "valide", "Valide"
        RETIRE = "retire", "Retiré"

    PARENTS_CLIENT = ("participation",)

    participation = models.ForeignKey(
        Participation, on_delete=models.PROTECT, related_name="consentements"
    )
    representant_nom = models.CharField(max_length=200)
    representant_lien = models.CharField(max_length=100, help_text="Lien avec le candidat.")
    version_formulaire = models.CharField(max_length=20)
    date_signature = models.DateField()
    consentement_participation = models.BooleanField(default=False)
    consentement_publication_nom = models.BooleanField(default=False)
    consentement_image_voix = models.BooleanField(default=False)
    # Document numérisé. Son stockage chiffré sera mis en place avec la sécurité du serveur de salle (§15).
    document = models.FileField(upload_to="consentements/", blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.VALIDE)
    date_retrait = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "consentement"
        verbose_name_plural = "consentements"
        ordering = ["participation", "-date_signature"]
        constraints = [
            # Un seul formulaire valide à la fois par participation ; les formulaires retirés restent.
            models.UniqueConstraint(
                fields=["participation"],
                condition=Q(statut="valide"),
                name="consentement_un_seul_valide_par_participation",
            ),
            models.CheckConstraint(
                condition=(
                    Q(statut="valide", date_retrait__isnull=True)
                    | Q(statut="retire", date_retrait__isnull=False)
                ),
                name="consentement_retrait_coherent",
            ),
        ]

    def __str__(self):
        return f"Consentement de {self.representant_nom} ({self.get_statut_display()})"
