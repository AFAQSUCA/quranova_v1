# Chapitre 23 — Les résultats, le classement et sa validation (itération 4, étapes 4e et 4f)

> **Commit de référence :** `47061de` · **Durée :** 8 à 10 heures · **Résultat :** le calcul des résultats (**trois règles à écrire par vous**), le classement provisoire, le tableau des notations incomplètes, la validation du classement par le responsable client et ses corrections. **56 tests**.

## Objectif

| Règle | Où elle est appliquée |
|---|---|
| **REC-13** : classement conforme au barème, vérifié à la main | `tests/test_calcul.py` : un exemple **calculé à la main** |
| **RM-16** : une note ou une évaluation manquante n'est jamais zéro | un candidat incomplet n'est **pas classé** ; son score partiel reste visible |
| **§10.4** : on n'invente aucune règle de départage | sans règle applicable, les égalités restent « ex aequo » |
| **RM-18, REC-39** : seul le responsable client valide | `valider_classement` refuse l'opérateur et l'administrateur |
| **§14.2** : pas de remise avant validation | `exiger_classement_valide` |
| **REC-17** : correction motivée, version conservée | `corriger_classement` : nouvelle version, l'ancienne reste |

## Décisions (à confirmer par le règlement du client)

| N° | Décision |
|---|---|
| D47 | Total d'une évaluation = Σ (note × coefficient). Score « moyenne » = moyenne des totaux des évaluations **validées** ; score « total » = leur somme. |
| D48 | Scores **arrondis à 2 décimales** (demi supérieur) avant le classement : on classe ce qui sera publié. Classement **par épreuve** ; « élimination » n'est pas prise en charge (refus explicite). Classement « à la française » : 1, 2, 2, 4. |

## L'exemple calculé à la main

Barème : Mémorisation (max 10, coefficient 2), Tajwid (max 10, coefficient 1), Voix (max 5, coefficient 1). Total = 2 × Mémorisation + Tajwid + Voix. Trois jurés sont attendus.

| Candidat | Juré 1 | Juré 2 | Juré 3 | Totaux | Somme | Moyenne |
|---|---|---|---|---|---|---|
| A | (9, 8, 4) = 30 | (8, 9, 5) = 30 | (10, 7, 4) = 31 | 30, 30, 31 | 91 | 30,33 |
| B | (9, 9, 5) = 32 | (9, 8, 4) = 30 | (8, 8, 4) = 28 | 32, 30, 28 | 90 | 30,00 |
| C | (7, 7, 3) = 24 | (8, 8, 4) = 28 | (6, 6, 3) = 21 | 24, 28, 21 | 73 | 24,33 |
| E | (9, 8, 4) = 30 | (9, 8, 4) = 30 | (9, 8, 4) = 30 | 30, 30, 30 | 90 | 30,00 |
| D | (9, 8, 4) = 30 | (9, 7, 5) = 30 | — (non validée) | 30, 30 | 60 | 30,00 |

D n'a que 2 évaluations sur 3 : **incomplète**, donc non classée (et **pas** classée avec un 0 pour le juré 3, ce qui lui donnerait 20). B et E sont à égalité parfaite ; avec le critère prioritaire « Mémorisation » (E : 9,00 ; B : 8,67), E passe devant. **Vérifiez ce tableau avec votre règlement** : si votre formule diffère, c'est le test qu'il faut changer en premier.

## Étape A — Trois règles à écrire par vous

**Fichier `apps\resultats\tests\test_calcul.py`**

```python
"""Tests du calcul des résultats avec un exemple CALCULÉ À LA MAIN (REC-13 ; RM-16, RM-17).

Barème : Mémorisation (max 10, coefficient 2), Tajwid (max 10, coefficient 1), Voix (max 5, coefficient 1).
Total d'une évaluation = 2 x Mémorisation + Tajwid + Voix. Trois jurés sont attendus.

Notes (Mémorisation, Tajwid, Voix) de chaque juré, et totaux calculés à la main :

| Candidat | Juré 1             | Juré 2             | Juré 3             | Totaux      | Somme | Moyenne |
|----------|--------------------|--------------------|--------------------|-------------|-------|---------|
| A        | (9, 8, 4) = 30     | (8, 9, 5) = 30     | (10, 7, 4) = 31    | 30, 30, 31  | 91    | 30,33   |
| B        | (9, 9, 5) = 32     | (9, 8, 4) = 30     | (8, 8, 4) = 28     | 32, 30, 28  | 90    | 30,00   |
| C        | (7, 7, 3) = 24     | (8, 8, 4) = 28     | (6, 6, 3) = 21     | 24, 28, 21  | 73    | 24,33   |
| E        | (9, 8, 4) = 30     | (9, 8, 4) = 30     | (9, 8, 4) = 30     | 30, 30, 30  | 90    | 30,00   |
| D        | (9, 8, 4) = 30     | (9, 7, 5) = 30     | — (non validée)    | 30, 30      | 60    | 30,00   |

D n'a que 2 évaluations validées sur 3 : sa notation est INCOMPLÈTE (jamais « 0 » pour le juré 3).
B et E sont à égalité parfaite (moyenne 30,00). Moyenne de Mémorisation : B = 26/3 = 8,67 ; E = 27/3 = 9,00 ; A = 27/3 = 9,00.
"""
from decimal import Decimal

import pytest

from apps.resultats.calcul import (
    CritereCalcul,
    EvaluationCalcul,
    arrondir,
    calculer_resultat,
    classer,
    total_evaluation,
)
from apps.resultats.exceptions import NoteManquanteError, RegleNonPriseEnChargeError

D = Decimal
M, T, V = CritereCalcul("m", "Mémorisation", D(10), D(2)), CritereCalcul("t", "Tajwid", D(10), D(1)), CritereCalcul("v", "Voix", D(5), D(1))
CRITERES = [M, T, V]


def evaluation(jure, m, t, v):
    return EvaluationCalcul(jure, {"m": D(m), "t": D(t), "v": D(v)})


NOTES = {
    "A": [(9, 8, 4), (8, 9, 5), (10, 7, 4)],
    "B": [(9, 9, 5), (9, 8, 4), (8, 8, 4)],
    "C": [(7, 7, 3), (8, 8, 4), (6, 6, 3)],
    "E": [(9, 8, 4), (9, 8, 4), (9, 8, 4)],
    "D": [(9, 8, 4), (9, 7, 5)],  # le juré 3 n'a pas validé
}


def resultats(**remplacements):
    notes = {**NOTES, **remplacements}
    return [
        calculer_resultat(c, [evaluation(f"j{i}", *n) for i, n in enumerate(notes[c], 1)], CRITERES, 3)
        for c in ("A", "B", "C", "E", "D")
    ]


# --- total d'une évaluation -----------------------------------------------------------------


def test_total_ponderé_calcule_a_la_main():
    assert total_evaluation({"m": D(9), "t": D(8), "v": D(4)}, CRITERES) == D(30)  # 2x9 + 8 + 4
    assert total_evaluation({"m": D(10), "t": D(7), "v": D(4)}, CRITERES) == D(31)  # 2x10 + 7 + 4


def test_un_zero_saisi_est_une_note_valable():
    assert total_evaluation({"m": D(0), "t": D(0), "v": D(0)}, CRITERES) == D(0)
    assert total_evaluation({"m": D(0), "t": D(8), "v": D(4)}, CRITERES) == D(12)


def test_rm16_une_note_manquante_n_est_jamais_un_zero():
    with pytest.raises(NoteManquanteError):
        total_evaluation({"m": D(9), "t": D(8)}, CRITERES)  # la Voix manque


def test_les_coefficients_decimaux_sont_exacts():
    critere = CritereCalcul("x", "Critère", D(10), D("1.5"))

    assert total_evaluation({"x": D("7.3")}, [critere]) == D("10.95")


# --- résultat d'un candidat ---------------------------------------------------------------------


def test_resultat_de_a_calcule_a_la_main():
    a = resultats()[0]

    assert a.totaux_jures == (D(30), D(30), D(31))
    assert (a.score_total, a.score_moyenne) == (D("91.00"), D("30.33"))  # 91 / 3 = 30,333…
    assert a.complet is True and a.nombre_evaluations == 3 and a.nombre_attendu == 3


def test_resultats_de_b_et_c():
    _, b, c, *_ = resultats()

    assert (b.score_total, b.score_moyenne) == (D("90.00"), D("30.00"))
    assert (c.score_total, c.score_moyenne) == (D("73.00"), D("24.33"))


def test_moyennes_par_critere_calculees_a_la_main():
    a, b, _, e, _ = resultats()

    assert b.moyennes_criteres["m"] == D("8.67")  # (9 + 9 + 8) / 3
    assert e.moyennes_criteres["m"] == D("9.00")
    assert a.moyennes_criteres == {"m": D("9.00"), "t": D("8.00"), "v": D("4.33")}


def test_rm16_une_evaluation_manquante_rend_la_notation_incomplete_sans_zero_ajoute():
    d = resultats()[4]

    assert d.complet is False and d.nombre_evaluations == 2 and d.nombre_attendu == 3
    assert d.totaux_jures == (D(30), D(30))  # pas de troisième total à 0
    assert d.score_moyenne == D("30.00")  # moyenne des 2 évaluations VALIDÉES, pas (30+30+0)/3 = 20


def test_aucune_evaluation_donne_un_score_absent_et_non_zero():
    r = calculer_resultat("x", [], CRITERES, 3)

    assert r.score_moyenne is None and r.score_total is None
    assert r.totaux_jures == () and r.complet is False and r.moyennes_criteres == {}


def test_sans_juré_attendu_le_resultat_n_est_jamais_complet():
    r = calculer_resultat("x", [evaluation("j1", 9, 8, 4)], CRITERES, 0)

    assert r.complet is False


def test_l_arrondi_est_au_demi_superieur():
    assert arrondir(D("30.335")) == D("30.34") and arrondir(D("30.334")) == D("30.33")
    deux = [EvaluationCalcul("j1", {"x": D("10.00")}), EvaluationCalcul("j2", {"x": D("10.01")})]
    critere = CritereCalcul("x", "X", D(20), D(1))

    assert calculer_resultat("p", deux, [critere], 2).score_moyenne == D("10.01")  # moyenne exacte 10,005


# --- classement ----------------------------------------------------------------------------------


def lignes(classement):
    return [(ligne.participation_id, ligne.rang, ligne.ex_aequo) for ligne in classement]


def test_classement_par_moyenne_sans_regle_de_departage_calcule_a_la_main():
    classement = classer(resultats(), "moyenne")

    assert lignes(classement) == [
        ("A", 1, False),
        ("B", 2, True),   # B et E : même moyenne 30,00 → ex aequo, rang 2 pour les deux
        ("E", 2, True),
        ("C", 4, False),  # « à la française » : le rang 3 est sauté
        ("D", None, False),  # notation incomplète : non classé, jamais classé avec un zéro
    ]
    assert [ligne.score for ligne in classement[:4]] == [D("30.33"), D("30.00"), D("30.00"), D("24.33")]


def test_le_candidat_incomplet_est_present_mais_non_classe_a_la_fin():
    classement = classer(resultats(), "moyenne")

    assert classement[-1].participation_id == "D" and classement[-1].complet is False
    assert classement[-1].score == D("30.00")  # score partiel visible, mais sans rang


def test_classement_par_total():
    classement = classer(resultats(), "total")

    assert lignes(classement)[:4] == [("A", 1, False), ("B", 2, True), ("E", 2, True), ("C", 4, False)]
    assert [ligne.score for ligne in classement[:4]] == [D("91.00"), D("90.00"), D("90.00"), D("73.00")]


def test_depart_par_critere_prioritaire_memorisation():
    classement = classer(resultats(), "moyenne", "critere_prioritaire", "m")

    assert lignes(classement)[:4] == [
        ("A", 1, False),
        ("E", 2, False),  # Mémorisation 9,00 contre 8,67 pour B : E passe devant
        ("B", 3, False),
        ("C", 4, False),
    ]


def test_le_depart_ne_joue_qu_entre_candidats_a_egalite():
    """A (30,33) reste devant même si B avait une meilleure Mémorisation : le départage ne change pas les scores."""
    meilleur_b = resultats(B=[(10, 4, 1)] * 3)  # Mémorisation 10,00 mais moyenne 25,00 (totaux 25, 25, 25)
    classement = classer(meilleur_b, "moyenne", "critere_prioritaire", "m")

    assert classement[0].participation_id == "A"


def test_depart_par_moyenne_generale_ne_departage_pas_deux_moyennes_egales():
    classement = classer(resultats(), "total", "moyenne_generale")

    assert lignes(classement)[1:3] == [("B", 2, True), ("E", 2, True)]  # même moyenne générale : toujours à égalité


def test_depart_par_moyenne_generale_departage_quand_le_classement_est_au_total():
    """Au total, deux candidats à 90 points ; leurs moyennes diffèrent si l'un a plus d'évaluations… ici elles sont égales."""
    a_egalite = [
        calculer_resultat("P", [evaluation("j1", 8, 8, 4), evaluation("j2", 8, 8, 4)], CRITERES, 2),  # totaux 28, 28
        calculer_resultat("Q", [evaluation("j1", 9, 6, 4), evaluation("j2", 7, 10, 4)], CRITERES, 2),  # 28, 28
    ]

    assert [ligne.ex_aequo for ligne in classer(a_egalite, "total", "moyenne_generale")] == [True, True]


@pytest.mark.parametrize("regle", ["", "epreuve_supplementaire", "decision_comite"])
def test_sans_regle_applicable_on_n_invente_rien_les_egalites_restent(regle):
    classement = classer(resultats(), "moyenne", regle)

    assert lignes(classement)[1:3] == [("B", 2, True), ("E", 2, True)]


def test_l_ordre_d_entree_est_conserve_pour_les_egalites_parfaites():
    inverse = list(reversed(resultats()))  # D, E, C, B, A

    classement = classer(inverse, "moyenne")

    assert [l.participation_id for l in classement[1:3]] == ["E", "B"]  # E arrivait avant B


def test_quand_d_est_complete_le_classement_est_a_la_francaise_1_2_2_4_5():
    d_complet = resultats(D=[(9, 8, 4), (9, 7, 5), (8, 7, 4)])  # totaux 30, 30, 27 → moyenne 29,00

    classement = classer(d_complet, "moyenne")

    assert lignes(classement) == [("A", 1, False), ("B", 2, True), ("E", 2, True), ("D", 4, False), ("C", 5, False)]


def test_tous_a_egalite():
    meme = [calculer_resultat(c, [evaluation("j1", 9, 8, 4)], CRITERES, 1) for c in "XYZ"]

    assert lignes(classer(meme, "moyenne")) == [("X", 1, True), ("Y", 1, True), ("Z", 1, True)]


def test_aucun_resultat_donne_un_classement_vide():
    assert classer([], "moyenne") == []


@pytest.mark.parametrize("regle", ["elimination", "n_importe_quoi", ""])
def test_une_regle_de_classement_non_prise_en_charge_est_refusee(regle):
    with pytest.raises(RegleNonPriseEnChargeError):
        classer(resultats(), regle)


def test_depart_par_critere_prioritaire_exige_le_critere():
    with pytest.raises(ValueError):
        classer(resultats(), "moyenne", "critere_prioritaire", None)
```

