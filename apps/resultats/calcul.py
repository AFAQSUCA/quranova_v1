"""Calcul des résultats et classement (§10.3, §10.4 ; RM-16, RM-17 ; REC-13).

Module PUR : aucune base de données, aucun réseau. Il reçoit des valeurs et renvoie des valeurs, donc il se teste avec
un exemple calculé à la main (voir ``tests/test_calcul.py``).

Définitions (D47, D48 — à confirmer par le règlement du client) :
- le TOTAL d'une évaluation (un juré) = somme des notes pondérées : Σ (note × coefficient) ;
- le SCORE « moyenne » d'un candidat = moyenne des totaux de ses évaluations VALIDÉES ; le score « total » = leur somme ;
- les scores sont arrondis à 2 décimales (demi supérieur) AVANT le classement : on classe ce qui sera publié ;
- une note manquante n'est jamais un zéro (RM-16) : un candidat dont il manque une évaluation est « incomplet » et
  n'est PAS classé (son score n'est pas comparable) ;
- classement « à la française » en cas d'égalité : 1, 2, 2, 4 ;
- le système n'invente aucune règle de départage (§10.4) : sans règle applicable, les égalités restent « ex aequo ».
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from apps.resultats.exceptions import NoteManquanteError, RegleNonPriseEnChargeError  # noqa: F401

DEUX_DECIMALES = Decimal("0.01")


@dataclass(frozen=True)
class CritereCalcul:
    id: str
    libelle: str
    maximum: Decimal
    coefficient: Decimal


@dataclass(frozen=True)
class EvaluationCalcul:
    """Une évaluation VALIDÉE d'un juré : ``notes`` associe l'identifiant d'un critère à sa note."""

    jure_id: str
    notes: dict


@dataclass(frozen=True)
class ResultatCalcule:
    participation_id: str
    totaux_jures: tuple          # un total par évaluation validée, dans l'ordre reçu
    nombre_evaluations: int
    nombre_attendu: int
    complet: bool                # toutes les évaluations attendues sont validées
    score_moyenne: Decimal | None  # None s'il n'y a AUCUNE évaluation (jamais 0)
    score_total: Decimal | None
    moyennes_criteres: dict = field(default_factory=dict)  # moyenne des notes brutes par critère


@dataclass(frozen=True)
class LigneClassement:
    participation_id: str
    rang: int | None             # None : non classé (notation incomplète)
    ex_aequo: bool
    score: Decimal | None
    complet: bool


def arrondir(valeur):
    return valeur.quantize(DEUX_DECIMALES, rounding=ROUND_HALF_UP)


def total_evaluation(notes, criteres):
    """Total pondéré d'UNE évaluation : Σ (note × coefficient).

    TODO(human) : écrivez la règle. ``notes`` : {identifiant du critère: note (Decimal)} ; ``criteres`` : liste de
    ``CritereCalcul``. Si une note manque pour un critère, levez ``NoteManquanteError`` (RM-16 : jamais zéro).
    Un zéro SAISI est une note valable. Renvoyez un ``Decimal`` exact (non arrondi).
    """
    manquants = [c.libelle for c in criteres if c.id not in notes]
    if manquants:
        raise NoteManquanteError("Note manquante : " + ", ".join(manquants) + ".")  # RM-16 : jamais zéro
    return sum((notes[c.id] * c.coefficient for c in criteres), Decimal(0))


