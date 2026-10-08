"""Plan des diapositives d'une prestation (§8.3 étape 4, §9.2, D39).

Le plan est une liste de dictionnaires qui ne contiennent QUE des références : l'identifiant du verset et les
bornes (``debut``, ``fin``) du segment dans son texte. Le texte lui-même est relu dans le corpus au moment de
l'envoyer (``textes_du_plan``) : on ne copie jamais un verset (règle absolue n°1), donc une version du corpus
figée (RM-27) garantit que le texte affiché est celui du corpus validé.
"""
from apps.coran.models import Verset
from apps.coran.passages import resoudre_passage
from apps.prestations.models import Prestation, Tirage
from apps.presentation.exceptions import PlanImpossibleError
from apps.presentation.segmentation import segmenter_verset
from apps.questions.models import Question

TAILLE_SEGMENT_PAR_DEFAUT = 180  # caractères par diapositive (D42) ; deviendra un réglage de l'épreuve


def construire_plan(prestation, taille_max=TAILLE_SEGMENT_PAR_DEFAUT, segmenter=segmenter_verset):
    """Construit la suite ordonnée des diapositives des séries tirées par la prestation.

    Pour chaque question : un intercalaire « Question n/P », ses diapositives (un verset ou un segment de
    verset chacune), puis « Fin de la question » ; « Fin de la série » après la dernière question (§8.3).
    """
    tirages = list(
        prestation.tirages.filter(statut=Tirage.Statut.VALIDE).select_related("serie").order_by("rang")
    )
    if not tirages:
        raise PlanImpossibleError("Aucun tirage valide : il n'y a rien à présenter.")
    if len(tirages) < prestation.epreuve.tirages_par_candidat:
        raise PlanImpossibleError("Tous les tirages prévus ne sont pas encore effectués : la série n'est pas tirée.")

    plan = []

    def ajouter(type_, **champs):
        plan.append({"type": type_, **champs})

    for tirage in tirages:
        serie = tirage.serie
        liaisons = list(serie.questions_ordonnees.select_related("question__passage").order_by("rang"))
        total = len(liaisons)
        for liaison in liaisons:
            question = liaison.question
            repere = {"serie": serie.libelle, "question_rang": liaison.rang, "question_total": total}
            if question.type == Question.Type.PASSAGE_CORANIQUE:
                passage = question.passage
                ajouter("intercalaire_question", libelle=passage.libelle, **repere)
                versets = resoudre_passage(passage.debut, passage.fin, question.version_corpus)
                for verset in versets:
                    segments = segmenter(verset.texte, taille_max)
                    debut = 0
                    for rang, segment in enumerate(segments, start=1):
                        ajouter(
                            "verset", verset_id=verset.pk,
                            reference=f"{verset.sourate.numero}:{verset.numero}",
                            segment_rang=rang, segment_total=len(segments),
                            debut=debut, fin=debut + len(segment), **repere,
                        )
                        debut += len(segment)
            else:
                ajouter("intercalaire_question", libelle="Énoncé", **repere)
                ajouter("enonce", question_id=str(question.pk), **repere)
            ajouter("fin_question", **repere)
        ajouter("fin_serie", serie=serie.libelle)

    total_diapositives = len(plan)
    for index, diapositive in enumerate(plan):
        diapositive["index"] = index
        diapositive["total"] = total_diapositives
    return plan


def textes_du_plan(plan):
    """``{index: texte}`` des diapositives qui en ont un, lu dans le corpus (une seule requête pour les versets)."""
    identifiants = {d["verset_id"] for d in plan if d["type"] == "verset"}
    versets = {v.pk: v.texte for v in Verset.objects.filter(pk__in=identifiants).only("texte")}
    textes = {}
    for d in plan:
        if d["type"] == "verset":
            textes[d["index"]] = versets[d["verset_id"]][d["debut"] : d["fin"]]
        elif d["type"] == "enonce":
            textes[d["index"]] = Question.objects.values_list("enonce", flat=True).get(pk=d["question_id"])
    return textes