**Fichier `apps\resultats\calcul.py`**

```python
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
    raise NotImplementedError("TODO(human) : total d'une évaluation (voir la docstring)")


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
    raise NotImplementedError("TODO(human) : résultat d'un candidat (voir la docstring)")


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
    raise NotImplementedError("TODO(human) : classement et départage (voir la docstring)")
```

```powershell
pytest apps\resultats\tests\test_calcul.py
```

Avant : `29 failed`. Après : `29 passed`.

**Indices :** `total_evaluation` : une somme de produits ; vérifiez d'abord qu'aucun critère ne manque. `calculer_resultat` : appelez `total_evaluation` sur chaque évaluation, puis moyennez avec `Decimal` (jamais de `float`) et `arrondir`. `classer` : triez les candidats **complets** par score décroissant (tri stable), puis attribuez les rangs en sautant ceux des ex aequo.

### Solution : `total_evaluation`

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
    manquants = [c.libelle for c in criteres if c.id not in notes]
    if manquants:
        raise NoteManquanteError("Note manquante : " + ", ".join(manquants) + ".")  # RM-16 : jamais zéro
    return sum((notes[c.id] * c.coefficient for c in criteres), Decimal(0))
```

</details>

### Solution : `calculer_resultat`

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
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
```

</details>

### Solution : `classer`

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
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
```

</details>

## Étape B — Le critère prioritaire (§10.4)

L'épreuve reçoit un champ `critere_prioritaire` (le règlement du client le désigne ; on ne l'invente pas). Il entre dans l'empreinte de la configuration (D14) et la validation de la configuration le **réclame** si la catégorie choisit « priorité à un critère ».

```powershell
python manage.py makemigrations concours
python manage.py migrate
```

**Fichier `apps\concours\models.py`**

```python
"""Concours, catégories, épreuves, barème et sessions (§7.2, §8.2, §14.1)."""
from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.commun.models import ModeleDuClient
from apps.concours.exceptions import ConfigurationInvalideError


class Concours(ModeleDuClient):
    """Un concours (une édition) conduit pour un client, dans le cadre d'une mission."""

    PARENTS_CLIENT = ("mission",)

    class Format(models.TextChoices):
        PRESENTIEL = "presentiel", "Présentiel"  # en ligne et hybride : V2

    class Etat(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        OUVERT = "ouvert", "Ouvert"
        EN_COURS = "en_cours", "En cours"
        SUSPENDU = "suspendu", "Suspendu"
        TERMINE = "termine", "Terminé"
        ARCHIVE = "archive", "Archivé"

    mission = models.ForeignKey(
        "clients.Mission", on_delete=models.PROTECT, related_name="concours"
    )
    nom = models.CharField(max_length=200)
    edition = models.CharField(max_length=50, blank=True, help_text="Millésime ou numéro d'édition.")
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.PRESENTIEL)
    date_debut = models.DateField()
    date_fin = models.DateField()
    # RM-27 : version unique du corpus, figée à l'ouverture. Vide tant que le concours est en brouillon.
    version_corpus = models.ForeignKey(
        "coran.VersionCorpus",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="concours",
    )
    etat = models.CharField(max_length=20, choices=Etat.choices, default=Etat.BROUILLON)
    # RM-31 : validation de la configuration par le responsable du client (qui, quand, quelle configuration).
    configuration_validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    configuration_validee_le = models.DateTimeField(null=True, blank=True)
    configuration_empreinte = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Empreinte SHA-256 de la configuration au moment de sa validation.",
    )

    class Meta:
        verbose_name = "concours"
        verbose_name_plural = "concours"
        ordering = ["-date_debut", "nom"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "nom", "edition"], name="concours_nom_edition_uniques"
            ),
            models.CheckConstraint(
                condition=Q(date_fin__gte=F("date_debut")),
                name="concours_date_fin_apres_date_debut",
            ),
            # La validation est complète ou absente : qui, quand et quelle configuration.
            models.CheckConstraint(
                condition=(
                    Q(
                        configuration_validee_par__isnull=True,
                        configuration_validee_le__isnull=True,
                        configuration_empreinte="",
                    )
                    | (
                        Q(configuration_validee_par__isnull=False, configuration_validee_le__isnull=False)
                        & ~Q(configuration_empreinte="")
                    )
                ),
                name="concours_validation_configuration_complete",
            ),
            # RM-27 et RM-31 : hors brouillon, le corpus est figé et la configuration validée.
            models.CheckConstraint(
                condition=(
                    Q(etat="brouillon")
                    | (Q(version_corpus__isnull=False) & Q(configuration_validee_le__isnull=False))
                ),
                name="concours_ouvert_exige_corpus_et_validation",
            ),
        ]

    def __str__(self):
        return f"{self.nom} {self.edition}".strip()


