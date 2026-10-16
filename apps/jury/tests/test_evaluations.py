"""Tests de l'évaluation par les jurés (§10 ; RM-15, RM-16 ; REC-11, REC-12, REC-17)."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_critere, creer_jure, creer_utilisateur
from apps.jury import evaluations
from apps.jury.exceptions import (
    CorrectionInvalideError,
    EvaluationIncompleteError,
    EvaluationInterditeError,
    EvaluationValideeError,
    NoteInvalideError,
)
from apps.jury.models import AffectationJury, CorrectionNote, Evaluation, Note
from apps.prestations.models import Prestation
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage
from apps.utilisateurs.models import Utilisateur


def poste(etat=Prestation.Etat.EN_NOTATION, jures=1):
    """(prestation, [jurés affectés], [critères]) : 3 critères (maximums 10, 10, 5)."""
    epreuve = creer_epreuve_ouverte(series=2)
    criteres = [creer_critere(epreuve, maximum=m, coefficient=c) for m, c in ((10, 2), (10, 1), (5, 1))]
    liste = []
    for _ in range(jures):
        jure = creer_jure(epreuve.organisation)
        AffectationJury.objects.create(jure=jure, epreuve=epreuve)
        liste.append(jure)
    prestation = creer_prestation(epreuve, etat=etat)
    creer_tirage(prestation, epreuve.lot.series.first())
    return prestation, liste, criteres


def notes_completes(criteres, valeurs=(9, 8, 4)):
    return {str(c.pk): v for c, v in zip(criteres, valeurs)}


def actions():
    return list(EntreeAudit.objects.values_list("action", flat=True))


# --- Brouillon -----------------------------------------------------------------------


@pytest.mark.django_db
def test_rec11_la_note_est_enregistree_pour_le_bon_jure_la_bonne_prestation():
    prestation, (jure1, jure2), criteres = poste(jures=2)

    evaluations.enregistrer_brouillon(jure1, prestation, notes_completes(criteres, (9, 8, 4)))
    evaluations.enregistrer_brouillon(jure2, prestation, notes_completes(criteres, (5, 6, 3)))

    e1, e2 = (Evaluation.objects.get(jure=j, prestation=prestation) for j in (jure1, jure2))
    assert [n.valeur for n in e1.notes.all()] == [Decimal("9"), Decimal("8"), Decimal("4")]
    assert [n.valeur for n in e2.notes.all()] == [Decimal("5"), Decimal("6"), Decimal("3")]
    assert e1.organisation_id == prestation.organisation_id


@pytest.mark.django_db
def test_rec12_une_note_omise_n_est_pas_un_zero():
    prestation, (jure,), criteres = poste()

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 0, str(criteres[1].pk): 7})
    etat = evaluations.etat_evaluation(prestation, evaluation)

    valeurs = {ligne["libelle"]: ligne["valeur"] for ligne in etat["criteres"]}
    assert valeurs[criteres[0].libelle] == Decimal("0")  # un zéro saisi : c'est une note
    assert valeurs[criteres[2].libelle] is None  # une note omise : manquante, pas zéro
    assert etat["manquants"] == [criteres[2].libelle] and etat["complete"] is False
    assert evaluation.notes.count() == 2  # pas de ligne pour la note manquante


@pytest.mark.django_db
def test_effacer_une_note_la_rend_manquante():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[1].pk): None})

    assert evaluation.notes.count() == 2
    assert evaluations.etat_evaluation(prestation, evaluation)["manquants"] == [criteres[1].libelle]


@pytest.mark.django_db
def test_les_criteres_non_cites_ne_changent_pas_et_l_observation_est_gardee():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres), observation="Très bien")

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 7})

    assert evaluation.notes.get(critere=criteres[0]).valeur == Decimal("7")
    assert evaluation.notes.get(critere=criteres[1]).valeur == Decimal("8")
    assert evaluation.observation == "Très bien"


@pytest.mark.django_db
@pytest.mark.parametrize("valeur", ["11", "-1", "abc", "NaN", "Infinity", "7.555", True, "10.01"])
def test_les_valeurs_hors_bareme_ou_invalides_sont_refusees(valeur):
    prestation, (jure,), criteres = poste()

    with pytest.raises(NoteInvalideError):
        evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): valeur})

    assert Note.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("saisie, attendu", [("7,5", "7.50"), ("7.5", "7.50"), (" 8 ", "8.00"), (0, "0.00"), ("10", "10.00")])
def test_les_formats_de_saisie_acceptes(saisie, attendu):
    prestation, (jure,), criteres = poste()

    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): saisie})

    assert evaluation.notes.get().valeur == Decimal(attendu)


@pytest.mark.django_db
def test_un_critere_d_une_autre_epreuve_est_refuse():
    prestation, (jure,), _ = poste()
    _, _, autres_criteres = poste()

    with pytest.raises(NoteInvalideError, match="critère"):
        evaluations.enregistrer_brouillon(jure, prestation, {str(autres_criteres[0].pk): 5})


@pytest.mark.django_db
def test_rm15_un_jure_non_affecte_ne_note_pas():
    prestation, _, criteres = poste()
    intrus = creer_jure(prestation.organisation)

    with pytest.raises(EvaluationInterditeError, match="affecté"):
        evaluations.enregistrer_brouillon(intrus, prestation, notes_completes(criteres))


@pytest.mark.django_db
def test_rm20_un_jure_d_un_autre_client_ne_note_pas():
    prestation, _, criteres = poste()

    with pytest.raises(EvaluationInterditeError, match="clients"):
        evaluations.enregistrer_brouillon(creer_jure(), prestation, notes_completes(criteres))


@pytest.mark.django_db
def test_un_jure_inactif_ne_note_pas():
    prestation, (jure,), criteres = poste()
    jure.actif = False
    jure.save()

    with pytest.raises(EvaluationInterditeError, match="inactif"):
        evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))


@pytest.mark.django_db
@pytest.mark.parametrize("etat, permis", [
    (Prestation.Etat.EN_ATTENTE, False), (Prestation.Etat.TIRE, False), (Prestation.Etat.EN_AFFICHAGE, True),
    (Prestation.Etat.EN_PAUSE, True), (Prestation.Etat.EN_NOTATION, True), (Prestation.Etat.CLOTUREE, False),
    (Prestation.Etat.ANNULEE, False),
])
def test_la_saisie_est_possible_des_l_affichage_jusqu_a_la_cloture(etat, permis):
    prestation, (jure,), criteres = poste(etat=etat)

    if permis:
        evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    else:
        with pytest.raises(EvaluationInterditeError):
            evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))


# --- Validation ----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_rec12_une_evaluation_incomplete_ne_se_valide_pas_et_signale_ce_qui_manque():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 9})

    with pytest.raises(EvaluationIncompleteError) as erreur:
        evaluations.valider_evaluation(jure, prestation)

    assert erreur.value.manquants == [criteres[1].libelle, criteres[2].libelle]
    assert Evaluation.objects.get().statut == Evaluation.Statut.BROUILLON


@pytest.mark.django_db
def test_valider_sans_rien_avoir_saisi_liste_tous_les_criteres():
    prestation, (jure,), criteres = poste()

    with pytest.raises(EvaluationIncompleteError) as erreur:
        evaluations.valider_evaluation(jure, prestation)

    assert len(erreur.value.manquants) == 3


@pytest.mark.django_db
def test_la_validation_fige_l_evaluation_et_les_series_evaluees_et_est_journalisee():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))

    evaluation = evaluations.valider_evaluation(jure, prestation)

    assert evaluation.statut == Evaluation.Statut.VALIDEE and evaluation.validee_le is not None
    assert evaluation.series_evaluees == ["Série 1"]  # D43 : REC-11, « le bon tirage »
    assert "evaluation.validee" in actions()


@pytest.mark.django_db
def test_la_validation_n_est_possible_qu_apres_terminer_la_prestation():
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_AFFICHAGE)
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))

    with pytest.raises(EvaluationInterditeError, match="Terminer"):
        evaluations.valider_evaluation(jure, prestation)


@pytest.mark.django_db
def test_une_evaluation_ne_se_valide_que_par_son_jure():
    prestation, (jure1, jure2), criteres = poste(jures=2)
    evaluations.enregistrer_brouillon(jure1, prestation, notes_completes(criteres))

    with pytest.raises(EvaluationIncompleteError):  # jure2 n'a rien saisi : il ne valide pas l'évaluation de jure1
        evaluations.valider_evaluation(jure2, prestation)

    assert Evaluation.objects.get(jure=jure1).statut == Evaluation.Statut.BROUILLON


@pytest.mark.django_db
def test_une_evaluation_validee_ne_se_modifie_plus_et_ne_se_valide_pas_deux_fois():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)

    with pytest.raises(EvaluationValideeError, match="correction"):
        evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 1})
    with pytest.raises(EvaluationValideeError, match="déjà validée"):
        evaluations.valider_evaluation(jure, prestation)
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("9")


@pytest.mark.django_db
def test_les_contraintes_de_base_une_evaluation_par_jure_et_prestation_note_positive():
    prestation, (jure,), criteres = poste()
    evaluation = evaluations.enregistrer_brouillon(jure, prestation, {str(criteres[0].pk): 5})

    with pytest.raises(IntegrityError), transaction.atomic():
        Evaluation.objects.create(jure=jure, prestation=prestation)
    with pytest.raises(IntegrityError), transaction.atomic():
        Note.objects.filter(pk=evaluation.notes.get().pk).update(valeur=Decimal("-1"))


# --- Suivi et clôture -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_suivi_de_notation_par_jure():
    prestation, (jure1, jure2, jure3), criteres = poste(jures=3)
    evaluations.enregistrer_brouillon(jure1, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure1, prestation)
    evaluations.enregistrer_brouillon(jure2, prestation, {str(criteres[0].pk): 3})

    suivi = {jure.pk: statut for jure, statut in evaluations.statut_notation(prestation)}

    assert suivi == {jure1.pk: "validee", jure2.pk: "brouillon", jure3.pk: "non_commencee"}


@pytest.mark.django_db
def test_l_operateur_cloture_quand_toutes_les_evaluations_sont_validees():
    prestation, (jure1, jure2), criteres = poste(jures=2)
    operateur = creer_utilisateur()
    for jure in (jure1, jure2):
        evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure1, prestation)
    with pytest.raises(EvaluationInterditeError, match="non validées"):
        evaluations.cloturer_prestation(prestation, operateur)

    evaluations.valider_evaluation(jure2, prestation)
    evaluations.cloturer_prestation(prestation, operateur)

    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.CLOTUREE and "prestation.cloturee" in actions()


@pytest.mark.django_db
def test_seul_le_personnel_du_prestataire_cloture():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation)

    with pytest.raises(EvaluationInterditeError, match="prestataire"):
        evaluations.cloturer_prestation(prestation, responsable)


@pytest.mark.django_db
def test_on_ne_cloture_pas_sans_jure_affecte():
    epreuve = creer_epreuve_ouverte(series=1)
    prestation = creer_prestation(epreuve, etat=Prestation.Etat.EN_NOTATION)

    with pytest.raises(EvaluationInterditeError, match="Aucun juré"):
        evaluations.cloturer_prestation(prestation, creer_utilisateur())


# --- Corrections (REC-17) ------------------------------------------------------------------------------


def evaluation_validee():
    prestation, (jure,), criteres = poste()
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation)
    return prestation, jure, criteres, responsable


@pytest.mark.django_db
def test_rec17_la_correction_suit_la_procedure_et_laisse_une_trace():
    prestation, jure, criteres, responsable = evaluation_validee()

    correction = evaluations.demander_correction(jure, prestation, criteres[0], "7,5", "Erreur de saisie : 7,5 et non 9.")
    assert correction.statut == CorrectionNote.Statut.DEMANDEE
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("9")  # rien ne change tant que ce n'est pas approuvé

    evaluations.traiter_correction(correction, responsable, True, "Vérifié avec la fiche papier")

    correction.refresh_from_db()
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("7.50")
    assert (correction.ancienne_valeur, correction.nouvelle_valeur) == (Decimal("9"), Decimal("7.50"))
    assert correction.traitee_par == responsable and correction.traitee_le and correction.motif.startswith("Erreur")
    assert "note.correction_demandee" in actions() and "note.corrigee" in actions()
    traitee = EntreeAudit.objects.get(action="note.corrigee")
    assert traitee.auteur == responsable and traitee.details["ancienne"] == "9.00"


@pytest.mark.django_db
def test_une_correction_refusee_ne_change_pas_la_note_mais_est_conservee():
    prestation, jure, criteres, responsable = evaluation_validee()
    correction = evaluations.demander_correction(jure, prestation, criteres[0], 5, "Je me suis trompé")

    evaluations.traiter_correction(correction, responsable, False, "Non justifié")

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.REFUSEE
    assert Note.objects.get(critere=criteres[0]).valeur == Decimal("9")
    assert "note.correction_refusee" in actions()


@pytest.mark.django_db
def test_l_operateur_n_approuve_pas_une_correction():
    prestation, jure, criteres, _ = evaluation_validee()
    correction = evaluations.demander_correction(jure, prestation, criteres[0], 5, "Motif")

    with pytest.raises(CorrectionInvalideError, match="responsable"):
        evaluations.traiter_correction(correction, creer_utilisateur(), True)
    with pytest.raises(CorrectionInvalideError):  # le responsable d'un AUTRE client non plus
        evaluations.traiter_correction(correction, creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT), True)

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.DEMANDEE


@pytest.mark.django_db
def test_une_correction_exige_un_motif_une_evaluation_validee_et_une_vraie_difference():
    prestation, jure, criteres, _ = evaluation_validee()

    with pytest.raises(CorrectionInvalideError, match="motif"):
        evaluations.demander_correction(jure, prestation, criteres[0], 5, "  ")
    with pytest.raises(CorrectionInvalideError, match="identique"):
        evaluations.demander_correction(jure, prestation, criteres[0], 9, "Motif")
    with pytest.raises(NoteInvalideError):
        evaluations.demander_correction(jure, prestation, criteres[0], 11, "Hors barème")
    autre_prestation, (autre_jure,), autres_criteres = poste()
    evaluations.enregistrer_brouillon(autre_jure, autre_prestation, notes_completes(autres_criteres))
    with pytest.raises(CorrectionInvalideError, match="validée"):
        evaluations.demander_correction(autre_jure, autre_prestation, autres_criteres[0], 5, "Motif")


@pytest.mark.django_db
def test_une_seule_correction_en_attente_par_note_et_pas_de_double_traitement():
    prestation, jure, criteres, responsable = evaluation_validee()
    correction = evaluations.demander_correction(jure, prestation, criteres[0], 5, "Motif")

    with pytest.raises(CorrectionInvalideError, match="en attente"):
        evaluations.demander_correction(jure, prestation, criteres[0], 4, "Autre motif")
    evaluations.traiter_correction(correction, responsable, True)
    with pytest.raises(CorrectionInvalideError, match="déjà été traitée"):
        evaluations.traiter_correction(correction, responsable, True)
