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
