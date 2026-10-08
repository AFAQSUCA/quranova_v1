"""Création des questions de la banque d'un client (§8.4)."""
from django.db import transaction

from apps.coran import services as services_coran
from apps.coran.exceptions import ReferenceInvalideError
from apps.coran.models import Sourate
from apps.questions.exceptions import QuestionInvalideError
from apps.questions.models import PassageCoranique, Question


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
