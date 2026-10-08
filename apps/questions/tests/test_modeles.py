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
