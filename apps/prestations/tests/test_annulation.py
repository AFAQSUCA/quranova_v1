"""Tests de l'annulation d'un tirage (RM-25, §8.5, D26)."""
import uuid

import pytest

from apps.commun.tests.outils import creer_utilisateur
from apps.prestations import services
from apps.prestations.exceptions import AnnulationInvalideError, LotEpuiseError
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.utilisateurs.models import Utilisateur


@pytest.fixture
def tirage(db):
    epreuve = creer_epreuve_ouverte(series=1)
    return services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())


@pytest.mark.django_db
def test_rm25_le_tirage_annule_garde_sa_trace(tirage):
    operateur = creer_utilisateur()

    annule = services.annuler_tirage(tirage, operateur, "  Erreur d'appel du candidat  ")

    assert Tirage.objects.count() == 1
    assert annule.statut == Tirage.Statut.ANNULE
    assert annule.motif_annulation == "Erreur d'appel du candidat"
    assert annule.annule_par == operateur and annule.annule_le is not None
    assert annule.serie == tirage.serie


@pytest.mark.django_db
def test_la_prestation_redevient_en_attente(tirage):
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident")

    tirage.prestation.refresh_from_db()
    assert tirage.prestation.etat == Prestation.Etat.EN_ATTENTE


@pytest.mark.django_db
def test_rm25_serie_reintegree_si_aucune_diapositive_affichee(tirage):
    """Lot d'une seule série : après annulation, le nouveau tirage peut la recevoir de nouveau."""
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident technique")

    nouveau = services.effectuer_tirage(tirage.prestation, uuid.uuid4())

    assert nouveau.serie == tirage.serie and nouveau.id != tirage.id
    assert Tirage.objects.count() == 2


@pytest.mark.django_db
def test_rm25_serie_exclue_si_une_diapositive_a_ete_affichee(tirage):
    Tirage.objects.filter(pk=tirage.pk).update(diapositive_affichee=True)
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident pendant l'affichage")

    with pytest.raises(LotEpuiseError):
        services.effectuer_tirage(tirage.prestation, uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("motif", ["", "   ", None])
def test_le_motif_est_obligatoire(tirage, motif):
    with pytest.raises(AnnulationInvalideError, match="motif"):
        services.annuler_tirage(tirage, creer_utilisateur(), motif)

    tirage.refresh_from_db()
    assert tirage.statut == Tirage.Statut.VALIDE


@pytest.mark.django_db
def test_un_responsable_client_ne_peut_pas_annuler(tirage):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)

    with pytest.raises(AnnulationInvalideError, match="prestataire"):
        services.annuler_tirage(tirage, responsable, "Je n'aime pas ma série")


@pytest.mark.django_db
def test_on_n_annule_pas_deux_fois(tirage):
    operateur = creer_utilisateur()
    services.annuler_tirage(tirage, operateur, "Incident")

    with pytest.raises(AnnulationInvalideError, match="déjà annulé"):
        services.annuler_tirage(tirage, operateur, "Encore")


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Prestation.Etat.EN_NOTATION, Prestation.Etat.CLOTUREE])
def test_pas_d_annulation_une_fois_en_notation(tirage, etat):
    Prestation.objects.filter(pk=tirage.prestation_id).update(etat=etat)

    with pytest.raises(AnnulationInvalideError, match="notation"):
        services.annuler_tirage(tirage, creer_utilisateur(), "Trop tard")


@pytest.mark.django_db
def test_la_demande_d_un_tirage_annule_n_est_pas_rejouable(tirage):
    services.annuler_tirage(tirage, creer_utilisateur(), "Incident")

    with pytest.raises(Exception, match="annulé"):
        services.effectuer_tirage(tirage.prestation, tirage.id_demande)
