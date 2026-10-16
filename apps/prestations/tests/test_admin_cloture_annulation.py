"""Clôture d'une prestation (§8.3 étape 6) et annulation d'un tirage (RM-25) depuis l'administration : le personnel en a besoin le jour J."""
import pytest
from django.urls import reverse

from apps.commun.tests.outils import creer_utilisateur
from apps.jury import evaluations
from apps.jury.tests.test_evaluations import notes_completes, poste
from apps.prestations.models import Prestation, Tirage
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def operateur_pour(prestation):
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=prestation.epreuve.categorie.concours.mission, utilisateur=operateur)
    return operateur


def liste_prestations():
    return reverse("admin:prestations_prestation_changelist")


def liste_tirages():
    return reverse("admin:prestations_tirage_changelist")


@pytest.mark.django_db
def test_l_operateur_cloture_une_prestation_dont_toutes_les_evaluations_sont_validees(client):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_NOTATION)
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)
    client.force_login(operateur_pour(prestation))

    reponse = client.post(liste_prestations(), {"action": "cloturer", "_selected_action": [str(prestation.pk)]})

    assert reponse.status_code == 302
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.CLOTUREE


@pytest.mark.django_db
def test_la_cloture_est_refusee_tant_qu_un_jure_n_a_pas_valide_et_l_etat_ne_change_pas(client):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_NOTATION)
    client.force_login(operateur_pour(prestation))

    reponse = client.post(liste_prestations(), {"action": "cloturer", "_selected_action": [str(prestation.pk)]}, follow=True)

    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_NOTATION
    assert "non validées" in reponse.content.decode()


@pytest.mark.django_db
def test_le_responsable_client_ne_cloture_pas_meme_en_forcant_la_requete(client):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_NOTATION)
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres))
    evaluations.valider_evaluation(jure, prestation)
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation, is_staff=True))

    client.post(liste_prestations(), {"action": "cloturer", "_selected_action": [str(prestation.pk)]})

    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_NOTATION


@pytest.mark.django_db
def test_l_annulation_d_un_tirage_demande_un_motif_puis_remet_la_prestation_en_attente(client):
    prestation, _, _ = poste(etat=Prestation.Etat.TIRE)
    tirage = prestation.tirages.get()
    client.force_login(operateur_pour(prestation))

    formulaire = client.post(liste_tirages(), {"action": "annuler_le_tirage", "_selected_action": [str(tirage.pk)]})
    assert formulaire.status_code == 200 and "motif" in formulaire.content.decode().lower()

    sans_motif = client.post(liste_tirages(), {"action": "annuler_le_tirage", "_selected_action": [str(tirage.pk)], "appliquer": "1", "motif": "  "})
    assert sans_motif.status_code == 200
    tirage.refresh_from_db()
    assert tirage.statut == Tirage.Statut.VALIDE  # rien n'a changé

    reponse = client.post(liste_tirages(), {"action": "annuler_le_tirage", "_selected_action": [str(tirage.pk)], "appliquer": "1",
                                            "motif": "Mauvais candidat appelé sur la tablette."})
    assert reponse.status_code == 302
    tirage.refresh_from_db(); prestation.refresh_from_db()
    assert tirage.statut == Tirage.Statut.ANNULE and "Mauvais candidat" in tirage.motif_annulation
    assert prestation.etat == Prestation.Etat.EN_ATTENTE


@pytest.mark.django_db
def test_le_responsable_client_n_annule_pas_un_tirage_meme_en_forcant_la_requete(client):
    prestation, _, _ = poste(etat=Prestation.Etat.TIRE)
    tirage = prestation.tirages.get()
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation, is_staff=True))

    client.post(liste_tirages(), {"action": "annuler_le_tirage", "_selected_action": [str(tirage.pk)], "appliquer": "1", "motif": "Pirate"})

    tirage.refresh_from_db()
    assert tirage.statut == Tirage.Statut.VALIDE
