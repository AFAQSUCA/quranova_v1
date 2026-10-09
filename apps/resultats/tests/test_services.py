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