class Categorie(ModeleDuClient):
    """Une catégorie d'un concours : mémorisation, tajwid, tilawa, questions..."""

    PARENTS_CLIENT = ("concours",)

    class Discipline(models.TextChoices):
        MEMORISATION = "memorisation", "Mémorisation"
        TAJWID = "tajwid", "Tajwid"
        TILAWA = "tilawa", "Tilawa"
        QUESTIONS = "questions", "Questions"
        PERSONNALISEE = "personnalisee", "Personnalisée"

    class RegleClassement(models.TextChoices):
        MOYENNE = "moyenne", "Moyenne"
        TOTAL = "total", "Total"
        ELIMINATION = "elimination", "Élimination"

    class RegleDepartage(models.TextChoices):
        MOYENNE_GENERALE = "moyenne_generale", "Moyenne générale"
        CRITERE_PRIORITAIRE = "critere_prioritaire", "Critère prioritaire"
        EPREUVE_SUPPLEMENTAIRE = "epreuve_supplementaire", "Épreuve supplémentaire"
        DECISION_COMITE = "decision_comite", "Décision documentée du comité"

    concours = models.ForeignKey(Concours, on_delete=models.PROTECT, related_name="categories")
    nom = models.CharField(max_length=100)
    discipline = models.CharField(
        max_length=20, choices=Discipline.choices, default=Discipline.MEMORISATION
    )
    age_minimum = models.PositiveSmallIntegerField(null=True, blank=True)
    age_maximum = models.PositiveSmallIntegerField(null=True, blank=True)
    effectif_prevu = models.PositiveIntegerField(null=True, blank=True)
    regle_classement = models.CharField(
        max_length=20, choices=RegleClassement.choices, default=RegleClassement.MOYENNE
    )
    # Vide par défaut : le système n'invente jamais de règle de départage (§10.4).
    regle_departage = models.CharField(
        max_length=30, choices=RegleDepartage.choices, blank=True, default=""
    )

    class Meta:
        verbose_name = "catégorie"
        verbose_name_plural = "catégories"
        ordering = ["nom"]
        constraints = [
            models.UniqueConstraint(fields=["concours", "nom"], name="categorie_nom_unique_par_concours"),
            models.CheckConstraint(
                condition=(
                    Q(age_minimum__isnull=True)
                    | Q(age_maximum__isnull=True)
                    | Q(age_maximum__gte=F("age_minimum"))
                ),
                name="categorie_age_maximum_apres_age_minimum",
            ),
        ]

    def __str__(self):
        return self.nom


class Epreuve(ModeleDuClient):
    """Une épreuve d'une catégorie, avec ses paramètres de tirage (§8.2, RM-03, RM-21)."""

    PARENTS_CLIENT = ("categorie",)

    class ModeAffichage(models.TextChoices):
        ARABE_SEUL = "arabe_seul", "Arabe seul"
        ARABE_ET_TRADUCTION = "arabe_et_traduction", "Arabe avec traduction française"

    class Etat(models.TextChoices):
        EN_PREPARATION = "en_preparation", "En préparation"
        OUVERTE = "ouverte", "Ouverte"
        TERMINEE = "terminee", "Terminée"

    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="epreuves")
    nom = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField()
    # P : questions par série. T : tirages par candidat. Q = T x P est calculé (RM-03).
    questions_par_serie = models.PositiveSmallIntegerField(help_text="P")
    tirages_par_candidat = models.PositiveSmallIntegerField(default=1, help_text="T")
    # RM-21 : réutilisation des séries tirées.
    reutilisation_autre_candidat = models.BooleanField(default=False)
    reutilisation_meme_candidat_autre_epreuve = models.BooleanField(default=False)
    exclusion_definitive = models.BooleanField(default=True)
    mode_affichage = models.CharField(
        max_length=30, choices=ModeAffichage.choices, default=ModeAffichage.ARABE_SEUL
    )
    # Désactivé par défaut : en mémorisation, l'écran scène ne doit pas être visible du candidat (§9.1).
    affichage_scene = models.BooleanField(default=False)
    etat = models.CharField(max_length=20, choices=Etat.choices, default=Etat.EN_PREPARATION)
    # §10.4 : critère de départage quand la règle de la catégorie est « priorité à un critère » (aucune valeur inventée).
    critere_prioritaire = models.ForeignKey(
        "concours.CritereNotation", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Critère qui départage les égalités si la catégorie le prévoit.",
    )

    class Meta:
        verbose_name = "épreuve"
        verbose_name_plural = "épreuves"
        ordering = ["categorie", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["categorie", "ordre"], name="epreuve_ordre_unique_par_categorie"),
            models.UniqueConstraint(fields=["categorie", "nom"], name="epreuve_nom_unique_par_categorie"),
            models.CheckConstraint(
                condition=Q(questions_par_serie__gte=1), name="epreuve_p_au_moins_1"
            ),
            models.CheckConstraint(
                condition=Q(tirages_par_candidat__gte=1), name="epreuve_t_au_moins_1"
            ),
        ]

    @property
    def questions_par_candidat(self):
        """Q = T x P (RM-03) : calculé, jamais saisi."""
        return self.tirages_par_candidat * self.questions_par_serie

    def save(self, *args, **kwargs):
        if self.critere_prioritaire_id is not None and self.critere_prioritaire.epreuve_id != self.pk:
            raise ConfigurationInvalideError("Le critère prioritaire doit être un critère de cette épreuve.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom


class CritereNotation(ModeleDuClient):
    """Un critère du barème d'une épreuve : libellé, note maximale, coefficient (§7.2)."""

    PARENTS_CLIENT = ("epreuve",)

    epreuve = models.ForeignKey(Epreuve, on_delete=models.PROTECT, related_name="criteres")
    libelle = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField()
    maximum = models.DecimalField(max_digits=6, decimal_places=2)
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        verbose_name = "critère de notation"
        verbose_name_plural = "critères de notation"
        ordering = ["epreuve", "ordre"]
        constraints = [
            models.UniqueConstraint(fields=["epreuve", "ordre"], name="critere_ordre_unique_par_epreuve"),
            models.UniqueConstraint(fields=["epreuve", "libelle"], name="critere_libelle_unique_par_epreuve"),
            models.CheckConstraint(condition=Q(maximum__gt=0), name="critere_maximum_positif"),
            models.CheckConstraint(condition=Q(coefficient__gt=0), name="critere_coefficient_positif"),
        ]

    def __str__(self):
        return self.libelle


class Session(ModeleDuClient):
    """Une session de passage d'un concours : date, lieu, serveur de salle utilisé (§14.1)."""

    PARENTS_CLIENT = ("concours",)

    concours = models.ForeignKey(Concours, on_delete=models.PROTECT, related_name="sessions")
    nom = models.CharField(max_length=100)
    date = models.DateField()
    lieu = models.CharField(max_length=200, blank=True)
    serveur_de_salle = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "session"
        verbose_name_plural = "sessions"
        ordering = ["date", "nom"]
        constraints = [
            models.UniqueConstraint(fields=["concours", "nom"], name="session_nom_unique_par_concours"),
        ]

    def __str__(self):
        return f"{self.nom} ({self.date})"
```

**Fichier `apps\concours\services.py`**

```python
"""Règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31)."""
import hashlib
import json

from django.utils import timezone

from apps.audit.services import journaliser
from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.concours.models import Categorie, Concours
from apps.coran.models import VersionCorpus
from apps.utilisateurs.models import Utilisateur


def _statut_actuel_du_corpus(version_id):
    """Statut lu dans la base : l'objet en mémoire peut être périmé."""
    return VersionCorpus.objects.filter(pk=version_id).values_list("statut", flat=True).first()


def _verifier_version_utilisable(version_id):
    if _statut_actuel_du_corpus(version_id) not in (
        VersionCorpus.Statut.VALIDEE,
        VersionCorpus.Statut.ACTIVE,
    ):
        raise ConfigurationInvalideError(
            "Seule une version du corpus validée ou active peut être utilisée par un concours (RM-09)."
        )


def definir_version_corpus(concours, version):
    """Rattache une version du corpus au concours ; impossible après l'ouverture (RM-27)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La version du corpus est figée à l'ouverture du concours (RM-27)."
        )
    _verifier_version_utilisable(version.pk)
    concours.version_corpus = version
    concours.save(update_fields=["version_corpus", "modifie_le"])


def problemes_de_configuration(concours):
    """Liste ce qui manque pour que la configuration soit validable (vide si tout est en ordre)."""
    categories = list(concours.categories.order_by("nom"))
    if not categories:
        return ["Le concours n'a aucune catégorie."]
    problemes = []
    for categorie in categories:
        epreuves = list(categorie.epreuves.order_by("ordre"))
        if not epreuves:
            problemes.append(f"La catégorie « {categorie.nom} » n'a aucune épreuve.")
        for epreuve in epreuves:
            if not epreuve.criteres.exists():
                problemes.append(f"L'épreuve « {epreuve.nom} » n'a aucun critère de notation.")
        for epreuve in epreuves:
            if categorie.regle_departage == Categorie.RegleDepartage.CRITERE_PRIORITAIRE and not epreuve.critere_prioritaire_id:
                problemes.append(
                    f"L'épreuve « {epreuve.nom} » : la règle de départage « critère prioritaire » exige de désigner ce critère."
                )
    return problemes


def empreinte_configuration(concours):
    """Empreinte SHA-256 de la configuration : catégories, épreuves, barème et réglages de tirage.

    Sert à détecter qu'une configuration a changé APRÈS avoir été validée (RM-31).
    """
    description = []
    for categorie in concours.categories.order_by("nom"):
        epreuves = []
        for epreuve in categorie.epreuves.order_by("ordre"):
            epreuves.append(
                {
                    "nom": epreuve.nom,
                    "ordre": epreuve.ordre,
                    "P": epreuve.questions_par_serie,
                    "T": epreuve.tirages_par_candidat,
                    "reutilisation_autre_candidat": epreuve.reutilisation_autre_candidat,
                    "reutilisation_meme_candidat_autre_epreuve": (
                        epreuve.reutilisation_meme_candidat_autre_epreuve
                    ),
                    "exclusion_definitive": epreuve.exclusion_definitive,
                    "mode_affichage": epreuve.mode_affichage,
                    "affichage_scene": epreuve.affichage_scene,
                    **({"critere_prioritaire": epreuve.critere_prioritaire.libelle} if epreuve.critere_prioritaire_id else {}),
                    "criteres": [
                        {
                            "libelle": critere.libelle,
                            "ordre": critere.ordre,
                            "maximum": str(critere.maximum),
                            "coefficient": str(critere.coefficient),
                        }
                        for critere in epreuve.criteres.order_by("ordre")
                    ],
                }
            )
        description.append(
            {
                "nom": categorie.nom,
                "discipline": categorie.discipline,
                "age_minimum": categorie.age_minimum,
                "age_maximum": categorie.age_maximum,
                "effectif_prevu": categorie.effectif_prevu,
                "regle_classement": categorie.regle_classement,
                "regle_departage": categorie.regle_departage,
                "epreuves": epreuves,
            }
        )
    texte = json.dumps(description, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def valider_configuration(concours, utilisateur):
    """Le responsable du client valide la configuration du concours (RM-31, §6.2).

    Le prestataire exécute, le client valide : ni l'opérateur ni l'administrateur ne peuvent le faire.
    """
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != concours.organisation_id
    ):
        raise ValidationRefuseeError(
            "Seul le responsable du client concerné peut valider la configuration du concours."
        )
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La configuration ne se valide que pour un concours en brouillon."
        )
    problemes = problemes_de_configuration(concours)
    if problemes:
        raise ConfigurationInvalideError("Configuration incomplète : " + " ".join(problemes))
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError(
            "Aucune version du corpus n'est rattachée au concours (RM-27)."
        )
    concours.configuration_validee_par = utilisateur
    concours.configuration_validee_le = timezone.now()
    concours.configuration_empreinte = empreinte_configuration(concours)
    concours.save(
        update_fields=[
            "configuration_validee_par",
            "configuration_validee_le",
            "configuration_empreinte",
            "modifie_le",
        ]
    )
    journaliser(
        "concours.configuration_validee", organisation=concours.organisation, auteur=utilisateur, objet=concours,
        details={"empreinte": concours.configuration_empreinte},
    )


def ouvrir_concours(concours):
    """Ouvre un concours : configuration validée et inchangée, corpus validé ou actif (RM-27, RM-31)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            f"Seul un concours en brouillon peut être ouvert (état actuel : {concours.get_etat_display()})."
        )
    if concours.configuration_validee_le is None:
        raise ConfigurationInvalideError(
            "La configuration n'a pas été validée par le responsable du client (RM-31)."
        )
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError("Aucune version du corpus n'est rattachée au concours.")
    _verifier_version_utilisable(concours.version_corpus_id)
    if empreinte_configuration(concours) != concours.configuration_empreinte:
        raise ConfigurationInvalideError(
            "La configuration a changé depuis sa validation : "
            "le responsable du client doit la valider de nouveau (RM-31)."
        )
    concours.etat = Concours.Etat.OUVERT
    concours.save(update_fields=["etat", "modifie_le"])
    journaliser("concours.ouvert", organisation=concours.organisation, objet=concours)


