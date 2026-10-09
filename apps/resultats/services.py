"""Lecture des résultats en base et classement provisoire (§10.3, §11 ; RM-16, RM-17).

Le classement provisoire n'est JAMAIS stocké : il se recalcule à la demande à partir des évaluations VALIDÉES
(comme la disponibilité d'une série, D2). Seule la validation par le responsable client fige un classement
définitif (étape suivante).
"""
from decimal import Decimal

from apps.candidats.models import Participation
from apps.concours.models import Categorie
from apps.jury.models import Evaluation
from apps.jury.evaluations import statut_notation
from apps.prestations.models import Prestation
from apps.resultats import calcul
from apps.resultats.calcul import CritereCalcul, EvaluationCalcul


def criteres_de_calcul(epreuve):
    return [
        CritereCalcul(str(c.pk), c.libelle, c.maximum, c.coefficient) for c in epreuve.criteres.order_by("ordre")
    ]


def participations_en_competition(epreuve):
    """Les participations admises de la catégorie de l'épreuve (les retirés et non admis ne concourent pas)."""
    return (
        Participation.objects.filter(categorie_id=epreuve.categorie_id, statut=Participation.Statut.ADMIS)
        .select_related("candidat").order_by("numero_candidat")
    )


def _evaluations_validees(prestation):
    if prestation is None:
        return []
    evaluations = Evaluation.objects.filter(prestation=prestation, statut=Evaluation.Statut.VALIDEE).prefetch_related("notes")
    return [
        EvaluationCalcul(str(e.jure_id), {str(n.critere_id): n.valeur for n in e.notes.all()})
        for e in evaluations.order_by("jure__nom", "jure__prenom")
    ]


def _jures_attendus(epreuve, prestation):
    if prestation is not None:
        return statut_notation(prestation)
    from apps.jury.models import AffectationJury

    return [(a.jure, "non_commencee") for a in AffectationJury.objects.filter(epreuve=epreuve, jure__actif=True).select_related("jure")]


def classement_provisoire(epreuve):
    """Le classement actuel de l'épreuve : une ligne par candidat en compétition, classés d'abord, incomplets ensuite.

    Chaque ligne : ``participation``, ``rang`` (``None`` si non classé), ``ex_aequo``, ``score`` (``None`` sans
    aucune évaluation), ``complet``, ``evaluations_validees``, ``evaluations_attendues``, ``jures_manquants``.
    """
    categorie = epreuve.categorie
    criteres = criteres_de_calcul(epreuve)
    prestations = {p.participation_id: p for p in Prestation.objects.filter(epreuve=epreuve)}
    participations = list(participations_en_competition(epreuve))
    resultats, manquants = [], {}
    for participation in participations:
        prestation = prestations.get(participation.pk)
        attendus = _jures_attendus(epreuve, prestation)
        manquants[str(participation.pk)] = [jure.nom_complet for jure, statut in attendus if statut != "validee"]
        resultats.append(
            calcul.calculer_resultat(str(participation.pk), _evaluations_validees(prestation), criteres, len(attendus))
        )
    par_id = {str(p.pk): p for p in participations}
    brut = {r.participation_id: r for r in resultats}
    lignes = calcul.classer(
        resultats, categorie.regle_classement, categorie.regle_departage,
        str(epreuve.critere_prioritaire_id) if epreuve.critere_prioritaire_id else None,
    )
    return [
        {
            "participation": par_id[ligne.participation_id], "rang": ligne.rang, "ex_aequo": ligne.ex_aequo,
            "score": ligne.score, "complet": ligne.complet,
            "evaluations_validees": brut[ligne.participation_id].nombre_evaluations,
            "evaluations_attendues": brut[ligne.participation_id].nombre_attendu,
            "jures_manquants": manquants[ligne.participation_id],
        }
        for ligne in lignes
    ]


def notations_incompletes(epreuve):
    """Le tableau des candidats dont la notation est incomplète (§11, vue n° 5), avec les jurés qui manquent."""
    return [ligne for ligne in classement_provisoire(epreuve) if not ligne["complet"]]


def detail_par_jure(participation, epreuve):
    """Les notes détaillées par juré d'un candidat (§11 vue n° 4) : réservé aux personnes autorisées par la vue."""
    prestation = Prestation.objects.filter(participation=participation, epreuve=epreuve).first()
    if prestation is None:
        return []
    return [
        {
            "jure": e.jure.nom_complet,
            "statut": e.statut,
            "notes": {n.critere.libelle: n.valeur for n in e.notes.select_related("critere")},
            "observation": e.observation,
        }
        for e in Evaluation.objects.filter(prestation=prestation).select_related("jure").order_by("jure__nom")
    ]
