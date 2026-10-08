"""Le classement dans l'administration : calcul visible, validation réservée au responsable client (RM-18)."""
import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.commun.tests.outils import creer_utilisateur
from apps.resultats.models import Classement
from apps.resultats.tests.outils import construire_exemple
from apps.resultats.tests.test_validation import exemple_complet
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def messages_de(reponse):
    return " | ".join(str(m) for m in get_messages(reponse.wsgi_request))


def lancer(client, epreuve, action):
    return client.post(reverse("admin:concours_epreuve_changelist"), {"action": action, "_selected_action": [str(epreuve.pk)]}, follow=True)


@pytest.mark.django_db
def test_la_fiche_de_l_epreuve_montre_le_classement_provisoire(client):
    epreuve, *_ = construire_exemple()
    operateur = creer_utilisateur(is_staff=True)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)
    client.force_login(operateur)

    contenu = client.get(reverse("admin:concours_epreuve_change", args=[epreuve.pk])).content.decode()

    assert "30.33" in contenu and "ex aequo" in contenu and "notation incomplète" in contenu


@pytest.mark.django_db
def test_seul_le_responsable_client_voit_les_actions_de_validation(client):
    epreuve, *_, responsable = exemple_complet()
    responsable.is_staff = True
    responsable.save()
    operateur = creer_utilisateur(is_staff=True)
    AffectationOperateur.objects.create(mission=epreuve.categorie.concours.mission, utilisateur=operateur)

    client.force_login(operateur)
    page = client.get(reverse("admin:concours_epreuve_changelist")).content.decode()
    assert "Valider le classement définitif" not in page

    client.force_login(responsable)
    page = client.get(reverse("admin:concours_epreuve_changelist")).content.decode()
    assert "Valider le classement définitif" in page and "Ouvrir l&#x27;épreuve" not in page


@pytest.mark.django_db
def test_le_responsable_valide_depuis_l_administration_apres_confirmation_des_egalites(client):
    epreuve, *_, responsable = exemple_complet()
    responsable.is_staff = True
    responsable.save()
    client.force_login(responsable)

    refus = lancer(client, epreuve, "valider_le_classement")
    assert "égalité" in messages_de(refus) and Classement.objects.count() == 0

    ok = lancer(client, epreuve, "valider_le_classement_avec_egalites")
    assert "classement validé" in messages_de(ok) and Classement.objects.count() == 1


@pytest.mark.django_db
def test_un_classement_valide_se_consulte_mais_ne_s_ecrit_pas_dans_l_administration(client):
    epreuve, *_, responsable = exemple_complet()
    from apps.resultats import validation

    classement = validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    client.force_login(Utilisateur.objects.create_superuser("admin-res", password="x"))

    assert client.get(reverse("admin:resultats_classement_change", args=[classement.pk])).status_code == 200
    assert client.get(reverse("admin:resultats_classement_add")).status_code == 403
    assert client.post(reverse("admin:resultats_classement_delete", args=[classement.pk]), {"post": "yes"}).status_code == 403