def demarrer_concours(concours):
    """Passe un concours « ouvert » à « en cours » : les tirages deviennent possibles (D25)."""
    if concours.etat != Concours.Etat.OUVERT:
        raise ConfigurationInvalideError(
            f"Seul un concours ouvert peut démarrer (état actuel : {concours.get_etat_display()})."
        )
    concours.etat = Concours.Etat.EN_COURS
    concours.save(update_fields=["etat", "modifie_le"])
```

## Étape C — Le classement provisoire en base

Il n'est **jamais stocké** : il se recalcule à partir des évaluations validées.

**Fichier `apps\resultats\tests\outils.py`**

```python
"""L'exemple calculé à la main (tests/test_calcul.py), reconstruit avec de vrais modèles."""
from datetime import date

from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_critere, creer_jure, creer_participation
from apps.jury import evaluations
from apps.jury.models import AffectationJury
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage

NOTES = {
    "A": [(9, 8, 4), (8, 9, 5), (10, 7, 4)],
    "B": [(9, 9, 5), (9, 8, 4), (8, 8, 4)],
    "C": [(7, 7, 3), (8, 8, 4), (6, 6, 3)],
    "E": [(9, 8, 4), (9, 8, 4), (9, 8, 4)],
    "D": [(9, 8, 4), (9, 7, 5)],  # le 3e juré n'a pas validé
}


def construire_exemple(regle_classement="moyenne", regle_departage="", critere_prioritaire=0):
    """Renvoie ``(epreuve, participations{A..E}, jurés, critères)`` avec les évaluations VALIDÉES de l'exemple."""
    epreuve = creer_epreuve_ouverte(series=1)
    categorie = epreuve.categorie
    categorie.regle_classement, categorie.regle_departage = regle_classement, regle_departage
    categorie.save()
    criteres = [creer_critere(epreuve, maximum=m, coefficient=c, libelle=l) for l, m, c in
                (("Mémorisation", 10, 2), ("Tajwid", 10, 1), ("Voix", 5, 1))]
    if regle_departage == "critere_prioritaire":
        epreuve.critere_prioritaire = criteres[critere_prioritaire]
        epreuve.save()
    jures = [creer_jure(epreuve.organisation) for _ in range(3)]
    for jure in jures:
        AffectationJury.objects.create(jure=jure, epreuve=epreuve)
    participations = {}
    for nom, notes_par_jure in NOTES.items():
        participation = creer_participation(
            categorie, creer_candidat(epreuve.organisation, nom=f"Candidat-{nom}", prenom=nom, date_naissance=date(1990, 1, 1)), statut=Participation.Statut.ADMIS
        )
        participations[nom] = participation
        prestation = creer_prestation(epreuve, participation=participation, etat=Prestation.Etat.EN_NOTATION)
        creer_tirage(prestation, epreuve.lot.series.first())
        for jure, valeurs in zip(jures, notes_par_jure):
            evaluations.enregistrer_brouillon(jure, prestation, {str(c.pk): v for c, v in zip(criteres, valeurs)})
            evaluations.valider_evaluation(jure, prestation)
    return epreuve, participations, jures, criteres
```

**Fichier `apps\resultats\tests\test_services.py`**

```python
"""Le classement provisoire à partir de vraies évaluations validées (REC-13 ; RM-16, §11)."""
from decimal import Decimal

import pytest

from apps.commun.tests.outils import creer_jure
from apps.jury import evaluations
from apps.jury.models import AffectationJury, Evaluation
from apps.prestations.models import Prestation
from apps.resultats import services
from apps.resultats.tests.outils import NOTES, construire_exemple

D = Decimal


def resume(lignes):
    return [(l["participation"].candidat.prenom, l["rang"], l["ex_aequo"], l["score"]) for l in lignes]


@pytest.mark.django_db
def test_rec13_le_classement_provisoire_correspond_au_calcul_manuel():
    epreuve, *_ = construire_exemple()

    assert resume(services.classement_provisoire(epreuve)) == [
        ("A", 1, False, D("30.33")),
        ("B", 2, True, D("30.00")),
        ("E", 2, True, D("30.00")),
        ("C", 4, False, D("24.33")),
        ("D", None, False, D("30.00")),
    ]


@pytest.mark.django_db
def test_le_classement_par_total_et_le_depart_par_critere_prioritaire_suivent_la_configuration():
    epreuve, *_ = construire_exemple("total")
    assert [(l["participation"].candidat.prenom, l["score"]) for l in services.classement_provisoire(epreuve)][:4] == [
        ("A", D("91.00")), ("B", D("90.00")), ("E", D("90.00")), ("C", D("73.00"))]

    epreuve, *_ = construire_exemple("moyenne", "critere_prioritaire", 0)
    assert resume(services.classement_provisoire(epreuve))[:4] == [
        ("A", 1, False, D("30.33")), ("E", 2, False, D("30.00")), ("B", 3, False, D("30.00")), ("C", 4, False, D("24.33"))]


@pytest.mark.django_db
def test_rm16_le_tableau_des_notations_incompletes_nomme_le_juge_qui_manque():
    epreuve, participations, jures, _ = construire_exemple()

    (incomplete,) = services.notations_incompletes(epreuve)

    assert incomplete["participation"] == participations["D"]
    assert (incomplete["evaluations_validees"], incomplete["evaluations_attendues"]) == (2, 3)
    assert incomplete["jures_manquants"] == [jures[2].nom_complet]


@pytest.mark.django_db
def test_une_evaluation_en_brouillon_ne_compte_pas():
    epreuve, participations, jures, criteres = construire_exemple()
    prestation = Prestation.objects.get(participation=participations["D"])
    evaluations.enregistrer_brouillon(jures[2], prestation, {str(c.pk): v for c, v in zip(criteres, (10, 10, 5))})  # brouillon, non validé

    ligne = [l for l in services.classement_provisoire(epreuve) if l["participation"] == participations["D"]][0]

    assert ligne["complet"] is False and ligne["rang"] is None and ligne["score"] == D("30.00")


@pytest.mark.django_db
def test_quand_le_dernier_juge_valide_le_candidat_est_classe():
    epreuve, participations, jures, criteres = construire_exemple()
    prestation = Prestation.objects.get(participation=participations["D"])
    evaluations.enregistrer_brouillon(jures[2], prestation, {str(c.pk): v for c, v in zip(criteres, (8, 7, 4))})
    evaluations.valider_evaluation(jures[2], prestation)

    assert resume(services.classement_provisoire(epreuve)) == [
        ("A", 1, False, D("30.33")), ("B", 2, True, D("30.00")), ("E", 2, True, D("30.00")),
        ("D", 4, False, D("29.00")), ("C", 5, False, D("24.33"))]


