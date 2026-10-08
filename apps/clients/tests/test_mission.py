"""Tests du modèle Mission (§14.1, §22)."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.clients.models import Mission
from apps.commun.tests.outils import creer_mission


@pytest.mark.django_db
def test_statut_initial_est_en_preparation():
    assert creer_mission().statut == Mission.Statut.EN_PREPARATION


@pytest.mark.django_db
def test_une_mission_d_un_seul_jour_est_acceptee():
    mission = creer_mission(date_debut=date(2027, 1, 20), date_fin=date(2027, 1, 20))

    assert mission.date_debut == mission.date_fin


@pytest.mark.django_db
def test_la_date_de_fin_ne_peut_pas_preceder_la_date_de_debut():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_mission(date_debut=date(2027, 1, 21), date_fin=date(2027, 1, 20))
