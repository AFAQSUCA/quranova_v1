"""Concours, catégories, épreuves, barème et sessions (§7.2, §8.2, §14.1)."""
from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient
from apps.concours.exceptions import ConfigurationInvalideError


class Concours(ModeleDuClient):
    """Un concours (une édition) conduit pour un client, dans le cadre d'une mission."""

    PARENTS_CLIENT = ("mission",)

    class Format(models.TextChoices):
        PRESENTIEL = "presentiel", "Présentiel"  # en ligne et hybride : V2

    class Etat(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        OUVERT = "ouvert", "Ouvert"
        EN_COURS = "en_cours", "En cours"
        SUSPENDU = "suspendu", "Suspendu"
        TERMINE = "termine", "Terminé"
        ARCHIVE = "archive", "Archivé"

    mission = models.ForeignKey(
        "clients.Mission", on_delete=models.PROTECT, related_name="concours"
    )
    nom = models.CharField(max_length=200)
    edition = models.CharField(max_length=50, blank=True, help_text="Millésime ou numéro d'édition.")
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.PRESENTIEL)
    date_debut = models.DateField()
    date_fin = models.DateField()
    # RM-27 : version unique du corpus, figée à l'ouverture. Vide tant que le concours est en brouillon.
    version_corpus = models.ForeignKey(
        "coran.VersionCorpus",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="concours",
    )
    etat = models.CharField(max_length=20, choices=Etat.choices, default=Etat.BROUILLON)
    # RM-31 : validation de la configuration par le responsable du client (qui, quand, quelle configuration).
    configuration_validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    configuration_validee_le = models.DateTimeField(null=True, blank=True)
    configuration_empreinte = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Empreinte SHA-256 de la configuration au moment de sa validation.",
    )

    class Meta:
        verbose_name = "concours"
        verbose_name_plural = "concours"
        ordering = ["-date_debut", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "nom", "edition"], name="concours_nom_edition_uniques"
            ),
            models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="concours_date_fin_apres_date_debut",
            ),
            # La validation est complète ou absente : qui, quand et quelle configuration.
            models.CheckConstraint(
                condition=(
                    Q(
                        configuration_validee_par__isnull=True,
                        configuration_validee_le__isnull=True,
                        configuration_empreinte="",
                    )
                    | (
                        Q(configuration_validee_par__isnull=False, configuration_validee_le__isnull=False)
                        & ~Q(configuration_empreinte="")
                    )
                ),
                name="concours_validation_configuration_complete",
            ),
            # RM-27 et RM-31 : hors brouillon, le corpus est figé et la configuration validée.
            models.CheckConstraint(
                condition=(
                    Q(etat="brouillon")
                    | (Q(version_corpus__isnull=False) & Q(configuration_validee_le__isnull=False))
                ),
                name="concours_ouvert_exige_corpus_et_validation",
            ),
        ]

    def __str__(self):
        return f"{self.nom} {self.edition}".strip()


class Categorie(ModeleDuClient):
    """Une catégorie d'un concours : mémorisation, tajwid, tilawa, questions..."""

    PARENTS_CLIENT = ("concours",)

    class Discipline(models.TextChoices):
        MEMORISATION = "memorisation", "Mémorisation"
        TAJWID = "tajwid", "Tajwid"
        TILAWA = "tilawa", "Tilawa"
        QUESTIONS = "questions", "Questions"
        PERSONNALISEE = "personnalisee", "Personnalisée"

    class RegleClassement(models.TextChoices):
        MOYENNE = "moyenne", "Moyenne"
        TOTAL = "total", "Total"
        ELIMINATION = "elimination", "Élimination"

    class RegleDepartage(models.TextChoices):
        MOYENNE_GENERALE = "moyenne_generale", "Moyenne générale"
        CRITERE_PRIORITAIRE = "critere_prioritaire", "Critère prioritaire"
        EPREUVE_SUPPLEMENTAIRE = "epreuve_supplementaire", "Épreuve supplémentaire"
        DECISION_COMITE = "decision_comite", "Décision documentée du comité"

    concours = models.ForeignKey(Concours, on_delete=models.PROTECT, related_name="categories")
    nom = models.CharField(max_length=100)
    discipline = models.CharField(
        max_length=20, choices=Discipline.choices, default=Discipline.MEMORISATION
    )
    age_minimum = models.PositiveSmallIntegerField(null=True, blank=True)
    age_maximum = models.PositiveSmallIntegerField(null=True, blank=True)
    effectif_prevu = models.PositiveIntegerField(null=True, blank=True)
    regle_classement = models.CharField(
        max_length=20, choices=RegleClassement.choices, default=RegleClassement.MOYENNE
    )
    # Vide par défaut : le système n'invente jamais de règle de départage (§10.4).
    regle_departage = models.CharField(
        max_length=30, choices=RegleDepartage.choices, blank=True, default=""
    )

    class Meta:
        verbose_name = "catégorie"
        verbose_name_plural = "catégories"
        ordering = ["nom"]
        constraints = [
            models.UniqueConstraint(fields=["concours", "nom"], name="categorie_nom_unique_par_concours"),
            models.CheckConstraint(
                condition=(
                    Q(age_minimum__isnull=True)
                    | Q(age_maximum__isnull=True)
                    | Q(age_maximum__gte=F("age_minimum"))
                ),
                name="categorie_age_maximum_apres_age_minimum",
            ),
        ]

    def __str__(self):
        return self.nom


