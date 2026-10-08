"""Tests des modèles Candidat, Participation et Consentement (§7.3, §16.2, §14.2 ; RM-05, RM-28)."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.candidats.exceptions import ParticipationInvalideError
from apps.candidats.models import Consentement, Participation
from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_consentement,
    creer_organisation,
    creer_participation,
)


# --- Candidat ----------------------------------------------------------------


@pytest.mark.django_db
def test_champs_facultatifs_d_un_candidat_par_minimisation():
    """§7.3 / §16.1 : date de naissance, sexe, ville, structure ne sont pas obligatoires."""
    candidat = creer_candidat()

    assert candidat.date_naissance is None
    assert candidat.sexe == "" and candidat.ville == "" and candidat.structure == ""


@pytest.mark.django_db
def test_nom_complet():
    assert creer_candidat(nom="Diallo", prenom="Awa").nom_complet == "Awa Diallo"


# --- Participation -----------------------------------------------------------


@pytest.mark.django_db
def test_statut_initial_est_inscrit():
    assert creer_participation().statut == Participation.Statut.INSCRIT


@pytest.mark.django_db
def test_la_participation_prend_l_organisation_du_concours():
    categorie = creer_categorie()

    participation = creer_participation(categorie)

    assert participation.organisation_id == categorie.organisation_id


@pytest.mark.django_db
def test_numero_de_candidat_unique_par_concours():
    categorie = creer_categorie()
    creer_participation(categorie, numero_candidat=7)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_participation(categorie, numero_candidat=7)


@pytest.mark.django_db
def test_meme_numero_possible_dans_deux_concours():
    creer_participation(numero_candidat=7)
    creer_participation(numero_candidat=7)

    assert Participation.objects.filter(numero_candidat=7).count() == 2


@pytest.mark.django_db
def test_un_candidat_ne_s_inscrit_qu_une_fois_par_categorie():
    categorie = creer_categorie()
    candidat = creer_candidat(categorie.organisation)
    creer_participation(categorie, candidat)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_participation(categorie, candidat)


@pytest.mark.django_db
def test_un_candidat_peut_s_inscrire_dans_deux_categories_du_meme_concours():
    categorie_a = creer_categorie(nom="Mémorisation")
    categorie_b = creer_categorie(categorie_a.concours, nom="Tajwid")
    candidat = creer_candidat(categorie_a.organisation)

    creer_participation(categorie_a, candidat)
    creer_participation(categorie_b, candidat)

    assert candidat.participations.count() == 2


@pytest.mark.django_db
def test_la_categorie_doit_appartenir_au_concours_de_la_participation():
    categorie = creer_categorie()
    autre_concours = creer_concours(categorie.concours.mission, nom="Autre concours")

    with pytest.raises(ParticipationInvalideError):
        Participation.objects.create(
            candidat=creer_candidat(categorie.organisation),
            concours=autre_concours,
            categorie=categorie,
            numero_candidat=1,
        )


@pytest.mark.django_db
def test_rm20_un_candidat_d_un_autre_client_est_refuse():
    categorie = creer_categorie()
    candidat_d_ailleurs = creer_candidat(creer_organisation())

    with pytest.raises(IncoherenceOrganisationError):
        Participation.objects.create(
            candidat=candidat_d_ailleurs,
            concours=categorie.concours,
            categorie=categorie,
            numero_candidat=1,
        )


@pytest.mark.django_db
def test_une_organisation_ne_peut_pas_etre_supprimee_si_elle_a_des_candidats():
    candidat = creer_candidat()

    with pytest.raises(ProtectedError):
        candidat.organisation.delete()


# --- Consentement ------------------------------------------------------------


@pytest.mark.django_db
def test_les_trois_consentements_sont_distincts_et_jamais_precoches():
    """§16.2 : trois consentements non précochés ; le seul fourni par le test est celui n° 1."""
    consentement = Consentement.objects.create(
        participation=creer_participation(),
        representant_nom="Parent",
        representant_lien="Père",
        version_formulaire="1.0",
        date_signature=date(2027, 1, 10),
    )

    assert consentement.consentement_participation is False
    assert consentement.consentement_publication_nom is False
    assert consentement.consentement_image_voix is False
    assert consentement.statut == Consentement.Statut.VALIDE


@pytest.mark.django_db
def test_le_consentement_prend_l_organisation_de_la_participation():
    participation = creer_participation()

    assert creer_consentement(participation).organisation_id == participation.organisation_id


@pytest.mark.django_db
def test_un_seul_consentement_valide_par_participation():
    participation = creer_participation()
    creer_consentement(participation)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_consentement(participation, version_formulaire="1.1")


@pytest.mark.django_db
def test_un_nouveau_formulaire_est_possible_apres_le_retrait_du_precedent():
    """Le retrait prend effet pour l'avenir (§16.2) : l'ancien formulaire est conservé."""
    participation = creer_participation()
    creer_consentement(
        participation, statut=Consentement.Statut.RETIRE, date_retrait=date(2027, 1, 15)
    )

    creer_consentement(participation, version_formulaire="1.1")

    assert participation.consentements.count() == 2


@pytest.mark.django_db
def test_un_consentement_retire_a_une_date_de_retrait_et_inversement():
    participation = creer_participation()

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_consentement(participation, statut=Consentement.Statut.RETIRE)
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_consentement(participation, date_retrait=date(2027, 1, 15))