@pytest.mark.django_db
def test_un_candidat_sans_prestation_est_incomplet_et_non_classe_jamais_zero():
    epreuve, *_ = construire_exemple()
    from apps.candidats.models import Participation
    from apps.commun.tests.outils import creer_candidat, creer_participation

    absent = creer_participation(epreuve.categorie, creer_candidat(epreuve.organisation, prenom="Z"), statut=Participation.Statut.ADMIS)

    ligne = [l for l in services.classement_provisoire(epreuve) if l["participation"] == absent][0]

    assert ligne["rang"] is None and ligne["score"] is None and ligne["evaluations_attendues"] == 3


@pytest.mark.django_db
def test_seuls_les_candidats_admis_concourent():
    epreuve, participations, *_ = construire_exemple()
    from apps.candidats.models import Participation

    Participation.objects.filter(pk=participations["C"].pk).update(statut=Participation.Statut.RETIRE)

    assert "C" not in [l["participation"].candidat.prenom for l in services.classement_provisoire(epreuve)]


@pytest.mark.django_db
def test_le_detail_par_jure_donne_les_notes_de_chaque_juré():
    epreuve, participations, jures, _ = construire_exemple()

    detail = services.detail_par_jure(participations["A"], epreuve)

    assert len(detail) == 3
    assert {"Mémorisation": D("9.00"), "Tajwid": D("8.00"), "Voix": D("4.00")} in [d["notes"] for d in detail]
    assert all(d["statut"] == "validee" for d in detail)


@pytest.mark.django_db
def test_un_critere_prioritaire_doit_appartenir_a_l_epreuve():
    from apps.commun.tests.outils import creer_critere, creer_epreuve
    from apps.concours.exceptions import ConfigurationInvalideError

    epreuve, *_ = construire_exemple()
    autre = creer_critere(creer_epreuve())
    epreuve.critere_prioritaire = autre

    with pytest.raises(ConfigurationInvalideError):
        epreuve.save()
```

**Fichier `apps\resultats\services.py`**

```python
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
```

Dans `config\settings\base.py`, ajoutez `"apps.resultats",` à `INSTALLED_APPS`.

**Fichier `apps\resultats\apps.py`**

```python
from django.apps import AppConfig


class ResultatsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.resultats"
    label = "resultats"
    verbose_name = "Résultats"
```

**Fichier `apps\resultats\exceptions.py`**

```python
"""Erreurs de l'application resultats."""


class NoteManquanteError(Exception):
    """Un critère n'a pas de note : on ne le convertit JAMAIS en zéro (RM-16)."""


class RegleNonPriseEnChargeError(Exception):
    """Une règle de classement ou de départage que le calcul automatique ne sait pas appliquer (§10.4)."""


class ClassementInvalideError(Exception):
    """Une validation ou une correction de classement refusée (RM-18, REC-39)."""
```

## Étape D — Valider le classement (RM-18)

**Fichier `apps\resultats\models.py`**

```python
"""Classement définitif : un instantané figé, validé par le responsable client (RM-18, §11, §14.2).

Le classement PROVISOIRE n'est jamais stocké (il se recalcule). Seule la validation fige un classement : les lignes
ne changent plus ensuite. Une correction postérieure crée une NOUVELLE version, motivée et identifiée comme telle ;
les versions précédentes restent.
"""
from django.db import models
from django.db.models import Q

from apps.commun.models import ModeleDuClient
from apps.resultats.exceptions import ClassementInvalideError


