"""Tests du contrôle de suffisance du lot (§8.2, RM-24) et de l'ouverture d'une épreuve.

``series_necessaires`` est la règle à écrire par vous ; le reste est testé à travers elle.
"""
import pytest

from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_participation
from apps.concours.models import Epreuve
from apps.prestations import services
from apps.prestations.exceptions import OuvertureEpreuveRefuseeError
from apps.prestations.tests.outils import ajouter_series, creer_epreuve_ouverte
from apps.questions.models import QuestionDeSerie, Serie
from apps.questions.tests.outils import creer_question


@pytest.mark.django_db
@pytest.mark.parametrize(
    "n, t, reattribution, attendu",
    [
        (10, 1, False, 10),  # exclusion définitive : S >= N x T
        (10, 2, False, 20),
        (1, 1, False, 1),
        (10, 1, True, 1),  # réattribution : S >= T
        (10, 3, True, 3),
        (0, 2, True, 2),
    ],
)
def test_rm24_series_necessaires(n, t, reattribution, attendu):
    epreuve = creer_epreuve_ouverte(series=0, tirages_par_candidat=t, reutilisation_autre_candidat=reattribution)

    assert services.series_necessaires(epreuve, n) == attendu


@pytest.mark.django_db
def test_rm24_sans_candidat_et_sans_reattribution_aucune_serie_n_est_necessaire():
    assert services.series_necessaires(creer_epreuve_ouverte(series=0), 0) == 0


def inscrits_admis(epreuve, n):
    for _ in range(n):
        creer_participation(
            epreuve.categorie, creer_candidat(epreuve.organisation), statut=Participation.Statut.ADMIS
        )


def en_preparation(series, admis, **champs):
    epreuve = creer_epreuve_ouverte(series=series, etat=Epreuve.Etat.EN_PREPARATION, **champs)
    inscrits_admis(epreuve, admis)
    return epreuve


@pytest.mark.django_db
def test_rm24_series_manquantes_compte_les_admis_seulement():
    epreuve = en_preparation(series=3, admis=5)
    creer_participation(epreuve.categorie)  # inscrit, non admis : ne compte pas

    assert services.series_manquantes(epreuve) == 2  # 5 admis x 1 tirage - 3 séries


@pytest.mark.django_db
def test_rm24_ouverture_bloquee_lot_insuffisant_avec_le_nombre_de_series_manquantes():
    epreuve = en_preparation(series=3, admis=5)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="2 série"):
        services.ouvrir_epreuve(epreuve)

    epreuve.refresh_from_db()
    assert epreuve.etat == Epreuve.Etat.EN_PREPARATION


@pytest.mark.django_db
def test_rm24_ouverture_possible_quand_le_lot_suffit():
    epreuve = en_preparation(series=5, admis=5)

    services.ouvrir_epreuve(epreuve)

    epreuve.refresh_from_db()
    assert epreuve.etat == Epreuve.Etat.OUVERTE


@pytest.mark.django_db
def test_rm24_la_reattribution_reduit_le_besoin():
    epreuve = en_preparation(series=1, admis=5, reutilisation_autre_candidat=True)

    services.ouvrir_epreuve(epreuve)

    epreuve.refresh_from_db()
    assert epreuve.etat == Epreuve.Etat.OUVERTE


@pytest.mark.django_db
def test_rm22_ouverture_bloquee_si_une_serie_est_incomplete():
    epreuve = en_preparation(series=5, admis=1)
    bancale = Serie.objects.create(lot=epreuve.lot, numero=99)
    for rang in (1, 2):  # P = 1 dans cette épreuve : deux questions, c'est une de trop
        QuestionDeSerie.objects.create(serie=bancale, question=creer_question(epreuve.organisation), rang=rang)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="99"):
        services.ouvrir_epreuve(epreuve)


@pytest.mark.django_db
def test_ouverture_bloquee_sans_lot_ou_sans_serie():
    epreuve = creer_epreuve_ouverte(series=0, etat=Epreuve.Etat.EN_PREPARATION)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="aucune série"):
        services.ouvrir_epreuve(epreuve)


@pytest.mark.django_db
def test_une_epreuve_deja_ouverte_ne_s_ouvre_pas_deux_fois():
    epreuve = creer_epreuve_ouverte(series=2)

    with pytest.raises(OuvertureEpreuveRefuseeError, match="préparation"):
        services.ouvrir_epreuve(epreuve)
