"""Tests des modèles Lot, Serie et QuestionDeSerie (§8.2, RM-20, RM-22)."""
import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.tests.outils import creer_epreuve, creer_organisation
from apps.questions.models import Lot, QuestionDeSerie, Serie
from apps.questions.tests.outils import creer_question


def un_lot(epreuve=None):
    return Lot.objects.create(epreuve=epreuve or creer_epreuve())


def une_serie(lot=None, numero=1):
    return Serie.objects.create(lot=lot or un_lot(), numero=numero)


@pytest.mark.django_db
def test_le_lot_prend_l_organisation_de_son_epreuve():
    epreuve = creer_epreuve()

    assert un_lot(epreuve).organisation_id == epreuve.organisation_id


@pytest.mark.django_db
def test_rm20_le_lot_ne_peut_pas_avoir_une_autre_organisation_que_son_epreuve():
    with pytest.raises(IncoherenceOrganisationError):
        Lot.objects.create(epreuve=creer_epreuve(), organisation=creer_organisation())


@pytest.mark.django_db
def test_une_epreuve_n_a_qu_un_lot():
    epreuve = creer_epreuve()
    un_lot(epreuve)

    with pytest.raises(IntegrityError), transaction.atomic():
        un_lot(epreuve)


@pytest.mark.django_db
def test_une_epreuve_ne_peut_pas_etre_supprimee_si_elle_a_un_lot():
    epreuve = un_lot().epreuve

    with pytest.raises(ProtectedError):
        epreuve.delete()


@pytest.mark.django_db
def test_libelle_et_numero_de_serie_uniques_par_lot():
    lot = un_lot()
    serie = une_serie(lot, 4)

    assert serie.libelle == "Série 4" and serie.organisation_id == lot.organisation_id
    with pytest.raises(IntegrityError), transaction.atomic():
        une_serie(lot, 4)
    une_serie(lot, 5)
    une_serie(numero=4)  # un autre lot : accepté


@pytest.mark.django_db
def test_le_numero_de_serie_est_au_moins_1():
    with pytest.raises(IntegrityError), transaction.atomic():
        une_serie(numero=0)


@pytest.mark.django_db
def test_rang_unique_et_question_unique_par_serie():
    serie = une_serie()
    premiere = creer_question(serie.organisation)
    QuestionDeSerie.objects.create(serie=serie, question=premiere, rang=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionDeSerie.objects.create(serie=serie, question=creer_question(serie.organisation), rang=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionDeSerie.objects.create(serie=serie, question=premiere, rang=2)


@pytest.mark.django_db
def test_le_rang_est_au_moins_1():
    serie = une_serie()

    with pytest.raises(IntegrityError), transaction.atomic():
        QuestionDeSerie.objects.create(serie=serie, question=creer_question(serie.organisation), rang=0)


@pytest.mark.django_db
def test_rm20_une_question_d_un_autre_client_n_entre_pas_dans_la_serie():
    serie = une_serie()

    with pytest.raises(IncoherenceOrganisationError):
        QuestionDeSerie.objects.create(serie=serie, question=creer_question(creer_organisation()), rang=1)


@pytest.mark.django_db
def test_les_questions_d_une_serie_sont_lues_dans_l_ordre_du_rang():
    serie = une_serie()
    q1, q2 = creer_question(serie.organisation), creer_question(serie.organisation)
    QuestionDeSerie.objects.create(serie=serie, question=q2, rang=2)
    QuestionDeSerie.objects.create(serie=serie, question=q1, rang=1)

    assert [qs.question for qs in serie.questions_ordonnees.all()] == [q1, q2]