def calculer_resultat(participation_id, evaluations, criteres, nombre_attendu):
    """Résultat d'un candidat à partir de ses évaluations validées.

    TODO(human) : écrivez la règle. ``evaluations`` : liste d'``EvaluationCalcul`` (VALIDÉES seulement) ;
    ``nombre_attendu`` : nombre de jurés dont l'évaluation est requise. Renvoyez un ``ResultatCalcule`` :
    - ``totaux_jures`` : ``total_evaluation`` de chaque évaluation, dans l'ordre ;
    - ``complet`` : vrai si ``nombre_attendu`` > 0 et que toutes les évaluations attendues sont là ;
    - ``score_moyenne`` / ``score_total`` : moyenne / somme des totaux, ARRONDIES à 2 décimales (``arrondir``) ;
      ``None`` (jamais 0) s'il n'y a aucune évaluation ;
    - ``moyennes_criteres`` : pour chaque critère, la moyenne (arrondie à 2 décimales) des notes brutes reçues.
    """
    totaux = tuple(total_evaluation(e.notes, criteres) for e in evaluations)
    n = len(totaux)
    moyennes_criteres = {
        c.id: arrondir(sum((e.notes[c.id] for e in evaluations), Decimal(0)) / n) for c in criteres
    } if n else {}
    return ResultatCalcule(
        participation_id=participation_id,
        totaux_jures=totaux,
        nombre_evaluations=n,
        nombre_attendu=nombre_attendu,
        complet=nombre_attendu > 0 and n >= nombre_attendu,
        score_moyenne=arrondir(sum(totaux, Decimal(0)) / n) if n else None,
        score_total=arrondir(sum(totaux, Decimal(0))) if n else None,
        moyennes_criteres=moyennes_criteres,
    )


def classer(resultats, regle_classement, regle_departage="", critere_prioritaire_id=None):
    """Classe des ``ResultatCalcule`` et renvoie une ``LigneClassement`` par candidat, dans l'ordre du classement.

    TODO(human) : écrivez la règle. Contrat (voir ``test_calcul.py``) :
    - ``regle_classement`` « moyenne » classe sur ``score_moyenne``, « total » sur ``score_total`` (plus grand =
      meilleur) ; « elimination » (ou toute autre valeur) lève ``RegleNonPriseEnChargeError`` ;
    - seuls les résultats ``complet`` sont classés ; les autres reçoivent ``rang=None`` et viennent APRÈS les classés,
      dans leur ordre d'arrivée ;
    - classement à la française : deux candidats à égalité parfaite ont le même rang, le suivant saute (1, 2, 2, 4) ;
    - départage (``regle_departage``) appliqué UNIQUEMENT entre candidats à égalité de score :
      « moyenne_generale » compare ``score_moyenne`` ; « critere_prioritaire » compare
      ``moyennes_criteres[critere_prioritaire_id]`` ; vide, « epreuve_supplementaire » ou « decision_comite » :
      aucun départage automatique (§10.4 : on n'invente rien) ;
    - tout candidat encore à égalité après départage a ``ex_aequo=True`` ; les autres ``False`` ;
    - l'ordre des candidats parfaitement à égalité est celui de l'entrée (stable).
    """
    if regle_classement not in ("moyenne", "total"):
        raise RegleNonPriseEnChargeError(f"Règle de classement « {regle_classement} » non prise en charge.")
    if regle_departage == "critere_prioritaire" and critere_prioritaire_id is None:
        raise ValueError("Le départage par critère prioritaire exige l'identifiant du critère.")

    def score(r):
        return r.score_moyenne if regle_classement == "moyenne" else r.score_total

    def departage(r):
        if regle_departage == "moyenne_generale":
            return r.score_moyenne
        if regle_departage == "critere_prioritaire":
            return r.moyennes_criteres.get(critere_prioritaire_id)
        return None  # aucune règle applicable automatiquement : on n'invente rien (§10.4)

    classes = [r for r in resultats if r.complet]
    autres = [r for r in resultats if not r.complet]
    # tri stable : meilleur score d'abord, puis meilleur départage ; les égalités gardent l'ordre d'entrée
    classes.sort(key=lambda r: (score(r), departage(r) if departage(r) is not None else Decimal(0)), reverse=True)

    cles = [(score(r), departage(r)) for r in classes]
    lignes, rang = [], 0
    for i, r in enumerate(classes):
        if i == 0 or cles[i] != cles[i - 1]:
            rang = i + 1
        ex_aequo = (i > 0 and cles[i] == cles[i - 1]) or (i + 1 < len(classes) and cles[i] == cles[i + 1])
        lignes.append(LigneClassement(r.participation_id, rang, ex_aequo, score(r), True))
    lignes += [LigneClassement(r.participation_id, None, False, score(r), False) for r in autres]
    return lignes