class Classement(ModeleDuClient):
    PARENTS_CLIENT = ("epreuve",)

    epreuve = models.ForeignKey("concours.Epreuve", on_delete=models.PROTECT, related_name="classements")
    version = models.PositiveIntegerField(default=1)
    est_correction = models.BooleanField(default=False)
    motif_correction = models.TextField(blank=True)
    valide_par = models.ForeignKey("utilisateurs.Utilisateur", on_delete=models.PROTECT, related_name="+")
    valide_le = models.DateTimeField()
    regle_classement = models.CharField(max_length=20)
    regle_departage = models.CharField(max_length=30, blank=True)
    empreinte = models.CharField(max_length=64)

    class Meta:
        verbose_name = "classement définitif"
        verbose_name_plural = "classements définitifs"
        ordering = ["epreuve", "version"]
        constraints = [
            models.UniqueConstraint(fields=["epreuve", "version"], name="classement_version_unique_par_epreuve"),
            models.CheckConstraint(
                condition=(Q(est_correction=False, version=1, motif_correction="") | Q(est_correction=True, version__gt=1) & ~Q(motif_correction="")),
                name="classement_correction_motivee",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ClassementInvalideError("Un classement validé ne se modifie pas : une correction crée une nouvelle version.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ClassementInvalideError("Un classement validé ne se supprime pas.")

    def __str__(self):
        return f"Classement de {self.epreuve} — version {self.version}" + (" (corrigée)" if self.est_correction else "")


class LigneDeClassement(ModeleDuClient):
    PARENTS_CLIENT = ("classement", "participation")

    classement = models.ForeignKey(Classement, on_delete=models.PROTECT, related_name="lignes")
    participation = models.ForeignKey("candidats.Participation", on_delete=models.PROTECT, related_name="+")
    rang = models.PositiveIntegerField(null=True, blank=True)
    ex_aequo = models.BooleanField(default=False)
    score = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    complet = models.BooleanField(default=True)
    evaluations_validees = models.PositiveSmallIntegerField(default=0)
    evaluations_attendues = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "ligne de classement"
        verbose_name_plural = "lignes de classement"
        ordering = ["classement", "rang", "participation__numero_candidat"]
        constraints = [
            models.UniqueConstraint(fields=["classement", "participation"], name="ligne_unique_par_classement"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ClassementInvalideError("Une ligne d'un classement validé ne se modifie pas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ClassementInvalideError("Une ligne d'un classement validé ne se supprime pas.")
```

```powershell
python manage.py makemigrations resultats
python manage.py migrate
```

**Fichier `apps\resultats\tests\test_validation.py`**

```python
"""Validation du classement définitif par le responsable client (RM-18 ; REC-16, REC-17, REC-39 ; §14.2)."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_utilisateur
from apps.jury import evaluations
from apps.jury.models import CorrectionNote
from apps.prestations.models import Prestation
from apps.resultats import services, validation
from apps.resultats.exceptions import ClassementInvalideError
from apps.resultats.models import Classement, LigneDeClassement
from apps.resultats.tests.outils import construire_exemple
from apps.utilisateurs.models import Utilisateur

D = Decimal


def exemple_complet(**options):
    """L'exemple, avec le 3e juré de D qui valide (plus aucune notation incomplète) : classement 1, 2, 2, 4, 5."""
    epreuve, participations, jures, criteres = construire_exemple(**options)
    prestation = Prestation.objects.get(participation=participations["D"])
    evaluations.enregistrer_brouillon(jures[2], prestation, {str(c.pk): v for c, v in zip(criteres, (8, 7, 4))})
    evaluations.valider_evaluation(jures[2], prestation)
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=epreuve.organisation)
    return epreuve, participations, jures, criteres, responsable


def corriger_une_note(epreuve, participations, jures, criteres, responsable):
    """A passe de 91 à 87 points : la correction d'une note validée change le classement."""
    prestation = Prestation.objects.get(participation=participations["A"])
    demande = evaluations.demander_correction(jures[0], prestation, criteres[0], 5, "Erreur de saisie")
    evaluations.traiter_correction(demande, responsable, True)


# --- RM-18, REC-39 ------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR])
def test_rec39_l_operateur_et_l_administrateur_ne_valident_pas_le_classement(role):
    epreuve, *_ = exemple_complet()

    with pytest.raises(ClassementInvalideError, match="responsable"):
        validation.valider_classement(epreuve, creer_utilisateur(role), confirmer_egalites=True)

    assert Classement.objects.count() == 0


@pytest.mark.django_db
def test_le_responsable_d_un_autre_client_ne_valide_pas():
    epreuve, *_ = exemple_complet()

    with pytest.raises(ClassementInvalideError, match="concerné"):
        validation.valider_classement(epreuve, creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT), confirmer_egalites=True)


@pytest.mark.django_db
def test_le_responsable_valide_et_le_classement_est_fige_comme_le_provisoire():
    epreuve, _, _, _, responsable = exemple_complet()
    provisoire = services.classement_provisoire(epreuve)

    classement = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    assert (classement.version, classement.est_correction, classement.valide_par) == (1, False, responsable)
    lignes = [(l.participation.candidat.prenom, l.rang, l.ex_aequo, l.score) for l in classement.lignes.all()]
    assert lignes == [("A", 1, False, D("30.33")), ("B", 2, True, D("30.00")), ("E", 2, True, D("30.00")),
                      ("D", 4, False, D("29.00")), ("C", 5, False, D("24.33"))]
    assert [l[1] for l in lignes] == [p["rang"] for p in provisoire]
    entree = EntreeAudit.objects.get(action="classement.valide")
    assert entree.auteur == responsable and entree.details["empreinte"] == classement.empreinte


@pytest.mark.django_db
def test_une_notation_incomplete_empeche_la_validation():
    epreuve, participations, jures, criteres = construire_exemple()  # D n'a que 2 évaluations sur 3
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=epreuve.organisation)

    with pytest.raises(ClassementInvalideError, match="incomplète pour : n° "):
        validation.valider_classement(epreuve, responsable, confirmer_egalites=True)


@pytest.mark.django_db
def test_les_egalites_sans_depart_exigent_une_confirmation_explicite():
    epreuve, _, _, _, responsable = exemple_complet()

    with pytest.raises(ClassementInvalideError, match="égalité"):
        validation.valider_classement(epreuve, responsable)

    assert Classement.objects.count() == 0
    # Avec une règle de départage applicable, plus d'égalité : pas de confirmation nécessaire.
    epreuve2, *_, responsable2 = exemple_complet(regle_departage="critere_prioritaire")
    assert validation.valider_classement(epreuve2, responsable2).lignes.filter(ex_aequo=True).count() == 0


@pytest.mark.django_db
def test_on_ne_valide_pas_deux_fois_et_on_ne_valide_pas_un_classement_vide():
    epreuve, *_, responsable = exemple_complet()
    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    with pytest.raises(ClassementInvalideError, match="déjà validé"):
        validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    from apps.commun.tests.outils import creer_epreuve
    vide = creer_epreuve()
    with pytest.raises(ClassementInvalideError, match="Aucun candidat"):
        validation.valider_classement(vide, creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=vide.organisation))


# --- Un classement validé est figé -----------------------------------------------------------------------


@pytest.mark.django_db
def test_le_classement_valide_ne_change_pas_quand_les_notes_changent_ensuite():
    epreuve, participations, jures, criteres, responsable = exemple_complet()
    classement = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    corriger_une_note(epreuve, participations, jures, criteres, responsable)

    provisoire = services.classement_provisoire(epreuve)
    assert provisoire[0]["participation"] != participations["A"] or provisoire[0]["score"] != D("30.33")  # le provisoire a bougé
    figee = classement.lignes.get(participation=participations["A"])
    assert (figee.rang, figee.score) == (1, D("30.33"))  # le définitif, non


@pytest.mark.django_db
def test_un_classement_et_ses_lignes_ne_se_modifient_ni_ne_se_suppriment():
    epreuve, *_, responsable = exemple_complet()
    classement = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    ligne = classement.lignes.first()

    for operation in (classement.save, classement.delete, ligne.save, ligne.delete):
        with pytest.raises(ClassementInvalideError):
            operation()


@pytest.mark.django_db
def test_l_empreinte_depend_du_contenu_et_les_contraintes_de_base_tiennent():
    epreuve, *_, responsable = exemple_complet()
    classement = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    lignes = services.classement_provisoire(epreuve)

    assert validation.calculer_empreinte(lignes, "moyenne", "") == classement.empreinte
    assert validation.calculer_empreinte(lignes, "total", "") != classement.empreinte
    with pytest.raises(IntegrityError), transaction.atomic():  # une correction sans motif est impossible, même en base
        Classement.objects.create(epreuve=epreuve, version=2, est_correction=True, valide_par=responsable,
                                  valide_le=classement.valide_le, regle_classement="moyenne", empreinte="x" * 64)


# --- Corrections postérieures ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_rec17_la_correction_cree_une_version_motivee_et_conserve_l_ancienne():
    epreuve, participations, jures, criteres, responsable = exemple_complet()
    v1 = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    corriger_une_note(epreuve, participations, jures, criteres, responsable)

    v2 = validation.corriger_classement(epreuve, responsable, "Correction d'une note approuvée", confirmer_egalites=True)

    assert (v2.version, v2.est_correction, v2.motif_correction) == (2, True, "Correction d'une note approuvée")
    assert validation.classement_definitif(epreuve) == v2
    assert validation.historique(epreuve) == [v1, v2]
    assert v1.lignes.get(participation=participations["A"]).rang == 1  # l'ancienne version est intacte
    entree = EntreeAudit.objects.get(action="classement.corrige")
    assert entree.details["precedente"] == 1 and entree.details["motif"].startswith("Correction")


@pytest.mark.django_db
def test_la_correction_exige_un_motif_un_responsable_un_classement_valide_et_un_changement():
    epreuve, participations, jures, criteres, responsable = exemple_complet()
    with pytest.raises(ClassementInvalideError, match="Aucun classement validé"):
        validation.corriger_classement(epreuve, responsable, "Motif")
    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    with pytest.raises(ClassementInvalideError, match="motif"):
        validation.corriger_classement(epreuve, responsable, "  ")
    with pytest.raises(ClassementInvalideError, match="responsable"):
        validation.corriger_classement(epreuve, creer_utilisateur(), "Motif")
    with pytest.raises(ClassementInvalideError, match="identique"):
        validation.corriger_classement(epreuve, responsable, "Motif", confirmer_egalites=True)


# --- Aucune remise avant validation (§14.2, REC-16) -------------------------------------------------------------


@pytest.mark.django_db
def test_rec16_aucun_classement_n_est_remis_avant_validation():
    epreuve, *_, responsable = exemple_complet()

    with pytest.raises(ClassementInvalideError, match="n'a pas été validé"):
        validation.exiger_classement_valide(epreuve)
    classement = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    assert validation.exiger_classement_valide(epreuve) == classement


@pytest.mark.django_db
def test_la_commande_corriger_classement():
    from io import StringIO

    from django.core.management import CommandError, call_command

    epreuve, participations, jures, criteres, responsable = exemple_complet()
    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    corriger_une_note(epreuve, participations, jures, criteres, responsable)
    sortie = StringIO()

    call_command("corriger_classement", str(epreuve.pk), "--utilisateur", responsable.username,
                 "--motif", "Note corrigée", "--confirmer-egalites", stdout=sortie)

    assert "version 2" in sortie.getvalue()
    with pytest.raises(CommandError, match="responsable"):
        call_command("corriger_classement", str(epreuve.pk), "--utilisateur", creer_utilisateur().username, "--motif", "x")
    with pytest.raises(CommandError, match="introuvable"):
        call_command("corriger_classement", "00000000-0000-0000-0000-000000000000", "--utilisateur", "x", "--motif", "x")
```

**Fichier `apps\resultats\validation.py`**

```python
"""Validation du classement définitif par le responsable client (RM-18, REC-39 ; §11, §14.2).

Le prestataire EXÉCUTE, le client VALIDE : ni l'opérateur ni l'administrateur ne valident (§6.2). Aucun classement
n'est remis ou publié avant cette validation (``exiger_classement_valide``).
"""
import hashlib
import json

from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.resultats import services
from apps.resultats.exceptions import ClassementInvalideError
from apps.resultats.models import Classement, LigneDeClassement
from apps.utilisateurs.models import Utilisateur


def _verifier_responsable(utilisateur, epreuve):
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != epreuve.organisation_id
    ):
        raise ClassementInvalideError("Seul le responsable du client concerné peut valider ou corriger le classement définitif.")


def calculer_empreinte(lignes, regle_classement, regle_departage):
    contenu = {
        "regles": [regle_classement, regle_departage],
        "lignes": [
            [str(l["participation"].pk), l["rang"], l["ex_aequo"], None if l["score"] is None else str(l["score"]), l["complet"]]
            for l in sorted(lignes, key=lambda l: str(l["participation"].pk))
        ],
    }
    return hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def classement_definitif(epreuve):
    """La version en vigueur (la plus récente), ou ``None`` si rien n'a été validé."""
    return Classement.objects.filter(epreuve=epreuve).order_by("-version").first()


def historique(epreuve):
    return list(Classement.objects.filter(epreuve=epreuve).order_by("version"))


def exiger_classement_valide(epreuve):
    """Aucune remise ni publication sans validation (§14.2) : renvoie le classement en vigueur ou refuse."""
    classement = classement_definitif(epreuve)
    if classement is None:
        raise ClassementInvalideError(f"Le classement de l'épreuve « {epreuve.nom} » n'a pas été validé par le responsable client.")
    return classement


def _creer(epreuve, utilisateur, lignes, version, correction, motif):
    categorie = epreuve.categorie
    classement = Classement.objects.create(
        epreuve=epreuve, version=version, est_correction=correction, motif_correction=motif,
        valide_par=utilisateur, valide_le=timezone.now(),
        regle_classement=categorie.regle_classement, regle_departage=categorie.regle_departage,
        empreinte=calculer_empreinte(lignes, categorie.regle_classement, categorie.regle_departage),
    )
    for l in lignes:
        LigneDeClassement.objects.create(
            classement=classement, participation=l["participation"], rang=l["rang"], ex_aequo=l["ex_aequo"], score=l["score"],
            complet=l["complet"], evaluations_validees=l["evaluations_validees"], evaluations_attendues=l["evaluations_attendues"],
        )
    return classement


def valider_classement(epreuve, utilisateur, confirmer_egalites=False):
    """Fige le classement actuel de l'épreuve comme classement DÉFINITIF (version 1)."""
    _verifier_responsable(utilisateur, epreuve)
    with transaction.atomic():
        if classement_definitif(epreuve) is not None:
            raise ClassementInvalideError("Ce classement est déjà validé : une modification passe par une correction motivée.")
        lignes = services.classement_provisoire(epreuve)
        if not lignes:
            raise ClassementInvalideError("Aucun candidat en compétition : il n'y a rien à valider.")
        incompletes = [l for l in lignes if not l["complet"]]
        if incompletes:
            noms = ", ".join(f"n° {l['participation'].numero_candidat}" for l in incompletes)
            raise ClassementInvalideError(f"Notation incomplète pour : {noms}. Le classement ne peut pas être validé.")
        if any(l["ex_aequo"] for l in lignes) and not confirmer_egalites:
            raise ClassementInvalideError(
                "Des candidats sont à égalité sans règle de départage applicable : confirmez que le classement est validé avec ces ex aequo."
            )
        classement = _creer(epreuve, utilisateur, lignes, 1, False, "")
        journaliser(
            "classement.valide", organisation=epreuve.organisation, auteur=utilisateur, objet=classement,
            details={"epreuve": epreuve.nom, "version": 1, "empreinte": classement.empreinte, "candidats": len(lignes),
                     "ex_aequo": any(l["ex_aequo"] for l in lignes)},
        )
    return classement


def corriger_classement(epreuve, utilisateur, motif, confirmer_egalites=False):
    """Crée une NOUVELLE version, motivée, du classement définitif (la version précédente est conservée)."""
    _verifier_responsable(utilisateur, epreuve)
    motif = (motif or "").strip()
    if not motif:
        raise ClassementInvalideError("Un motif est obligatoire pour corriger un classement validé.")
    with transaction.atomic():
        courant = classement_definitif(epreuve)
        if courant is None:
            raise ClassementInvalideError("Aucun classement validé à corriger : validez-le d'abord.")
        lignes = services.classement_provisoire(epreuve)
        categorie = epreuve.categorie
        if any(not l["complet"] for l in lignes):
            raise ClassementInvalideError("Notation incomplète : le classement corrigé ne peut pas être validé.")
        if any(l["ex_aequo"] for l in lignes) and not confirmer_egalites:
            raise ClassementInvalideError("Des candidats sont à égalité sans départage : confirmez la validation avec ces ex aequo.")
        if calculer_empreinte(lignes, categorie.regle_classement, categorie.regle_departage) == courant.empreinte:
            raise ClassementInvalideError("Le classement actuel est identique au classement validé : rien à corriger.")
        classement = _creer(epreuve, utilisateur, lignes, courant.version + 1, True, motif)
        journaliser(
            "classement.corrige", organisation=epreuve.organisation, auteur=utilisateur, objet=classement,
            details={"epreuve": epreuve.nom, "version": classement.version, "precedente": courant.version,
                     "motif": motif, "empreinte": classement.empreinte},
        )
    return classement
```

**Fichier `apps\resultats\management\commands\corriger_classement.py`**

```python
"""Commande : corrige un classement définitif (nouvelle version motivée) au nom d'un responsable client (RM-18)."""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.concours.models import Epreuve
from apps.resultats import validation
from apps.resultats.exceptions import ClassementInvalideError
from apps.utilisateurs.models import Utilisateur


class Command(BaseCommand):
    help = "Crée une nouvelle version, motivée, du classement définitif d'une épreuve (réservé au responsable client)."

    def add_arguments(self, parser):
        parser.add_argument("epreuve", help="Identifiant (UUID) de l'épreuve.")
        parser.add_argument("--utilisateur", required=True, help="Nom d'utilisateur du responsable client.")
        parser.add_argument("--motif", required=True, help="Motif de la correction (obligatoire).")
        parser.add_argument("--confirmer-egalites", action="store_true", help="Valider avec les ex aequo restants.")

    def handle(self, *args, **options):
        try:
            epreuve = Epreuve.objects.get(pk=options["epreuve"])
        except (Epreuve.DoesNotExist, ValidationError, ValueError):
            raise CommandError(f"Épreuve introuvable : {options['epreuve']}") from None
        utilisateur = Utilisateur.objects.filter(username=options["utilisateur"]).first()
        if utilisateur is None:
            raise CommandError(f"Utilisateur introuvable : {options['utilisateur']}")
        try:
            classement = validation.corriger_classement(epreuve, utilisateur, options["motif"], options["confirmer_egalites"])
        except ClassementInvalideError as erreur:
            raise CommandError(str(erreur)) from None
        self.stdout.write(self.style.SUCCESS(f"Classement corrigé : version {classement.version} (la précédente est conservée)."))
```

## Étape E — L'administration

**Fichier `apps\resultats\tests\test_admin.py`**

```python
"""Le classement dans l'administration : calcul visible, validation réservée au responsable client (RM-18)."""
import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.commun.tests.outils import creer_utilisateur
from apps.resultats.models import Classement
from apps.resultats.tests.outils import construire_exemple
from apps.resultats.tests.test_validation import exemple_complet
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def messages_de(reponse):
    return " | ".join(str(m) for m in get_messages(reponse.wsgi_request))


def lancer(client, epreuve, action):
    return client.post(reverse("admin:concours_epreuve_changelist"), {"action": action, "_selected_action": [str(epreuve.pk)]}, follow=True)


@pytest.mark.django_db
def test_la_fiche_de_l_epreuve_montre_le_classement_provisoire(client):
    epreuve, *_ = construire_exemple()
    operateur = creer_utilisateur(is_staff=True)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    client.force_login(operateur)

    contenu = client.get(reverse("admin:concours_epreuve_change", args=[epreuve.pk])).content.decode()

    assert "30.33" in contenu and "ex aequo" in contenu and "notation incomplète" in contenu


@pytest.mark.django_db
def test_seul_le_responsable_client_voit_les_actions_de_validation(client):
    epreuve, *_, responsable = exemple_complet()
    responsable.is_staff = True
    responsable.save()
    operateur = creer_utilisateur(is_staff=True)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)

    client.force_login(operateur)
    page = client.get(reverse("admin:concours_epreuve_changelist")).content.decode()
    assert "Valider le classement définitif" not in page

    client.force_login(responsable)
    page = client.get(reverse("admin:concours_epreuve_changelist")).content.decode()
    assert "Valider le classement définitif" in page and "Ouvrir l&#x27;épreuve" not in page