class Epreuve(ModeleDuClient):
    """Une épreuve d'une catégorie, avec ses paramètres de tirage (§8.2, RM-03, RM-21)."""

    PARENTS_CLIENT = ("categorie",)

    class ModeAffichage(models.TextChoices):
        ARABE_SEUL = "arabe_seul", "Arabe seul"
        ARABE_ET_TRADUCTION = "arabe_et_traduction", "Arabe avec traduction française"

    class Etat(models.TextChoices):
        EN_PREPARATION = "en_preparation", "En préparation"
        OUVERTE = "ouverte", "Ouverte"
        TERMINEE = "terminee", "Terminée"

    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="epreuves")
    nom = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField()
    # P : questions par série. T : tirages par candidat. Q = T x P est calculé (RM-03).
    questions_par_serie = models.PositiveSmallIntegerField(help_text="P")
    tirages_par_candidat = models.PositiveSmallIntegerField(default=1, help_text="T")
    # RM-21 : réutilisation des séries tirées.
    reutilisation_autre_candidat = models.BooleanField(default=False)
    reutilisation_meme_candidat_autre_epreuve = models.BooleanField(default=False)
    exclusion_definitive = models.BooleanField(default=True)
    mode_affichage = models.CharField(
        max_length=30, choices=ModeAffichage.choices, default=ModeAffichage.ARABE_SEUL
    )
    # Désactivé par défaut : en mémorisation, l'écran scène ne doit pas être visible du candidat (§9.1).
    affichage_scene = models.BooleanField(default=False)
    etat = models.CharField(max_length=20, choices=Etat.choices, default=Etat.EN_PREPARATION)
    # §10.4 : critère de départage quand la règle de la catégorie est « priorité à un critère » (aucune valeur inventée).
    critere_prioritaire = models.ForeignKey(
        "concours.CritereNotation", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Critère qui départage les égalités si la catégorie le prévoit.",
    )

    class Meta:
        verbose_name = "épreuve"
        verbose_name_plural = "épreuves"
        ordering = ["categorie", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["categorie", "ordre"], name="epreuve_ordre_unique_par_categorie"),
            models.UniqueConstraint(fields=["categorie", "nom"], name="epreuve_nom_unique_par_categorie"),
            models.CheckConstraint(
                condition=Q(questions_par_serie__gte=1), name="epreuve_p_au_moins_1"
            ),
            models.CheckConstraint(
                condition=Q(tirages_par_candidat__gte=1), name="epreuve_t_au_moins_1"
            ),
        ]

    @property
    def questions_par_candidat(self):
        """Q = T x P (RM-03) : calculé, jamais saisi."""
        return self.tirages_par_candidat * self.questions_par_serie

    def save(self, *args, **kwargs):
        if self.critere_prioritaire_id is not None and self.critere_prioritaire.epreuve_id != self.pk:
            raise ConfigurationInvalideError("Le critère prioritaire doit être un critère de cette épreuve.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class CritereNotation(ModeleDuClient):
    """Un critère du barème d'une épreuve : libellé, note maximale, coefficient (§7.2)."""

    PARENTS_CLIENT = ("epreuve",)

    epreuve = models.ForeignKey(Epreuve, on_delete=models.PROTECT, related_name="criteres")
    libelle = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField()
    maximum = models.DecimalField(max_digits=6, decimal_places=2)
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        verbose_name = "critère de notation"
        verbose_name_plural = "critères de notation"
        ordering = ["epreuve", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["epreuve", "ordre"], name="critere_ordre_unique_par_epreuve"),
            models.UniqueConstraint(fields=["epreuve", "libelle"], name="critere_libelle_unique_par_epreuve"),
            models.CheckConstraint(condition=Q(maximum__gt=0), name="critere_maximum_positif"),
            models.CheckConstraint(condition=Q(coefficient__gt=0), name="critere_coefficient_positif"),
        ]

    def __str__(self):
        return self.libelle


class Session(ModeleDuClient):
    """Une session de passage d'un concours : date, lieu, serveur de salle utilisé (§14.1)."""

    PARENTS_CLIENT = ("concours",)

    concours = models.ForeignKey(Concours, on_delete=models.PROTECT, related_name="sessions")
    nom = models.CharField(max_length=100)
    date = models.DateField()
    lieu = models.CharField(max_length=200, blank=True)
    serveur_de_salle = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "session"
        verbose_name_plural = "sessions"
        ordering = ["date", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["concours", "nom"], name="session_nom_unique_par_concours"),
        ]

    def __str__(self):
        return f"{self.nom} ({self.date})"
