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
