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
