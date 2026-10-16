# Chapitre 12 — Questions, lots et séries (itération 2, première partie)

> **Étape du plan :** 3.1 à 3.2 (préparation du tirage) · **Durée :** 3 à 4 heures · **Commit de référence :** `967318d` · **Résultat :** l'application `questions` (`Question`, `PassageCoranique`, `Lot`, `Serie`, `QuestionDeSerie`) et **45 tests**.

## Objectif

Préparer ce que le tirage va distribuer : une **banque de questions** par client, et, pour chaque épreuve, un **lot** de **séries** de P questions chacune (§8.1, §8.2).

```text
Épreuve ── Lot ── Série 1 ── Question (rang 1)
                          ├─ Question (rang 2)
                          └─ Question (rang P)
```

| Règle | Où elle est appliquée |
|---|---|
| **§8.4 / REC-04, REC-05** : références vérifiées, texte jamais saisi | `creer_question_passage` (vérifie avant d'écrire) ; `PassageCoranique` ne stocke que des numéros |
| **Règle absolue n°1** | aucun champ texte sur `PassageCoranique` (un test le vérifie) |
| **RM-20** : séparation des clients | `PARENTS_CLIENT` + contrôle dans `composer_serie` |
| **RM-22** : exactement P questions par série | `composer_serie` (avant écriture) et `series_incompletes` (contrôle a posteriori) |
| **RM-23** : questions de la version du corpus du concours | `composer_serie` |

## Décisions

| N° | Décision |
|---|---|
| D24 | Un lot par épreuve en V1 (`OneToOneField`) ; le partage entre épreuves (RM-21.b) viendra plus tard. |
| D25 | Tirage possible seulement si concours « en cours » et épreuve « ouverte » *(chapitre suivant)*. |
| D26 | Annulation d'un tirage : motif et auteur obligatoires *(chapitre suivant)*. |

## Étape A — Dossiers et réglages

```powershell
New-Item -ItemType Directory "apps\questions\tests" -Force | Out-Null
New-Item -ItemType File "apps\questions\__init__.py", "apps\questions\tests\__init__.py" -Force | Out-Null
```

Dans `config\settings\base.py`, ajoutez `"apps.questions",` à `INSTALLED_APPS` (après `apps.jury`).

## Étape B — Les tests d'abord

**Fichier `apps\questions\tests\outils.py`**

```python
"""Fabriques de test pour les questions, lots et séries."""
from apps.commun.tests.outils import creer_organisation
from apps.questions import services
from apps.questions.models import PassageCoranique, Question


def creer_question(organisation=None, version=None, **champs):
    """Question « énoncé » sans corpus, ou « passage coranique » si ``version`` est donnée."""
    organisation = organisation or creer_organisation()
    if version is None:
        return services.creer_question_enonce(organisation, champs.get("enonce", "Question de test"))
    question = Question.objects.create(
        organisation=organisation, type=Question.Type.PASSAGE_CORANIQUE, version_corpus=version
    )
    PassageCoranique.objects.create(
        question=question, sourate_debut=1, verset_debut=1, sourate_fin=1, verset_fin=3
    )
    return question
```

**Fichier `apps\questions\tests\test_modeles.py`**

```python
"""Tests des modèles Question et PassageCoranique (§8.4, §14.1)."""
import pytest
from django.db import IntegrityError, transaction

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import creer_organisation, creer_version_validee
from apps.questions.exceptions import QuestionInvalideError
from apps.questions.models import PassageCoranique, Question


def une_question(**champs):
    valeurs = {"organisation": creer_organisation(), "type": Question.Type.PASSAGE_CORANIQUE}
    valeurs.update(champs)
    if valeurs["type"] == Question.Type.PASSAGE_CORANIQUE:
        valeurs.setdefault("version_corpus", creer_version_validee())
    return Question.objects.create(**valeurs)


def un_passage(question=None, **champs):
    valeurs = {
        "question": question or une_question(),
        "sourate_debut": 2,
        "verset_debut": 142,
        "sourate_fin": 2,
        "verset_fin": 150,
    }
    valeurs.update(champs)
    return PassageCoranique.objects.create(**valeurs)


@pytest.mark.django_db
def test_une_question_passage_coranique_exige_une_version_du_corpus():
    """RM-23 : une question coranique est rattachée à une version du corpus."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Question.objects.create(
            organisation=creer_organisation(), type=Question.Type.PASSAGE_CORANIQUE
        )


@pytest.mark.django_db
def test_une_question_enonce_exige_un_enonce():
    with pytest.raises(IntegrityError), transaction.atomic():
        Question.objects.create(organisation=creer_organisation(), type=Question.Type.ENONCE)

    question = Question.objects.create(
        organisation=creer_organisation(), type=Question.Type.ENONCE, enonce="Quel est le nom de la sourate 1 ?"
    )
    assert question.version_corpus is None


@pytest.mark.django_db
def test_le_passage_prend_l_organisation_de_sa_question():
    passage = un_passage()

    assert passage.organisation_id == passage.question.organisation_id


@pytest.mark.django_db
def test_rm20_le_passage_ne_peut_pas_avoir_une_autre_organisation_que_sa_question():
    with pytest.raises(IncoherenceOrganisationError):
        un_passage(organisation=creer_organisation())


@pytest.mark.django_db
def test_une_question_n_a_qu_un_passage():
    passage = un_passage()

    with pytest.raises(IntegrityError), transaction.atomic():
        un_passage(passage.question)


@pytest.mark.django_db
def test_un_passage_ne_se_rattache_pas_a_une_question_enonce():
    question = une_question(type=Question.Type.ENONCE, enonce="Texte libre")

    with pytest.raises(QuestionInvalideError):
        un_passage(question)


@pytest.mark.django_db
def test_rec05_la_fin_ne_precede_pas_le_debut_en_base():
    for champs in (
        {"sourate_debut": 3, "sourate_fin": 2},
        {"verset_debut": 150, "verset_fin": 142},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            un_passage(**champs)


@pytest.mark.django_db
def test_un_passage_peut_traverser_une_sourate_et_tenir_en_un_verset():
    un_passage(sourate_debut=2, verset_debut=285, sourate_fin=3, verset_fin=10)
    un_passage(sourate_debut=1, verset_debut=1, sourate_fin=1, verset_fin=1)

    assert PassageCoranique.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("champ", ["sourate_debut", "verset_debut", "sourate_fin", "verset_fin"])
def test_les_numeros_sont_au_moins_1(champ):
    with pytest.raises(IntegrityError), transaction.atomic():
        un_passage(**{champ: 0})


@pytest.mark.django_db
def test_libelle_d_un_passage():
    assert un_passage().libelle == "Sourate 2, versets 142 à 150"
    assert un_passage(verset_debut=5, verset_fin=5).libelle == "Sourate 2, verset 5"
    assert (
        un_passage(sourate_debut=2, verset_debut=285, sourate_fin=3, verset_fin=10).libelle
        == "Sourate 2, verset 285 à sourate 3, verset 10"
    )
```

**Fichier `apps\questions\tests\test_services.py`**

```python
"""Tests de la création d'une question à partir de références coraniques (§8.4, REC-04, REC-05)."""
import pytest

from apps.commun.tests.outils import creer_organisation, creer_version_validee
from apps.coran.exceptions import ReferenceInvalideError
from apps.coran.tests.outils import creer_sourate
from apps.questions import services
from apps.questions.models import PassageCoranique, Question


@pytest.fixture
def version(db):
    """Une version de corpus minimale : sourate 1 (7 versets), sourate 2 (286), sourate 3 (200)."""
    version = creer_version_validee()
    for numero, versets in ((1, 7), (2, 286), (3, 200)):
        creer_sourate(version, numero=numero, nombre_versets=versets, ordre_revelation=numero)
    return version


@pytest.mark.django_db
def test_rec04_creation_d_une_question_a_partir_de_references(version):
    organisation = creer_organisation()

    question = services.creer_question_passage(organisation, version, (2, 142), (2, 150))

    assert question.type == Question.Type.PASSAGE_CORANIQUE
    assert question.organisation == organisation and question.version_corpus == version
    assert question.passage.libelle == "Sourate 2, versets 142 à 150"


@pytest.mark.django_db
def test_le_service_n_enregistre_aucun_texte_coranique(version):
    """Règle absolue n°1 : on stocke des références, jamais le texte des versets."""
    question = services.creer_question_passage(creer_organisation(), version, (2, 142), (2, 150))

    assert question.enonce == ""
    champs_texte = {f.name for f in PassageCoranique._meta.get_fields()}
    assert not ({"texte", "contenu"} & champs_texte)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "debut, fin, extrait",
    [
        ((200, 1), (200, 5), "sourate 200"),  # sourate inexistante
        ((2, 287), (2, 288), "286"),  # verset inexistant
        ((2, 0), (2, 5), "verset"),  # verset nul
        ((2, 150), (2, 142), "précède"),  # fin avant le début
        ((3, 1), (2, 5), "précède"),
    ],
)
def test_rec05_reference_invalide_refusee_avec_explication(version, debut, fin, extrait):
    with pytest.raises(ReferenceInvalideError, match=extrait):
        services.creer_question_passage(creer_organisation(), version, debut, fin)

    assert Question.objects.count() == 0 and PassageCoranique.objects.count() == 0


@pytest.mark.django_db
def test_une_version_sans_sourate_est_refusee():
    with pytest.raises(ReferenceInvalideError, match="aucune sourate"):
        services.creer_question_passage(creer_organisation(), creer_version_validee(), (1, 1), (1, 2))


@pytest.mark.django_db
def test_un_passage_qui_traverse_les_sourates_est_accepte_a_la_creation(version):
    question = services.creer_question_passage(creer_organisation(), version, (2, 285), (3, 10))

    assert question.passage.libelle == "Sourate 2, verset 285 à sourate 3, verset 10"


@pytest.mark.django_db
def test_creer_une_question_enonce():
    organisation = creer_organisation()

    question = services.creer_question_enonce(organisation, "  Quel est le sens de « al-Fatiha » ?  ")

    assert question.type == Question.Type.ENONCE
    assert question.enonce == "Quel est le sens de « al-Fatiha » ?"
    assert question.version_corpus is None


@pytest.mark.django_db
def test_un_enonce_vide_est_refuse():
    from apps.questions.exceptions import QuestionInvalideError

    with pytest.raises(QuestionInvalideError):
        services.creer_question_enonce(creer_organisation(), "   ")
```

**Fichier `apps\questions\tests\test_lots.py`**

```python
"""Tests des modèles Lot, Serie et QuestionDeSerie (§8.2, RM-20, RM-22)."""
import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import creer_epreuve, creer_organisation
from apps.questions.models import Lot, QuestionDeSerie, Serie
from apps.questions.tests.outils import creer_question


def un_lot(epreuve=None):
    return Lot.objects.create(epreuve=epreuve or creer_epreuve())


def une_serie(lot=None, numero=1):
    return Serie.objects.create(lot=lot or un_lot(), numero=numero)


@pytest.mark.django_db
def test_le_lot_prend_l_organisation_de_son_epreuve():
    epreuve = creer_epreuve()

    assert un_lot(epreuve).organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_rm20_le_lot_ne_peut_pas_avoir_une_autre_organisation_que_son_epreuve():
    with pytest.raises(IncoherenceOrganisationError):
        Lot.objects.create(epreuve=creer_epreuve(), organisation=creer_organisation())


@pytest.mark.django_db
def test_une_epreuve_n_a_qu_un_lot():
    epreuve = creer_epreuve()
    un_lot(epreuve)

    with pytest.raises(IntegrityError), transaction.atomic():
        un_lot(epreuve)


@pytest.mark.django_db
def test_une_epreuve_ne_peut_pas_etre_supprimee_si_elle_a_un_lot():
    epreuve = un_lot().epreuve

    with pytest.raises(ProtectedError):
        epreuve.delete()


@pytest.mark.django_db
def test_libelle_et_numero_de_serie_uniques_par_lot():
    lot = un_lot()
    serie = une_serie(lot, 4)

    assert serie.libelle == "Série 4" and serie.organisation_id == lot.organisation_id
    with pytest.raises(IntegrityError), transaction.atomic():
        une_serie(lot, 4)
    une_serie(lot, 5)
    une_serie(numero=4)  # un autre lot : accepté


@pytest.mark.django_db
def test_le_numero_de_serie_est_au_moins_1():
    with pytest.raises(IntegrityError), transaction.atomic():
        une_serie(numero=0)


@pytest.mark.django_db
def test_rang_unique_et_question_unique_par_serie():
    serie = une_serie()
    premiere = creer_question(serie.organisation)
    QuestionDeSerie.objects.create(serie=serie, question=premiere, rang=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionDeSerie.objects.create(serie=serie, question=creer_question(serie.organisation), rang=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionDeSerie.objects.create(serie=serie, question=premiere, rang=2)


@pytest.mark.django_db
def test_le_rang_est_au_moins_1():
    serie = une_serie()

    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionDeSerie.objects.create(serie=serie, question=creer_question(serie.organisation), rang=0)


@pytest.mark.django_db
def test_rm20_une_question_d_un_autre_client_n_entre_pas_dans_la_serie():
    serie = une_serie()

    with pytest.raises(IncoherenceOrganisationError):
        QuestionDeSerie.objects.create(serie=serie, question=creer_question(creer_organisation()), rang=1)


@pytest.mark.django_db
def test_les_questions_d_une_serie_sont_lues_dans_l_ordre_du_rang():
    serie = une_serie()
    q1, q2 = creer_question(serie.organisation), creer_question(serie.organisation)
    QuestionDeSerie.objects.create(serie=serie, question=q2, rang=2)
    QuestionDeSerie.objects.create(serie=serie, question=q1, rang=1)

    assert [qs.question for qs in serie.questions_ordonnees.all()] == [q1, q2]
```

**Fichier `apps\questions\tests\test_services_lots.py`**

```python
"""Tests de la composition des lots et séries (§8.2 ; RM-20, RM-22, RM-23)."""
import pytest

from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_epreuve,
    creer_organisation,
    creer_version_validee,
)
from apps.questions import services
from apps.questions.exceptions import SerieInvalideError
from apps.questions.models import Lot, QuestionDeSerie, Serie
from apps.questions.tests.outils import creer_question


@pytest.fixture
def epreuve(db):
    """Une épreuve avec P = 3, dans un concours rattaché à une version du corpus."""
    concours = creer_concours(version_corpus=creer_version_validee())
    return creer_epreuve(creer_categorie(concours), questions_par_serie=3)


def questions(epreuve, n, **champs):
    return [creer_question(epreuve.organisation, **champs) for _ in range(n)]


@pytest.mark.django_db
def test_obtenir_lot_cree_le_lot_une_seule_fois(epreuve):
    premier = services.obtenir_lot(epreuve)
    second = services.obtenir_lot(epreuve)

    assert premier == second and Lot.objects.count() == 1


@pytest.mark.django_db
def test_composer_une_serie_numerote_et_ordonne(epreuve):
    lot = services.obtenir_lot(epreuve)
    qs = questions(epreuve, 6)

    s1 = services.composer_serie(lot, qs[:3])
    s2 = services.composer_serie(lot, qs[3:])

    assert (s1.numero, s2.numero) == (1, 2)
    assert [x.question for x in s1.questions_ordonnees.all()] == qs[:3]
    assert [x.rang for x in s2.questions_ordonnees.all()] == [1, 2, 3]


@pytest.mark.django_db
@pytest.mark.parametrize("n", [0, 2, 4])
def test_rm22_une_serie_contient_exactement_p_questions(epreuve, n):
    lot = services.obtenir_lot(epreuve)

    with pytest.raises(SerieInvalideError, match="3"):
        services.composer_serie(lot, questions(epreuve, n))

    assert Serie.objects.count() == 0 and QuestionDeSerie.objects.count() == 0


@pytest.mark.django_db
def test_une_question_n_est_pas_repetee_dans_une_serie(epreuve):
    lot = services.obtenir_lot(epreuve)
    a, b = questions(epreuve, 2)

    with pytest.raises(SerieInvalideError, match="plusieurs fois"):
        services.composer_serie(lot, [a, b, a])

    assert Serie.objects.count() == 0


@pytest.mark.django_db
def test_rm20_une_question_d_un_autre_client_est_refusee(epreuve):
    lot = services.obtenir_lot(epreuve)
    qs = questions(epreuve, 2) + [creer_question(creer_organisation())]

    with pytest.raises(SerieInvalideError, match="client"):
        services.composer_serie(lot, qs)

    assert Serie.objects.count() == 0


@pytest.mark.django_db
def test_rm23_un_passage_d_une_autre_version_du_corpus_est_refuse(epreuve):
    lot = services.obtenir_lot(epreuve)
    autre_version = creer_version_validee()
    qs = questions(epreuve, 2) + [creer_question(epreuve.organisation, version=autre_version)]

    with pytest.raises(SerieInvalideError, match="version"):
        services.composer_serie(lot, qs)

    assert Serie.objects.count() == 0


@pytest.mark.django_db
def test_rm23_un_passage_de_la_version_du_concours_est_accepte(epreuve):
    lot = services.obtenir_lot(epreuve)
    version = epreuve.categorie.concours.version_corpus
    qs = questions(epreuve, 2) + [creer_question(epreuve.organisation, version=version)]

    assert services.composer_serie(lot, qs).questions_ordonnees.count() == 3


@pytest.mark.django_db
def test_rm23_un_passage_est_refuse_tant_que_le_concours_n_a_pas_de_version():
    epreuve = creer_epreuve(creer_categorie(creer_concours()), questions_par_serie=1)
    lot = services.obtenir_lot(epreuve)
    passage = creer_question(epreuve.organisation, version=creer_version_validee())

    with pytest.raises(SerieInvalideError, match="version"):
        services.composer_serie(lot, [passage])


@pytest.mark.django_db
def test_series_incompletes_signale_les_series_hors_p(epreuve):
    lot = services.obtenir_lot(epreuve)
    bonne = services.composer_serie(lot, questions(epreuve, 3))
    # Une série construite en contournant le service (import, admin) : le contrôle la rattrape.
    bancale = Serie.objects.create(lot=lot, numero=2)
    QuestionDeSerie.objects.create(serie=bancale, question=creer_question(epreuve.organisation), rang=1)
    vide = Serie.objects.create(lot=lot, numero=3)

    assert services.series_incompletes(lot) == [bancale, vide]
    assert bonne not in services.series_incompletes(lot)
```

```powershell
pytest apps\questions
```

Attendu : erreurs de collecte (`ModuleNotFoundError`). C'est voulu.

## Étape C — Le code

**Fichier `apps\questions\apps.py`**

```python
from django.apps import AppConfig


class QuestionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.questions"
    label = "questions"
    verbose_name = "Questions"
```

**Fichier `apps\questions\exceptions.py`**

```python
"""Erreurs de l'application questions."""


class QuestionInvalideError(Exception):
    """Une question ou un passage coranique qui viole une règle (§8.4)."""


class SerieInvalideError(Exception):
    """Une série ou un lot qui viole une règle (RM-20, RM-22, RM-23)."""
```

**Fichier `apps\questions\models.py`**

```python
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
```

**Fichier `apps\questions\services.py`**

```python
"""Création des questions de la banque d'un client (§8.4)."""
from django.db import transaction
from django.db.models import Count, Max

from apps.coran import services as services_coran
from apps.coran.exceptions import ReferenceInvalideError
from apps.coran.models import Sourate
from apps.questions.exceptions import QuestionInvalideError, SerieInvalideError
from apps.questions.models import Lot, PassageCoranique, Question, QuestionDeSerie, Serie


def creer_question_passage(organisation, version, debut, fin):
    """Crée une question « passage coranique » à partir de deux références (REC-04, REC-05).

    Les références sont vérifiées dans ``version`` (existence, puis ordre canonique) AVANT
    toute écriture. On n'enregistre que les références : le texte reste dans le corpus.
    """
    plan = dict(
        Sourate.objects.filter(version=version).order_by("numero").values_list("numero", "nombre_versets")
    )
    if not plan:
        raise ReferenceInvalideError(f"La version du corpus n° {version.pk} ne contient aucune sourate.")
    services_coran.verifier_reference(plan, debut)
    services_coran.verifier_reference(plan, fin)
    services_coran.verifier_ordre_passage(debut, fin)

    with transaction.atomic():
        question = Question.objects.create(
            organisation=organisation, type=Question.Type.PASSAGE_CORANIQUE, version_corpus=version
        )
        PassageCoranique.objects.create(
            question=question,
            sourate_debut=debut[0],
            verset_debut=debut[1],
            sourate_fin=fin[0],
            verset_fin=fin[1],
        )
    return question


def creer_question_enonce(organisation, enonce):
    """Crée une question « énoncé » (texte libre saisi par l'opérateur)."""
    enonce = enonce.strip()
    if not enonce:
        raise QuestionInvalideError("L'énoncé d'une question ne peut pas être vide.")
    return Question.objects.create(organisation=organisation, type=Question.Type.ENONCE, enonce=enonce)


# --- Lots et séries (§8.2) ---------------------------------------------------


def obtenir_lot(epreuve):
    """Le lot de l'épreuve, créé au premier appel (D24 : un lot par épreuve)."""
    lot, _ = Lot.objects.get_or_create(epreuve=epreuve, defaults={"organisation_id": epreuve.organisation_id})
    return lot


def _verifier_questions_de_serie(lot, questions):
    """Contrôles d'une série AVANT écriture : RM-22, doublons, RM-20, RM-23."""
    epreuve = lot.epreuve
    p = epreuve.questions_par_serie
    if len(questions) != p:
        raise SerieInvalideError(
            f"Une série de l'épreuve « {epreuve.nom} » contient exactement {p} questions "
            f"(RM-22) : {len(questions)} fournie(s)."
        )
    if len({q.pk for q in questions}) != len(questions):
        raise SerieInvalideError("Une même question ne peut pas figurer plusieurs fois dans une série.")
    version_du_concours = epreuve.categorie.concours.version_corpus_id
    for question in questions:
        if question.organisation_id != lot.organisation_id:
            raise SerieInvalideError("Une question d'un autre client ne peut pas entrer dans ce lot (RM-20).")
        if question.type == Question.Type.PASSAGE_CORANIQUE and question.version_corpus_id != version_du_concours:
            raise SerieInvalideError(
                "Un passage coranique doit venir de la version du corpus du concours (RM-23) : "
                "la version de la question diffère, ou le concours n'a pas encore de version."
            )


def composer_serie(lot, questions):
    """Crée la série suivante du lot avec ``questions`` dans l'ordre donné.

    Le numéro est le plus élevé du lot plus un, sous verrou : deux ajouts simultanés ne
    reçoivent pas le même numéro.
    """
    questions = list(questions)
    _verifier_questions_de_serie(lot, questions)
    with transaction.atomic():
        Lot.objects.select_for_update().get(pk=lot.pk)
        dernier = lot.series.aggregate(numero=Max("numero"))["numero"]
        serie = Serie.objects.create(lot=lot, numero=(dernier or 0) + 1)
        for rang, question in enumerate(questions, start=1):
            QuestionDeSerie.objects.create(serie=serie, question=question, rang=rang)
    return serie


def series_incompletes(lot):
    """Les séries qui ne contiennent pas exactement P questions (RM-22), pour contrôle avant ouverture."""
    p = lot.epreuve.questions_par_serie
    return list(lot.series.annotate(n=Count("questions_ordonnees")).exclude(n=p).order_by("numero"))
```

```powershell
python manage.py makemigrations questions
python manage.py migrate
pytest apps\questions
```

Attendu : `45 passed`. Puis `pytest` complet : **434 réussis**, plus les 66 échecs des règles `TODO(human)` de `apps\coran\services.py`.

## Pourquoi ces choix

- **Références, pas texte.** Si `PassageCoranique` copiait le texte, une correction du corpus ne se propagerait pas, et on pourrait afficher un verset différent de celui du corpus validé (RM-27). Avec des références, le texte vient toujours de la version figée du concours.
- **Contraintes en base ET contrôle dans le service.** La base protège contre un oubli (import, administration) ; le service donne un message clair avant d'écrire. `series_incompletes` rattrape une série fabriquée en contournant le service.
- **Le service ne dépend pas de la traversée de sourates** (votre `TODO(human)` `references_du_passage`) : créer une question ne fait que vérifier deux références et leur ordre.

## Questions de compréhension

1. Pourquoi la disponibilité d'une série n'est-elle pas un champ de `Serie` ?
2. Pourquoi `composer_serie` verrouille-t-elle le lot pendant qu'elle calcule le numéro ?

<details>
<summary>Réponses</summary>

1. Elle se déduit des tirages ; la stocker créerait deux sources de vérité qui se désynchronisent (D2).
2. Sans verrou, deux ajouts simultanés liraient le même « dernier numéro » et créeraient deux séries de même numéro ; la contrainte d'unicité ferait échouer l'un des deux. Le verrou les met en file.
</details>

## Journal d'apprentissage

Notez la différence entre une règle en base (contrainte) et une règle en service, et un exemple de chaque dans ce chapitre.

## Commit proposé

```text
Itération 2 : questions, lots et séries (RM-20, RM-22, RM-23)
```
