"""Tests des modèles Prestation et Tirage (§8.3, §14.1, §14.2 ; RM-20, RM-25)."""
import uuid

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_organisation,
    creer_participation,
    creer_session,
    creer_utilisateur,
)
from apps.prestations.exceptions import PrestationInvalideError, TirageInvalideError
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import ajouter_series, creer_epreuve_ouverte, creer_prestation, creer_tirage


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=3)


# --- Prestation --------------------------------------------------------------


@pytest.mark.django_db
def test_une_prestation_est_en_attente_par_defaut_et_prend_l_organisation(epreuve):
    prestation = creer_prestation(epreuve)

    assert prestation.etat == Prestation.Etat.EN_ATTENTE
    assert prestation.organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_une_prestation_par_participation_et_par_epreuve(epreuve):
    prestation = creer_prestation(epreuve)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_prestation(epreuve, participation=prestation.participation)


@pytest.mark.django_db
def test_le_rang_de_passage_est_unique_par_session_et_par_epreuve(epreuve):
    premiere = creer_prestation(epreuve, rang_passage=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_prestation(epreuve, session=premiere.session, rang_passage=1)


@pytest.mark.django_db
def test_l_epreuve_doit_etre_celle_de_la_categorie_de_la_participation(epreuve):
    autre_categorie = creer_categorie(epreuve.categorie.concours)
    participation = creer_participation(autre_categorie)

    with pytest.raises(PrestationInvalideError, match="catégorie"):
        creer_prestation(epreuve, participation=participation)


@pytest.mark.django_db
def test_la_session_doit_etre_celle_du_concours(epreuve):
    autre_concours_du_meme_client = creer_concours(epreuve.categorie.concours.mission)

    with pytest.raises(PrestationInvalideError, match="session"):
        creer_prestation(epreuve, session=creer_session(autre_concours_du_meme_client))


@pytest.mark.django_db
def test_rm20_une_participation_d_un_autre_client_est_refusee(epreuve):
    participation = creer_participation()

    with pytest.raises(IncoherenceOrganisationError):
        creer_prestation(epreuve, participation=participation)


# --- Tirage ------------------------------------------------------------------


@pytest.mark.django_db
def test_un_tirage_valide_par_defaut(epreuve):
    prestation = creer_prestation(epreuve)
    serie = epreuve.lot.series.first()

    tirage = creer_tirage(prestation, serie)

    assert tirage.statut == Tirage.Statut.VALIDE
    assert tirage.diapositive_affichee is False
    assert tirage.organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_la_serie_doit_appartenir_au_lot_de_l_epreuve(epreuve):
    autre_epreuve = creer_epreuve_ouverte(series=1)
    prestation = creer_prestation(epreuve)

    with pytest.raises(TirageInvalideError, match="lot"):
        creer_tirage(prestation, autre_epreuve.lot.series.first())


@pytest.mark.django_db
def test_l_identifiant_de_demande_est_unique(epreuve):
    serie1, serie2, _ = epreuve.lot.series.all()
    identifiant = uuid.uuid4()
    creer_tirage(creer_prestation(epreuve), serie1, id_demande=identifiant)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(creer_prestation(epreuve), serie2, id_demande=identifiant)


@pytest.mark.django_db
def test_rm21_jamais_deux_fois_la_meme_serie_pour_un_candidat(epreuve):
    prestation = creer_prestation(epreuve)
    serie = epreuve.lot.series.first()
    creer_tirage(prestation, serie, rang=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(prestation, serie, rang=2)


@pytest.mark.django_db
def test_un_seul_tirage_valide_par_rang(epreuve):
    prestation = creer_prestation(epreuve)
    serie1, serie2, _ = epreuve.lot.series.all()
    creer_tirage(prestation, serie1, rang=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(prestation, serie2, rang=1)


@pytest.mark.django_db
def test_un_tirage_annule_libere_le_rang_et_garde_la_trace(epreuve):
    prestation = creer_prestation(epreuve)
    serie1, serie2, _ = epreuve.lot.series.all()
    operateur = creer_utilisateur()
    creer_tirage(
        prestation, serie1, rang=1, statut=Tirage.Statut.ANNULE,
        motif_annulation="Erreur d'appel", annule_par=operateur, annule_le=timezone.now(),
    )

    creer_tirage(prestation, serie2, rang=1)

    assert prestation.tirages.count() == 2


@pytest.mark.django_db
def test_rm25_l_annulation_exige_motif_auteur_et_date(epreuve):
    prestation = creer_prestation(epreuve)
    serie = epreuve.lot.series.first()

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(prestation, serie, statut=Tirage.Statut.ANNULE)
    with pytest.raises(IntegrityError), transaction.atomic():  # motif vide
        creer_tirage(
            prestation, serie, statut=Tirage.Statut.ANNULE,
            annule_par=creer_utilisateur(), annule_le=timezone.now(),
        )


@pytest.mark.django_db
def test_un_tirage_valide_ne_porte_pas_de_motif_d_annulation(epreuve):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_tirage(creer_prestation(epreuve), epreuve.lot.series.first(), motif_annulation="x")


@pytest.mark.django_db
def test_un_tirage_n_est_jamais_supprime(epreuve):
    tirage = creer_tirage(creer_prestation(epreuve), epreuve.lot.series.first())

    with pytest.raises(TirageInvalideError, match="annulé"):
        tirage.delete()
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_un_tirage_enregistre_ne_peut_pas_etre_remplace_en_silence(epreuve):
    tirage = creer_tirage(creer_prestation(epreuve), epreuve.lot.series.first())
    tirage.serie = epreuve.lot.series.last()

    with pytest.raises(TirageInvalideError, match="remplacé"):
        tirage.save()


@pytest.mark.django_db
def test_une_serie_tiree_ne_peut_pas_etre_supprimee(epreuve):
    serie = epreuve.lot.series.first()
    creer_tirage(creer_prestation(epreuve), serie)

    with pytest.raises(ProtectedError):
        serie.delete()
