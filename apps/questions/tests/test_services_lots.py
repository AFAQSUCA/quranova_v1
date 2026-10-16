"""Tests de la composition des lots et séries (§8.2 ; RM-20, RM-22, RM-23)."""
import pytest

from apps.commun.tests.outils import (
    creer_categorie,
    creer_concours,
    creer_epreuve,
    creer_organisation,
    creer_version_validee,
)
from apps.questions import services
from apps.questions.exceptions import SerieInvalideError
from apps.questions.models import Lot, QuestionDeSerie, Serie
from apps.questions.tests.outils import creer_question


@pytest.fixture
def epreuve(db):
    """Une épreuve avec P = 3, dans un concours rattaché à une version du corpus."""
    concours = creer_concours(version_corpus=creer_version_validee())
    return creer_epreuve(creer_categorie(concours), questions_par_serie=3)


def questions(epreuve, n, **champs):
    return [creer_question(epreuve.organisation, **champs) for _ in range(n)]


@pytest.mark.django_db
def test_obtenir_lot_cree_le_lot_une_seule_fois(epreuve):
    premier = services.obtenir_lot(epreuve)
    second = services.obtenir_lot(epreuve)

    assert premier == second and Lot.objects.count() == 1


@pytest.mark.django_db
def test_composer_une_serie_numerote_et_ordonne(epreuve):
    lot = services.obtenir_lot(epreuve)
    qs = questions(epreuve, 6)

    s1 = services.composer_serie(lot, qs[:3])
    s2 = services.composer_serie(lot, qs[3:])

    assert (s1.numero, s2.numero) == (1, 2)
    assert [x.question for x in s1.questions_ordonnees.all()] == qs[:3]
    assert [x.rang for x in s2.questions_ordonnees.all()] == [1, 2, 3]


@pytest.mark.django_db
@pytest.mark.parametrize("n", [0, 2, 4])
def test_rm22_une_serie_contient_exactement_p_questions(epreuve, n):
    lot = services.obtenir_lot(epreuve)

    with pytest.raises(SerieInvalideError, match="3"):
        services.composer_serie(lot, questions(epreuve, n))

    assert Serie.objects.count() == 0 and QuestionDeSerie.objects.count() == 0


@pytest.mark.django_db
def test_une_question_n_est_pas_repetee_dans_une_serie(epreuve):
    lot = services.obtenir_lot(epreuve)
    a, b = questions(epreuve, 2)

    with pytest.raises(SerieInvalideError, match="plusieurs fois"):
        services.composer_serie(lot, [a, b, a])

    assert Serie.objects.count() == 0


@pytest.mark.django_db
def test_rm20_une_question_d_un_autre_client_est_refusee(epreuve):
    lot = services.obtenir_lot(epreuve)
    qs = questions(epreuve, 2) + [creer_question(creer_organisation())]

    with pytest.raises(SerieInvalideError, match="client"):
        services.composer_serie(lot, qs)

    assert Serie.objects.count() == 0


@pytest.mark.django_db
def test_rm23_un_passage_d_une_autre_version_du_corpus_est_refuse(epreuve):
    lot = services.obtenir_lot(epreuve)
    autre_version = creer_version_validee()
    qs = questions(epreuve, 2) + [creer_question(epreuve.organisation, version=autre_version)]

    with pytest.raises(SerieInvalideError, match="version"):
        services.composer_serie(lot, qs)

    assert Serie.objects.count() == 0


@pytest.mark.django_db
def test_rm23_un_passage_de_la_version_du_concours_est_accepte(epreuve):
    lot = services.obtenir_lot(epreuve)
    version = epreuve.categorie.concours.version_corpus
    qs = questions(epreuve, 2) + [creer_question(epreuve.organisation, version=version)]

    assert services.composer_serie(lot, qs).questions_ordonnees.count() == 3


@pytest.mark.django_db
def test_rm23_un_passage_est_refuse_tant_que_le_concours_n_a_pas_de_version():
    epreuve = creer_epreuve(creer_categorie(creer_concours()), questions_par_serie=1)
    lot = services.obtenir_lot(epreuve)
    passage = creer_question(epreuve.organisation, version=creer_version_validee())

    with pytest.raises(SerieInvalideError, match="version"):
        services.composer_serie(lot, [passage])


@pytest.mark.django_db
def test_series_incompletes_signale_les_series_hors_p(epreuve):
    lot = services.obtenir_lot(epreuve)
    bonne = services.composer_serie(lot, questions(epreuve, 3))
    # Une série construite en contournant le service (import, admin) : le contrôle la rattrape.
    bancale = Serie.objects.create(lot=lot, numero=2)
    QuestionDeSerie.objects.create(serie=bancale, question=creer_question(epreuve.organisation), rang=1)
    vide = Serie.objects.create(lot=lot, numero=3)

    assert services.series_incompletes(lot) == [bancale, vide]
    assert bonne not in services.series_incompletes(lot)
