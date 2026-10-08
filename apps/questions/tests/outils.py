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
