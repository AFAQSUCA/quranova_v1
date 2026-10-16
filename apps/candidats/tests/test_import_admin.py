"""Import des candidats par téléversement depuis l'administration (§7.3) : l'opérateur n'a pas à ouvrir un terminal."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.candidats import modele
from apps.candidats.models import Participation
from apps.commun.tests.outils import creer_categorie, creer_concours, creer_utilisateur
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def concours(db):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")
    creer_categorie(concours, nom="Seniors")
    return concours


@pytest.fixture
def operateur(concours):
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=concours.mission, utilisateur=operateur)
    return operateur


def envoyer(client, concours, contenu, simuler=True, nom="candidats.csv"):
    donnees = {"action": "importer_les_candidats", "_selected_action": [str(concours.pk)], "appliquer": "1",
               "fichier": SimpleUploadedFile(nom, contenu, content_type="text/csv")}
    if simuler:
        donnees["simuler"] = "on"
    return client.post(reverse("admin:concours_concours_changelist"), donnees)


def test_le_formulaire_propose_le_telechargement_du_modele_et_la_simulation_par_defaut(client, concours, operateur):
    client.force_login(operateur)

    page = client.post(reverse("admin:concours_concours_changelist"), {"action": "importer_les_candidats", "_selected_action": [str(concours.pk)]})

    contenu = page.content.decode()
    assert page.status_code == 200 and reverse("candidats:modele_import", args=[concours.pk]) in contenu and 'name="simuler"' in contenu


def test_la_simulation_affiche_le_rapport_sans_rien_enregistrer(client, concours, operateur):
    client.force_login(operateur)

    reponse = envoyer(client, concours, modele.contenu_modele(concours), simuler=True)

    assert reponse.status_code == 200 and "Simulation" in reponse.content.decode()
    assert not Participation.objects.filter(concours=concours).exists()


def test_l_import_reel_inscrit_les_candidats_et_le_rapport_les_numerote(client, concours, operateur):
    client.force_login(operateur)

    reponse = envoyer(client, concours, modele.contenu_modele(concours), simuler=False)

    page = reponse.content.decode()
    assert reponse.status_code == 200 and "2 candidats inscrits" in page
    assert Participation.objects.filter(concours=concours).count() == 2


def test_un_fichier_avec_erreurs_n_enregistre_rien_et_liste_toutes_les_erreurs(client, concours, operateur):
    client.force_login(operateur)
    mauvais = "nom;prenom;date_naissance;sexe;ville;structure;categorie\r\nDiallo;Awa;31/02/2010;F;X;Y;Juniors\r\nKoné;Ali;01/01/2000;Z;X;Y;Inconnue\r\n".encode("utf-8")

    reponse = envoyer(client, concours, mauvais, simuler=False)

    page = reponse.content.decode()
    assert "Ligne 2" in page and "Ligne 3" in page and not Participation.objects.exists()


def test_un_fichier_trop_gros_ou_vide_est_refuse(client, concours, operateur):
    client.force_login(operateur)

    assert "vide" in envoyer(client, concours, b"").content.decode().lower()
    gros = b"nom;prenom;categorie\r\n" + b"x;y;Juniors\r\n" * 600_000
    assert "volumineux" in envoyer(client, concours, gros).content.decode().lower()
    assert not Participation.objects.exists()


def test_le_responsable_client_ne_peut_pas_importer_meme_en_forcant_la_requete(client, concours):
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation, is_staff=True))

    envoyer(client, concours, modele.contenu_modele(concours), simuler=False)

    assert not Participation.objects.exists()


def test_un_operateur_non_affecte_ne_voit_pas_le_concours_et_n_importe_rien(client, concours):
    client.force_login(creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True))

    envoyer(client, concours, modele.contenu_modele(concours), simuler=False)

    assert not Participation.objects.exists()
