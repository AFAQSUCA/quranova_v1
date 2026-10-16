"""Questions de la banque d'un client et passages coraniques (§8.4, §14.1).

Règle absolue n°1 : un passage coranique ne stocke que des RÉFÉRENCES (sourate, verset).
Le texte est toujours lu dans le corpus importé, jamais copié ici.
"""
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient
from apps.questions.exceptions import QuestionInvalideError


class Question(ModeleDuClient):
    """Une question de la banque de l'organisation : un passage coranique ou un énoncé libre."""

    class Type(models.TextChoices):
        PASSAGE_CORANIQUE = "passage_coranique", "Passage coranique"
        ENONCE = "enonce", "Énoncé"

    type = models.CharField(max_length=20, choices=Type.choices)
    # RM-23 : une question coranique est rattachée à une version précise du corpus.
    version_corpus = models.ForeignKey(
        "coran.VersionCorpus", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    enonce = models.TextField(blank=True)

    class Meta:
        verbose_name = "question"
        verbose_name_plural = "questions"
        ordering = ["-cree_le"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(type="passage_coranique") | Q(version_corpus__isnull=False),
                name="question_passage_exige_version_corpus",
            ),
            models.CheckConstraint(
                condition=~Q(type="enonce") | ~Q(enonce=""),
                name="question_enonce_exige_un_texte",
            ),
        ]

    def __str__(self):
        if self.type == self.Type.PASSAGE_CORANIQUE and hasattr(self, "passage"):
            return self.passage.libelle
        return self.enonce[:60]


class PassageCoranique(ModeleDuClient):
    """Début et fin d'un passage, bornes incluses, dans l'ordre canonique (§8.4)."""

    PARENTS_CLIENT = ("question",)

    question = models.OneToOneField(Question, on_delete=models.PROTECT, related_name="passage")
    sourate_debut = models.PositiveSmallIntegerField()
    verset_debut = models.PositiveSmallIntegerField()
    sourate_fin = models.PositiveSmallIntegerField()
    verset_fin = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "passage coranique"
        verbose_name_plural = "passages coraniques"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(sourate_debut__gte=1)
                    & Q(verset_debut__gte=1)
                    & Q(sourate_fin__gte=1)
                    & Q(verset_fin__gte=1)
                ),
                name="passage_numeros_au_moins_1",
            ),
            # La fin ne précède pas le début (§8.4, point 2) ; début = fin est permis.
            models.CheckConstraint(
                condition=Q(sourate_debut__lt=F("sourate_fin"))
                | (Q(sourate_debut=F("sourate_fin")) & Q(verset_debut__lte=F("verset_fin"))),
                name="passage_fin_apres_debut",
            ),
        ]

    @property
    def debut(self):
        return (self.sourate_debut, self.verset_debut)

    @property
    def fin(self):
        return (self.sourate_fin, self.verset_fin)

    @property
    def libelle(self):
        """Ex. « Sourate 2, versets 142 à 150 » (diapositive intercalaire, §8.3)."""
        if self.sourate_debut != self.sourate_fin:
            return (
                f"Sourate {self.sourate_debut}, verset {self.verset_debut} "
                f"à sourate {self.sourate_fin}, verset {self.verset_fin}"
            )
        if self.verset_debut == self.verset_fin:
            return f"Sourate {self.sourate_debut}, verset {self.verset_debut}"
        return f"Sourate {self.sourate_debut}, versets {self.verset_debut} à {self.verset_fin}"

    def save(self, *args, **kwargs):
        if self.question.type != Question.Type.PASSAGE_CORANIQUE:
            raise QuestionInvalideError("Seule une question de type passage coranique a un passage.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.libelle


class Lot(ModeleDuClient):
    """Les séries préparées pour une épreuve (§8.2).

    Un lot par épreuve en V1 (D24) : le partage d'un lot entre épreuves (RM-21.b) viendra plus tard.
    """

    PARENTS_CLIENT = ("epreuve",)

    epreuve = models.OneToOneField("concours.Epreuve", on_delete=models.PROTECT, related_name="lot")

    class Meta:
        verbose_name = "lot"
        verbose_name_plural = "lots"

    def __str__(self):
        return f"Lot de l'épreuve {self.epreuve}"


class Serie(ModeleDuClient):
    """Une série du lot : P questions ordonnées (RM-22).

    La disponibilité d'une série n'est PAS stockée ici : elle se déduit des tirages (D2).
    """

    PARENTS_CLIENT = ("lot",)

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="series")
    numero = models.PositiveIntegerField()

    class Meta:
        verbose_name = "série"
        verbose_name_plural = "séries"
        ordering = ["lot", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["lot", "numero"], name="serie_numero_unique_par_lot"),
            models.CheckConstraint(condition=Q(numero__gte=1), name="serie_numero_au_moins_1"),
        ]

    @property
    def libelle(self):
        return f"Série {self.numero}"

    def __str__(self):
        return self.libelle


class QuestionDeSerie(ModeleDuClient):
    """Une question à son rang dans une série."""

    PARENTS_CLIENT = ("serie", "question")

    serie = models.ForeignKey(Serie, on_delete=models.PROTECT, related_name="questions_ordonnees")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="appartenances")
    rang = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "question de série"
        verbose_name_plural = "questions de série"
        ordering = ["serie", "rang"]
        constraints = [
            models.UniqueConstraint(fields=["serie", "rang"], name="questiondeserie_rang_unique"),
            models.UniqueConstraint(fields=["serie", "question"], name="questiondeserie_question_unique"),
            models.CheckConstraint(condition=Q(rang__gte=1), name="questiondeserie_rang_au_moins_1"),
        ]

    def __str__(self):
        return f"{self.serie} — question {self.rang}"
