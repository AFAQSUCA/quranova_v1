"""Traitement des demandes de correction de note par le responsable du client, depuis l'administration (REC-17, RM-18)."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.commun.tests.outils import creer_utilisateur
from apps.jury import evaluations
from apps.jury.models import CorrectionNote, Note
from apps.jury.tests.test_evaluations import notes_completes, poste
from apps.prestations.models import Prestation
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def demande(db):
    prestation, (jure,), criteres = poste(etat=Prestation.Etat.EN_NOTATION)
    evaluations.enregistrer_brouillon(jure, prestation, notes_completes(criteres, (9, 8, 4)))
    evaluations.valider_evaluation(jure, prestation)
    correction = evaluations.demander_correction(jure, prestation, criteres[0], 7, "Erreur de saisie : je voulais écrire 7.")
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=prestation.organisation, is_staff=True)
    return correction, responsable, prestation


def liste():
    return reverse("admin:jury_correctionnote_changelist")


def poster(client, correction, action):
    return client.post(liste(), {"action": action, "_selected_action": [str(correction.pk)]})


def test_le_responsable_voit_la_demande_avec_l_ancienne_et_la_nouvelle_valeur_et_le_motif(client, demande):
    correction, responsable, _ = demande
    client.force_login(responsable)

    page = client.get(liste()).content.decode()

    assert "Erreur de saisie" in page and "9" in page and "7" in page


def test_le_responsable_approuve_la_correction_la_note_change_et_la_trace_reste(client, demande):
    correction, responsable, prestation = demande
    client.force_login(responsable)

    poster(client, correction, "approuver")

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.APPROUVEE and correction.traitee_par == responsable
    assert Note.objects.get(evaluation=correction.evaluation, critere=correction.critere).valeur == Decimal("7.00")


def test_le_responsable_refuse_la_correction_la_note_ne_change_pas(client, demande):
    correction, responsable, _ = demande
    client.force_login(responsable)

    poster(client, correction, "refuser")

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.REFUSEE
    assert Note.objects.get(evaluation=correction.evaluation, critere=correction.critere).valeur == Decimal("9.00")


@pytest.mark.parametrize("action", ["approuver", "refuser"])
def test_l_operateur_ne_traite_pas_une_correction_meme_en_forcant_la_requete(client, demande, action):
    correction, _, prestation = demande
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=prestation.epreuve.categorie.concours.mission, utilisateur=operateur)
    client.force_login(operateur)

    assert client.get(liste()).status_code == 200  # il peut voir où en sont les demandes
    poster(client, correction, action)

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.DEMANDEE


def test_le_responsable_d_un_autre_client_ne_voit_ni_ne_traite_la_demande(client, demande):
    correction, _, _ = demande
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True))

    assert "Erreur de saisie" not in client.get(liste()).content.decode()
    poster(client, correction, "approuver")

    correction.refresh_from_db()
    assert correction.statut == CorrectionNote.Statut.DEMANDEE


def test_personne_ne_modifie_ni_ne_supprime_une_demande_depuis_l_administration(client, demande):
    correction, responsable, _ = demande
    client.force_login(responsable)

    assert client.get(reverse("admin:jury_correctionnote_add")).status_code == 403
    assert client.post(reverse("admin:jury_correctionnote_delete", args=[correction.pk]), {"post": "yes"}).status_code == 403
