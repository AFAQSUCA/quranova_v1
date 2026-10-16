"""Tests de la sélection des séries admissibles (RM-21, RM-25) — règle à écrire par vous.

Les trois paramètres de RM-21 sont portés par l'épreuve :
- RM-21.a ``reutilisation_autre_candidat`` (défaut : non) ;
- RM-21.b ``reutilisation_meme_candidat_autre_epreuve`` (défaut : non) ;
- RM-21.c ``exclusion_definitive`` (déduite : oui si a et b sont « non »).
Quelle que soit la configuration, un candidat ne reçoit jamais deux fois la même série dans une épreuve.
"""
import pytest
from django.utils import timezone

from apps.commun.tests.outils import creer_utilisateur
from apps.prestations import services
from apps.prestations.models import Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage


def annule(prestation, serie, *, affichee):
    return creer_tirage(
        prestation, serie, statut=Tirage.Statut.ANNULE, motif_annulation="Incident",
        annule_par=creer_utilisateur(), annule_le=timezone.now(), diapositive_affichee=affichee,
    )


@pytest.fixture
def epreuve(db):
    return creer_epreuve_ouverte(series=4)


@pytest.mark.django_db
def test_rm21_toutes_les_series_sont_admissibles_au_depart_dans_l_ordre(epreuve):
    admissibles = services.series_admissibles(creer_prestation(epreuve))

    assert [s.numero for s in admissibles] == [1, 2, 3, 4]


@pytest.mark.django_db
def test_rm21_serie_exclue_apres_tirage_pour_les_autres_candidats_par_defaut(epreuve):
    premiere = epreuve.lot.series.get(numero=2)
    creer_tirage(creer_prestation(epreuve), premiere)

    admissibles = services.series_admissibles(creer_prestation(epreuve))

    assert [s.numero for s in admissibles] == [1, 3, 4]


@pytest.mark.django_db
def test_rm21a_reattribution_a_un_autre_candidat_si_autorisee():
    epreuve = creer_epreuve_ouverte(series=4, reutilisation_autre_candidat=True)
    creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get(numero=2))

    admissibles = services.series_admissibles(creer_prestation(epreuve))

    assert [s.numero for s in admissibles] == [1, 2, 3, 4]


@pytest.mark.django_db
@pytest.mark.parametrize("reattribution", [False, True])
def test_rm21_jamais_deux_fois_la_meme_serie_pour_un_candidat(reattribution):
    epreuve = creer_epreuve_ouverte(series=3, reutilisation_autre_candidat=reattribution, tirages_par_candidat=2)
    prestation = creer_prestation(epreuve)
    creer_tirage(prestation, epreuve.lot.series.get(numero=1), rang=1)

    admissibles = services.series_admissibles(prestation)

    assert 1 not in [s.numero for s in admissibles]


@pytest.mark.django_db
def test_rm21b_sans_effet_tant_qu_un_lot_n_est_pas_partage():
    """D24 : un lot par épreuve ; le paramètre RM-21.b ne change donc rien pour l'instant."""
    standard = creer_epreuve_ouverte(series=3)
    permissive = creer_epreuve_ouverte(series=3, reutilisation_meme_candidat_autre_epreuve=True)
    for epreuve in (standard, permissive):
        creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get(numero=1))

    resultats = [
        [s.numero for s in services.series_admissibles(creer_prestation(e))] for e in (standard, permissive)
    ]

    assert resultats[0] == resultats[1] == [2, 3]


@pytest.mark.django_db
def test_rm25_serie_reintegree_si_le_tirage_annule_n_a_rien_affiche(epreuve):
    prestation = creer_prestation(epreuve)
    annule(prestation, epreuve.lot.series.get(numero=1), affichee=False)

    for candidat in (prestation, creer_prestation(epreuve)):
        assert 1 in [s.numero for s in services.series_admissibles(candidat)]


@pytest.mark.django_db
def test_rm25_serie_exclue_si_le_tirage_annule_a_deja_affiche_une_diapositive(epreuve):
    prestation = creer_prestation(epreuve)
    annule(prestation, epreuve.lot.series.get(numero=1), affichee=True)

    for candidat in (prestation, creer_prestation(epreuve)):
        assert 1 not in [s.numero for s in services.series_admissibles(candidat)]


@pytest.mark.django_db
def test_rm25_avec_reattribution_la_serie_affichee_puis_annulee_reste_exclue_pour_le_meme_candidat():
    """D27 : le candidat a vu la série ; il ne la reçoit pas de nouveau, les autres le peuvent."""
    epreuve = creer_epreuve_ouverte(series=3, reutilisation_autre_candidat=True)
    prestation = creer_prestation(epreuve)
    annule(prestation, epreuve.lot.series.get(numero=1), affichee=True)

    assert 1 not in [s.numero for s in services.series_admissibles(prestation)]
    assert 1 in [s.numero for s in services.series_admissibles(creer_prestation(epreuve))]


@pytest.mark.django_db
def test_rm21_lot_epuise_liste_vide():
    epreuve = creer_epreuve_ouverte(series=1)
    creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get())

    assert services.series_admissibles(creer_prestation(epreuve)) == []


@pytest.mark.django_db
def test_les_tirages_d_une_autre_epreuve_n_ont_aucun_effet(epreuve):
    autre = creer_epreuve_ouverte(series=2)
    creer_tirage(creer_prestation(autre), autre.lot.series.get(numero=1))

    assert len(services.series_admissibles(creer_prestation(epreuve))) == 4