@pytest.mark.django_db
def test_le_responsable_valide_depuis_l_administration_apres_confirmation_des_egalites(client):
    epreuve, *_, responsable = exemple_complet()
    responsable.is_staff = True
    responsable.save()
    client.force_login(responsable)

    refus = lancer(client, epreuve, "valider_le_classement")
    assert "égalité" in messages_de(refus) and Classement.objects.count() == 0

    ok = lancer(client, epreuve, "valider_le_classement_avec_egalites")
    assert "classement validé" in messages_de(ok) and Classement.objects.count() == 1


@pytest.mark.django_db
def test_un_classement_valide_se_consulte_mais_ne_s_ecrit_pas_dans_l_administration(client):
    epreuve, *_, responsable = exemple_complet()
    from apps.resultats import validation

    classement = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    client.force_login(Utilisateur.objects.create_superuser("admin-res", password="x"))

    assert client.get(reverse("admin:resultats_classement_change", args=[classement.pk])).status_code == 200
    assert client.get(reverse("admin:resultats_classement_add")).status_code == 403
    assert client.post(reverse("admin:resultats_classement_delete", args=[classement.pk]), {"post": "yes"}).status_code == 403
```

**Fichier `apps\resultats\admin.py`**

```python
"""Les classements définitifs se consultent ; ils ne se créent que par la validation du responsable client (RM-18)."""
from django.contrib import admin

from apps.commun.admin import ConsultationSeule, InlineDuClient
from apps.resultats.models import Classement, LigneDeClassement


class LigneInline(InlineDuClient):
    model = LigneDeClassement
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Classement)
class ClassementAdmin(ConsultationSeule):
    list_display = ("epreuve", "version", "est_correction", "valide_par", "valide_le")
    list_filter = ("est_correction", "epreuve")
    inlines = [LigneInline]
```

**Fichier `apps\concours\admin.py`**

```python
"""Administration de la configuration d'un concours (§7.2, RM-27, RM-31)."""
from django.contrib import admin

from apps.commun.admin import AdminDuClient, InlineDuClient, appliquer_action, role_admin
from apps.concours import services
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from apps.prestations.services import ouvrir_epreuve
from apps.resultats import services as services_resultats
from apps.resultats import validation
from apps.utilisateurs.models import Utilisateur


