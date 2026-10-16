"""Tests du service de tirage (§8.5 ; RM-07, RM-21, RM-28 ; REC-06, REC-07)."""
import uuid
from datetime import date

import pytest

from apps.candidats.exceptions import ConsentementManquantError, ParticipationNonAdmiseError, TirageImpossibleError
from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_consentement, creer_participation
from apps.concours.models import Concours, Epreuve
from apps.prestations import services
from apps.prestations.exceptions import LotEpuiseError, TirageRefuseError
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.mark.django_db
def test_rec06_un_seul_tirage_valide_est_enregistre(epreuve):
    prestation = creer_prestation(epreuve)

    tirage = services.effectuer_tirage(prestation, uuid.uuid4(), terminal="tablette-1")

    assert Tirage.objects.count() == 1
    assert tirage.statut == Tirage.Statut.VALIDE and tirage.rang == 1 and tirage.terminal == "tablette-1"
    assert tirage.serie.lot.epreuve == epreuve
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.TIRE


@pytest.mark.django_db
def test_rec07_double_clic_aucun_double_tirage(epreuve):
    prestation = creer_prestation(epreuve)
    demande = uuid.uuid4()

    premier = services.effectuer_tirage(prestation, demande)
    second = services.effectuer_tirage(prestation, demande)

    assert premier == second and Tirage.objects.count() == 1


@pytest.mark.django_db
def test_un_identifiant_de_demande_ne_sert_pas_pour_une_autre_prestation(epreuve):
    demande = uuid.uuid4()
    services.effectuer_tirage(creer_prestation(epreuve), demande)

    with pytest.raises(TirageImpossibleError, match="autre prestation"):
        services.effectuer_tirage(creer_prestation(epreuve), demande)
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_le_tirage_choisit_avec_le_module_secrets(epreuve, monkeypatch):
    appels = []

    def faux_choice(sequence):
        appels.append(list(sequence))
        return sequence[-1]

    monkeypatch.setattr(services.secrets, "choice", faux_choice)

    tirage = services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())

    assert [s.numero for s in appels[0]] == [1, 2, 3, 4] and tirage.serie.numero == 4


@pytest.mark.django_db
def test_deux_candidats_ne_recoivent_pas_la_meme_serie_par_defaut():
    epreuve = creer_epreuve_ouverte(series=3)

    series = [services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4()).serie for _ in range(3)]

    assert len(set(series)) == 3


@pytest.mark.django_db
def test_lot_epuise_le_tirage_est_bloque_sans_rien_enregistrer():
    epreuve = creer_epreuve_ouverte(series=1)
    services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())
    prestation = creer_prestation(epreuve)

    with pytest.raises(LotEpuiseError, match="compléter"):
        services.effectuer_tirage(prestation, uuid.uuid4())

    assert Tirage.objects.count() == 1
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_ATTENTE


@pytest.mark.django_db
def test_plusieurs_tirages_par_candidat():
    epreuve = creer_epreuve_ouverte(series=5, tirages_par_candidat=2)
    prestation = creer_prestation(epreuve)

    premier = services.effectuer_tirage(prestation, uuid.uuid4())
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_ATTENTE  # il reste un tirage à faire
    second = services.effectuer_tirage(prestation, uuid.uuid4())

    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.TIRE
    assert (premier.rang, second.rang) == (1, 2) and premier.serie != second.serie
    with pytest.raises(TirageRefuseError):
        services.effectuer_tirage(prestation, uuid.uuid4())
    assert Tirage.objects.count() == 2


@pytest.mark.django_db
def test_rm28_un_mineur_sans_consentement_ne_tire_pas(epreuve):
    mineur = creer_candidat(epreuve.organisation, date_naissance=date(2015, 5, 1))
    participation = creer_participation(epreuve.categorie, mineur, statut=Participation.Statut.ADMIS)
    prestation = creer_prestation(epreuve, participation=participation)

    with pytest.raises(ConsentementManquantError):
        services.effectuer_tirage(prestation, uuid.uuid4())

    assert Tirage.objects.count() == 0


@pytest.mark.django_db
def test_rm28_un_mineur_avec_consentement_tire(epreuve):
    mineur = creer_candidat(epreuve.organisation, date_naissance=date(2015, 5, 1))
    participation = creer_participation(epreuve.categorie, mineur, statut=Participation.Statut.ADMIS)
    creer_consentement(participation)

    tirage = services.effectuer_tirage(creer_prestation(epreuve, participation=participation), uuid.uuid4())

    assert tirage.statut == Tirage.Statut.VALIDE


@pytest.mark.django_db
def test_une_participation_non_admise_ne_tire_pas(epreuve):
    participation = creer_participation(
        epreuve.categorie, creer_candidat(epreuve.organisation, date_naissance=date(1990, 1, 1))
    )  # statut « inscrit »

    with pytest.raises(ParticipationNonAdmiseError):
        services.effectuer_tirage(creer_prestation(epreuve, participation=participation), uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Concours.Etat.OUVERT, Concours.Etat.SUSPENDU, Concours.Etat.TERMINE])
def test_d25_pas_de_tirage_si_le_concours_n_est_pas_en_cours(epreuve, etat):
    Concours.objects.filter(pk=epreuve.categorie.concours_id).update(etat=etat)

    with pytest.raises(TirageRefuseError, match="concours"):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Epreuve.Etat.EN_PREPARATION, Epreuve.Etat.TERMINEE])
def test_d25_pas_de_tirage_si_l_epreuve_n_est_pas_ouverte(epreuve, etat):
    Epreuve.objects.filter(pk=epreuve.pk).update(etat=etat)

    with pytest.raises(TirageRefuseError, match="épreuve"):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Prestation.Etat.EN_NOTATION, Prestation.Etat.CLOTUREE, Prestation.Etat.ANNULEE])
def test_pas_de_tirage_si_la_prestation_n_est_pas_en_attente(epreuve, etat):
    prestation = creer_prestation(epreuve, etat=etat)

    with pytest.raises(TirageRefuseError, match="attente"):
        services.effectuer_tirage(prestation, uuid.uuid4())


@pytest.mark.django_db
def test_epreuve_sans_lot_le_tirage_est_bloque():
    epreuve = creer_epreuve_ouverte(series=0)

    with pytest.raises(LotEpuiseError):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())
