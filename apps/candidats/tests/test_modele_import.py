"""Modèle d'import des candidats à remettre au client (livrable L-05, §7.3).

Le modèle est FABRIQUÉ À PARTIR DES COLONNES RÉELLES de l'importeur et vérifié par lui : s'il cesse d'être importable, un test échoue.
"""
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.audit.models import EntreeAudit
from apps.candidats import modele
from apps.candidats.importation import ALIAS_COLONNES, FACULTATIVES, OBLIGATOIRES, importer_candidats
from apps.commun.tests.outils import creer_categorie, creer_concours, creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

MODELE_VERSIONNE = Path(settings.BASE_DIR) / "docs" / "modeles" / "candidats-modele.csv"


def test_le_modele_a_exactement_les_colonnes_de_l_importeur():
    en_tete = modele.contenu_modele().decode("utf-8-sig").splitlines()[0].split(";")

    assert en_tete == list(modele.COLONNES)
    assert set(OBLIGATOIRES) | set(FACULTATIVES) == set(modele.COLONNES)
    assert all(ALIAS_COLONNES[c.replace("_", "")] == c for c in modele.COLONNES)  # chaque colonne est reconnue telle quelle


def test_le_modele_est_au_format_attendu_par_excel_francais():
    octets = modele.contenu_modele()

    assert octets.startswith(b"\xef\xbb\xbf") and b"\r\n" in octets  # UTF-8 avec BOM : les accents survivent à Excel
    assert octets.decode("utf-8-sig").splitlines()[0].count(";") == len(modele.COLONNES) - 1


def test_les_lignes_d_exemple_sont_reperables_pour_ne_pas_etre_importees_par_erreur():
    lignes = modele.contenu_modele().decode("utf-8-sig").splitlines()[1:]

    assert lignes and all(ligne.startswith("EXEMPLE-") for ligne in lignes)


@pytest.mark.django_db
def test_le_modele_d_un_concours_est_importable_tel_quel_avec_ses_vraies_categories(tmp_path):
    concours = creer_concours()
    creer_categorie(concours, nom="Hifz Juniors")
    creer_categorie(concours, nom="Hifz Seniors")
    fichier = tmp_path / "modele.csv"
    fichier.write_bytes(modele.contenu_modele(concours))

    rapport = importer_candidats(concours, fichier, simuler=True)

    assert rapport.ok, rapport.texte()
    assert {i.categorie for i in rapport.inscriptions} == {"Hifz Juniors", "Hifz Seniors"}


@pytest.mark.django_db
def test_le_modele_d_un_concours_sans_categorie_reste_lisible_mais_signale_le_probleme(tmp_path):
    concours = creer_concours()
    fichier = tmp_path / "modele.csv"
    fichier.write_bytes(modele.contenu_modele(concours))

    rapport = importer_candidats(concours, fichier, simuler=True)

    assert not rapport.ok and "Catégorie" in rapport.texte()  # il faut créer les catégories avant d'importer


@pytest.mark.django_db
def test_le_modele_generique_a_une_ligne_valide_pour_chaque_type_de_donnee(tmp_path):
    concours = creer_concours()
    creer_categorie(concours, nom="Catégorie A")
    creer_categorie(concours, nom="Catégorie B")
    fichier = tmp_path / "modele.csv"
    fichier.write_bytes(modele.contenu_modele())

    assert importer_candidats(concours, fichier, simuler=True).ok


def test_le_fichier_modele_versionne_est_a_jour():
    """docs/modeles/candidats-modele.csv est ce qu'on envoie au client : il ne doit jamais diverger du générateur."""
    assert MODELE_VERSIONNE.read_bytes() == modele.contenu_modele()


@pytest.mark.django_db
def test_telechargement_par_le_personnel_affecte_et_par_le_responsable_du_client_seulement(client):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")
    url = reverse("candidats:modele_import", args=[concours.pk])
    assert client.get(url).status_code == 302

    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    client.force_login(operateur)
    assert client.get(url).status_code == 404  # non affecté (RM-20)
    AffectationOperateur.objects.create(mission=concours.mission, utilisateur=operateur)
    reponse = client.get(url)
    assert reponse.status_code == 200 and reponse["Content-Type"].startswith("text/csv")
    assert "attachment" in reponse["Content-Disposition"] and reponse.content.startswith(b"\xef\xbb\xbf")
    assert b"Juniors" in reponse.content

    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation, is_staff=True))
    assert client.get(url).status_code == 200
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=creer_organisation(), is_staff=True))
    assert client.get(url).status_code == 404  # un autre client ne voit rien
    assert EntreeAudit.objects.filter(action="document.modele_import_telecharge").count() == 2