@admin.register(Concours)
class ConcoursAdmin(AdminDuClient):
    list_display = ("nom", "edition", "mission", "etat", "version_corpus", "configuration_validee_le")
    list_filter = ("etat", "organisation")
    search_fields = ("nom", "edition")
    actions = ["valider_la_configuration", "ouvrir", "demarrer"]

    def get_readonly_fields(self, request, obj=None):
        # L'état et la validation ne changent que par les services (RM-27, RM-31, D14).
        lecture = ["etat", "configuration_validee_par", "configuration_validee_le", "configuration_empreinte", "documents"]
        if obj is not None and obj.etat != Concours.Etat.BROUILLON:
            lecture.append("version_corpus")  # figée à l'ouverture (RM-27)
        return lecture

    @admin.display(description="Documents à remettre")
    def documents(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        return format_html(
            '<a href="{}" target="_blank">Procès-verbal (imprimable)</a> · <a href="{}">Export des données (CSV)</a>',
            reverse("resultats:proces_verbal", args=[obj.pk]), reverse("resultats:export", args=[obj.pk]),
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if role_admin(request.user) == Utilisateur.Role.RESPONSABLE_CLIENT:
            return {"valider_la_configuration": actions["valider_la_configuration"]}
        actions.pop("valider_la_configuration", None)  # le client valide, le prestataire exécute
        return actions

    @admin.action(description="Valider la configuration (responsable client)")
    def valider_la_configuration(self, request, queryset):
        appliquer_action(request, queryset, lambda c: services.valider_configuration(c, request.user),
                         "configuration validée")

    @admin.action(description="Ouvrir le concours")
    def ouvrir(self, request, queryset):
        appliquer_action(request, queryset, services.ouvrir_concours, "concours ouvert")

    @admin.action(description="Démarrer le concours (les tirages deviennent possibles)")
    def demarrer(self, request, queryset):
        appliquer_action(request, queryset, services.demarrer_concours, "concours en cours")


@admin.register(Categorie)
class CategorieAdmin(AdminDuClient):
    list_display = ("nom", "concours", "discipline", "age_minimum", "age_maximum", "regle_classement")
    list_filter = ("discipline", "concours")
    search_fields = ("nom",)


class CritereInline(InlineDuClient):
    model = CritereNotation


@admin.register(Epreuve)
class EpreuveAdmin(AdminDuClient):
    list_display = ("nom", "categorie", "ordre", "questions_par_serie", "tirages_par_candidat", "etat")
    list_filter = ("etat", "categorie__concours")
    search_fields = ("nom",)
    inlines = [CritereInline]
    readonly_fields = ("etat", "classement_provisoire")
    actions = ["ouvrir", "valider_le_classement", "valider_le_classement_avec_egalites"]

    @admin.display(description="Classement provisoire (recalculé à chaque affichage)")
    def classement_provisoire(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        try:
            lignes = services_resultats.classement_provisoire(obj)
        except NotImplementedError as regle:
            return f"Calcul indisponible : {regle}"
        except Exception as erreur:  # une règle non prise en charge ne doit pas casser la fiche
            return f"Calcul indisponible : {erreur}"
        if not lignes:
            return "Aucun candidat en compétition."
        return format_html(
            "<table><tr><th>Rang</th><th>Candidat</th><th>Score</th><th>Évaluations</th><th></th></tr>{}</table>",
            format_html_join(
                "",
                "<tr><td>{}</td><td>n° {} — {}</td><td>{}</td><td>{}/{}</td><td>{}</td></tr>",
                (
                    (
                        ("—" if l["rang"] is None else f"{l['rang']}{' (ex aequo)' if l['ex_aequo'] else ''}"),
                        l["participation"].numero_candidat, l["participation"].candidat.nom_complet,
                        "—" if l["score"] is None else l["score"],
                        l["evaluations_validees"], l["evaluations_attendues"],
                        "" if l["complet"] else "notation incomplète : " + ", ".join(l["jures_manquants"]),
                    )
                    for l in lignes
                ),
            ),
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if role_admin(request.user) == Utilisateur.Role.RESPONSABLE_CLIENT:
            return {k: v for k, v in actions.items() if k.startswith("valider_le_classement")}
        for nom in ("valider_le_classement", "valider_le_classement_avec_egalites"):
            actions.pop(nom, None)  # le client valide, le prestataire exécute (RM-18)
        return actions

    @admin.action(description="Valider le classement définitif (responsable client)")
    def valider_le_classement(self, request, queryset):
        appliquer_action(request, queryset, lambda e: validation.valider_classement(e, request.user), "classement validé")

    @admin.action(description="Valider le classement définitif, en confirmant les ex aequo")
    def valider_le_classement_avec_egalites(self, request, queryset):
        appliquer_action(
            request, queryset, lambda e: validation.valider_classement(e, request.user, confirmer_egalites=True), "classement validé"
        )

    @admin.action(description="Ouvrir l'épreuve (lot complet et suffisant)")
    def ouvrir(self, request, queryset):
        appliquer_action(request, queryset, ouvrir_epreuve, "épreuve ouverte")


@admin.register(Session)
class SessionAdmin(AdminDuClient):
    list_display = ("nom", "concours", "date", "lieu")
    list_filter = ("concours",)
```

**Fichier `apps\commun\admin.py`**

```python
"""Socle de l'administration : accès par rôle, cloisonnement par client, erreurs métier lisibles.

Pendant les phases de développement, l'administration Django sert de console provisoire
(les vrais écrans de gestion viendront ensuite). Elle applique déjà les règles du projet :

- l'accès dépend du RÔLE (§6), pas des permissions Django par modèle ;
- chaque liste est filtrée par client (règle absolue n°3, RM-20), y compris les menus
  déroulants des formulaires, pour qu'on ne puisse pas rattacher une donnée à un autre client ;
- une règle métier violée donne un message d'erreur, jamais une page d'erreur 500.
"""
from django.contrib import admin, messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect

from apps.candidats.exceptions import ParticipationInvalideError, TirageImpossibleError
from apps.clients.models import Organisation
from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.models import ModeleDuClient
from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.jury.exceptions import AffectationInvalideError as AffectationJuryInvalideError
from apps.prestations.exceptions import (
    AnnulationInvalideError,
    AppelInvalideError,
    OuvertureEpreuveRefuseeError,
    PrestationInvalideError,
    TerminalInvalideError,
    TirageInvalideError,
)
from apps.questions.exceptions import QuestionInvalideError, SerieInvalideError
from apps.resultats.exceptions import ClassementInvalideError, NoteManquanteError, RegleNonPriseEnChargeError
from apps.jury.exceptions import CorrectionInvalideError, EvaluationInterditeError
from apps.utilisateurs.exceptions import AffectationInvalideError
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

ERREURS_METIER = (
    IncoherenceOrganisationError,
    ParticipationInvalideError,
    TirageImpossibleError,
    ConfigurationInvalideError,
    ValidationRefuseeError,
    AffectationInvalideError,
    AffectationJuryInvalideError,
    PrestationInvalideError,
    TirageInvalideError,
    AnnulationInvalideError,
    AppelInvalideError,
    OuvertureEpreuveRefuseeError,
    QuestionInvalideError,
    SerieInvalideError,
    ClassementInvalideError,
    NoteManquanteError,
    RegleNonPriseEnChargeError,
    CorrectionInvalideError,
    EvaluationInterditeError,
    IntegrityError,
)

ROLES_ECRITURE = (Utilisateur.Role.ADMINISTRATEUR, Utilisateur.Role.OPERATEUR)
ROLES_LECTURE = ROLES_ECRITURE + (Utilisateur.Role.RESPONSABLE_CLIENT,)


def role_admin(utilisateur):
    """Le rôle effectif dans l'administration, ou ``None`` si l'accès est refusé."""
    if not (utilisateur.is_active and utilisateur.is_staff):
        return None
    if utilisateur.is_superuser:
        return Utilisateur.Role.ADMINISTRATEUR
    return utilisateur.role


def organisations_visibles(utilisateur):
    """``None`` = toutes les organisations ; sinon l'ensemble des identifiants autorisés (RM-20)."""
    role = role_admin(utilisateur)
    if role == Utilisateur.Role.ADMINISTRATEUR:
        return None
    if role == Utilisateur.Role.RESPONSABLE_CLIENT:
        return {utilisateur.organisation_id}
    if role == Utilisateur.Role.OPERATEUR:
        return set(missions_accessibles(utilisateur).values_list("organisation_id", flat=True))
    return set()


class AdminDuClient(admin.ModelAdmin):
    """Base de toute administration d'une table client."""

    champ_organisation = "organisation"  # pour Organisation : "pk"

    # --- accès par rôle ---
    def has_module_permission(self, request):
        return role_admin(request.user) in ROLES_LECTURE

    def has_view_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_LECTURE

    def has_add_permission(self, request):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_change_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_delete_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    # --- cloisonnement par client ---
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        visibles = organisations_visibles(request.user)
        if visibles is None:
            return queryset
        return queryset.filter(**{f"{self.champ_organisation}__in": visibles})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        visibles = organisations_visibles(request.user)
        cible = db_field.remote_field.model
        if visibles is not None and "queryset" not in kwargs:
            if issubclass(cible, ModeleDuClient):
                kwargs["queryset"] = cible._default_manager.filter(organisation_id__in=visibles)
            elif cible is Organisation:
                kwargs["queryset"] = Organisation.objects.filter(pk__in=visibles)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        # L'organisation d'une donnée dépendante est recopiée de son parent (ModeleDuClient).
        if getattr(self.model, "PARENTS_CLIENT", ()):
            exclude.append("organisation")
        return exclude

    # --- erreurs métier : un message, pas une erreur 500 ---
    def executer_metier(self, request, fonction):
        """Exécute ``fonction`` ; une règle métier violée devient un message, et rien n'est enregistré."""
        try:
            with transaction.atomic():
                fonction()
        except ERREURS_METIER as erreur:
            messages.error(request, f"Enregistrement refusé : {erreur}")
            request._echec_metier = True

    def save_model(self, request, obj, form, change):
        self.executer_metier(request, lambda: super(AdminDuClient, self).save_model(request, obj, form, change))

    def save_related(self, request, form, formsets, change):
        if not getattr(request, "_echec_metier", False):
            super().save_related(request, form, formsets, change)

    def response_add(self, request, obj, post_url_continue=None):
        if getattr(request, "_echec_metier", False):
            return HttpResponseRedirect(request.get_full_path())
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if getattr(request, "_echec_metier", False):
            return HttpResponseRedirect(request.get_full_path())
        return super().response_change(request, obj)


class InlineDuClient(admin.TabularInline):
    """Base des tableaux imbriqués : même cloisonnement et mêmes exclusions."""

    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        visibles = organisations_visibles(request.user)
        cible = db_field.remote_field.model
        if visibles is not None and "queryset" not in kwargs and issubclass(cible, ModeleDuClient):
            kwargs["queryset"] = cible._default_manager.filter(organisation_id__in=visibles)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if getattr(self.model, "PARENTS_CLIENT", ()):
            exclude.append("organisation")
        return exclude

    def has_view_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_LECTURE

    def has_add_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_change_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_delete_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE


class ConsultationSeule(AdminDuClient):
    """Une donnée qui se consulte mais ne s'écrit que par les services (ex. un tirage, §14.2)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def appliquer_action(request, queryset, fonction, succes):
    """Applique un service à chaque objet sélectionné ; un message par succès ou par refus."""
    for objet in queryset:
        try:
            with transaction.atomic():
                fonction(objet)
        except (*ERREURS_METIER, NotImplementedError) as erreur:
            messages.error(request, f"{objet} : {erreur}")
        else:
            messages.success(request, f"{objet} : {succes}.")
```

```powershell
pytest apps\resultats
```

Dans l'administration : la fiche d'une **épreuve** montre le classement provisoire recalculé ; le **responsable client** (seul) voit l'action « Valider le classement définitif ».

## Questions de compréhension

1. Pourquoi D (2 évaluations sur 3) n'est-il pas classé, plutôt que classé avec son score partiel ?
2. Pourquoi arrondir **avant** de classer ?
3. Pourquoi le classement provisoire n'est-il pas stocké alors que le définitif l'est ?

<details>
<summary>Réponses</summary>

1. Sa moyenne sur 2 jurés n'est pas comparable à celle des autres sur 3 : le classer reviendrait à supposer ce que le juré manquant aurait donné. RM-16 : manquant ≠ zéro, et ≠ « moyenne des autres ».
2. Parce que ce qui est publié (2 décimales) doit être ce qui est classé : deux candidats affichés à 30,33 ne peuvent pas être départagés par des décimales que personne ne voit.
3. Le provisoire dépend d'évaluations encore susceptibles de changer : le stocker créerait une 2ᵉ source de vérité qui se désynchronise. Le définitif est un **acte** (validé par une personne, à une date) : il doit rester tel qu'il a été validé, même si des notes sont corrigées ensuite.
</details>

## Journal d'apprentissage

Notez la règle de classement du règlement d'un client réel et vérifiez que votre calcul la donne sur un exemple.

## Commit proposé

```text
Itération 4e-4f : résultats, classement et validation par le responsable client
```
