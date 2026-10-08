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
