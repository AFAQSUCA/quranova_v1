"""Admission en masse des candidats inscrits (500 candidats : pas un par un)."""
import pytest
from django.urls import reverse

from apps.audit.models import EntreeAudit
from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_candidat, creer_categorie, creer_concours, creer_participation, creer_utilisateur
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def salle(db):
    concours = creer_concours()
    categorie = creer_categorie(concours)
    participations = [creer_participation(categorie, creer_candidat(concours.organisation)) for _ in range(3)]
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=concours.mission, utilisateur=operateur)
    return concours, participations, operateur


def poster(client, participations):
    return client.post(reverse("admin:candidats_participation_changelist"),
                       {"action": "admettre", "_selected_action": [str(p.pk) for p in participations]})


def test_l_operateur_admet_les_candidats_inscrits_d_un_coup(client, salle):
    _, participations, operateur = salle
    client.force_login(operateur)

    reponse = poster(client, participations)

    assert reponse.status_code == 302
    assert Participation.objects.filter(statut=Participation.Statut.ADMIS).count() == 3
    assert EntreeAudit.objects.filter(action="participation.admise").count() == 3


def test_un_candidat_retire_n_est_pas_admis_par_erreur(client, salle):
    _, participations, operateur = salle
    Participation.objects.filter(pk=participations[0].pk).update(statut=Participation.Statut.RETIRE)
    client.force_login(operateur)

    poster(client, participations)

    assert Participation.objects.get(pk=participations[0].pk).statut == Participation.Statut.RETIRE
    assert Participation.objects.filter(statut=Participation.Statut.ADMIS).count() == 2


def test_le_responsable_client_n_admet_pas_meme_en_forcant_la_requete(client, salle):
    concours, participations, _ = salle
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation, is_staff=True))

    poster(client, participations)

    assert not Participation.objects.filter(statut=Participation.Statut.ADMIS).exists()
