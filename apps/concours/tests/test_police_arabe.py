"""Police et taille du texte arabe réglées par concours (affichage seulement, règle n° 1 : le verset n'est jamais modifié).

Le CSS produit est inséré tel quel dans les pages : on vérifie qu'il ne peut contenir que des constantes, un nombre borné
et une adresse simple (pas d'injection via le nom du fichier téléversé).
"""
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.commun.tests.outils import creer_concours, creer_mission, creer_session, creer_utilisateur
from apps.concours import polices
from apps.concours.models import Concours
from apps.concours.polices import PoliceArabe, valider_fichier_police
from apps.coran.tests.outils import creer_sourate, creer_verset, creer_version
from apps.utilisateurs.models import AffectationOperateur, Utilisateur

WOFF2 = b"wOF2" + b"\x00" * 60
TTF = b"\x00\x01\x00\x00" + b"\x00" * 60


def police(nom="amiri.woff2", contenu=WOFF2):
    return SimpleUploadedFile(nom, contenu)


# --- Fichier téléversé ----------------------------------------------------------


def test_un_fichier_woff2_valide_est_accepte():
    valider_fichier_police(police())


def test_un_fichier_ttf_valide_est_accepte():
    valider_fichier_police(police("police.ttf", TTF))


def test_un_fichier_qui_n_est_pas_une_police_est_refuse():
    with pytest.raises(ValidationError, match="pas une police"):
        valider_fichier_police(police("faux.woff2", b"<html>pas une police</html>"))


def test_une_extension_qui_ne_correspond_pas_au_contenu_est_refusee():
    with pytest.raises(ValidationError, match="extension"):
        valider_fichier_police(police("police.ttf", WOFF2))


def test_un_fichier_trop_gros_est_refuse():
    gros = SimpleUploadedFile("grosse.woff2", WOFF2 + b"\x00" * polices.TAILLE_MAX_FICHIER)
    with pytest.raises(ValidationError, match="3 Mo"):
        valider_fichier_police(gros)


# --- Modèle ---------------------------------------------------------------------


@pytest.mark.django_db
def test_par_defaut_aucun_reglage_particulier():
    concours = creer_concours()
    assert concours.police_arabe == PoliceArabe.DEFAUT
    assert concours.taille_texte_arabe == 100
    assert not concours.police_arabe_fichier


@pytest.mark.django_db
def test_la_police_personnalisee_exige_un_fichier():
    concours = creer_concours()
    concours.police_arabe = PoliceArabe.PERSONNALISEE
    with pytest.raises(ValidationError) as erreur:
        concours.full_clean()
    assert "police_arabe_fichier" in erreur.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize("taille", [49, 201])
def test_la_taille_hors_bornes_est_refusee(taille):
    concours = creer_concours()
    concours.taille_texte_arabe = taille
    with pytest.raises(ValidationError) as erreur:
        concours.full_clean()
    assert "taille_texte_arabe" in erreur.value.message_dict


# --- CSS produit ----------------------------------------------------------------


@pytest.mark.django_db
def test_css_par_defaut_sans_police_embarquee():
    css = polices.css(creer_concours())
    assert "@font-face" not in css
    assert "Amiri Quran" in css
    assert "--echelle-coran: 1.00" in css


@pytest.mark.django_db
def test_css_d_une_police_de_la_liste_avec_echelle():
    concours = creer_concours(police_arabe=PoliceArabe.NASKH, taille_texte_arabe=150)
    css = polices.css(concours)
    assert '--police-coran: "Noto Naskh Arabic"' in css
    assert "--echelle-coran: 1.50" in css


@pytest.mark.django_db
def test_css_d_un_fichier_televerse_declare_une_police_embarquee():
    concours = creer_concours(police_arabe=PoliceArabe.PERSONNALISEE)
    concours.police_arabe_fichier.save("hafs.woff2", police("hafs.woff2"))
    css = polices.css(concours)
    assert '@font-face { font-family: "QuranovaArabe"' in css
    assert 'format("woff2")' in css
    assert concours.police_arabe_fichier.url in css
    assert '--police-coran: "QuranovaArabe"' in css


def test_une_adresse_suspecte_n_entre_jamais_dans_le_css():
    faux = SimpleNamespace(police_arabe=PoliceArabe.PERSONNALISEE, taille_texte_arabe=100)
    faux.police_arabe_fichier = SimpleNamespace(url='/media/x");}body{display:none;/*.woff2', name="x.woff2")
    css = polices.css(faux)
    assert "display:none" not in css and "@font-face" not in css
    assert "Amiri Quran" in css  # repli sur la police par défaut


# --- Pages des écrans -----------------------------------------------------------


@pytest.fixture
def session_reglee(db):
    concours = creer_concours(police_arabe=PoliceArabe.SCHEHERAZADE, taille_texte_arabe=130)
    return creer_session(concours)


@pytest.mark.django_db
def test_la_page_de_scene_porte_les_reglages_du_concours(client, session_reglee):
    html = client.get(reverse("presentation:ecran_scene", args=[session_reglee.pk])).content.decode()
    assert '--police-coran: "Scheherazade New"' in html
    assert "--echelle-coran: 1.30" in html


@pytest.mark.django_db
def test_la_page_du_jury_porte_les_reglages_du_concours(client, session_reglee):
    html = client.get(reverse("jury:ecran_jury", args=[session_reglee.pk])).content.decode()
    assert '--police-coran: "Scheherazade New"' in html


@pytest.mark.django_db
def test_la_page_de_commande_porte_les_reglages_du_concours(client, session_reglee):
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=session_reglee.concours.mission, utilisateur=operateur)
    client.force_login(operateur)
    html = client.get(reverse("presentation:ecran_commande", args=[session_reglee.pk])).content.decode()
    assert "--echelle-coran: 1.30" in html


@pytest.mark.django_db
def test_rm14_la_page_du_tirage_ne_charge_aucune_police_arabe(client):
    html = client.get(reverse("prestations:ecran_tirage")).content.decode()
    assert "--police-coran" not in html


# --- Administration -------------------------------------------------------------


@pytest.fixture
def administrateur(db, client):
    utilisateur = Utilisateur.objects.create_superuser("admin-police", password="x")
    client.force_login(utilisateur)
    return utilisateur


@pytest.mark.django_db
def test_l_administration_regle_la_police_du_concours(client, administrateur):
    concours = creer_concours()
    url = reverse("admin:concours_concours_change", args=[concours.pk])
    page = client.get(url).content.decode()
    assert "Affichage du texte arabe" in page
    donnees = {
        "mission": concours.mission_id, "nom": concours.nom, "edition": concours.edition, "format": concours.format,
        "date_debut": concours.date_debut.isoformat(), "date_fin": concours.date_fin.isoformat(),
        "police_arabe": PoliceArabe.TRADITIONAL, "taille_texte_arabe": 120,
    }
    reponse = client.post(url, donnees)
    assert reponse.status_code == 302
    concours.refresh_from_db()
    assert concours.police_arabe == PoliceArabe.TRADITIONAL and concours.taille_texte_arabe == 120


@pytest.mark.django_db
def test_l_administration_refuse_une_police_personnalisee_sans_fichier(client, administrateur):
    concours = creer_concours()
    donnees = {
        "mission": concours.mission_id, "nom": concours.nom, "edition": concours.edition, "format": concours.format,
        "date_debut": concours.date_debut.isoformat(), "date_fin": concours.date_fin.isoformat(),
        "police_arabe": PoliceArabe.PERSONNALISEE, "taille_texte_arabe": 100,
    }
    reponse = client.post(reverse("admin:concours_concours_change", args=[concours.pk]), donnees)
    assert reponse.status_code == 200 and "Téléversez le fichier de police" in reponse.content.decode()
    concours.refresh_from_db()
    assert concours.police_arabe == PoliceArabe.DEFAUT


@pytest.mark.django_db
def test_l_apercu_montre_le_premier_verset_du_corpus_sans_le_modifier(client, administrateur):
    version = creer_version()
    sourate = creer_sourate(version, numero=1)
    verset = creer_verset(sourate, numero=1, texte="texte-neutre-du-corpus")
    concours = creer_concours(version_corpus=version)
    page = client.get(reverse("admin:concours_concours_change", args=[concours.pk])).content.decode()
    assert verset.texte in page
    assert "Verset 1:1" in page


@pytest.mark.django_db
def test_l_apercu_demande_d_abord_la_version_du_corpus(client, administrateur):
    concours = creer_concours()
    page = client.get(reverse("admin:concours_concours_change", args=[concours.pk])).content.decode()
    assert "Choisissez d&#x27;abord la version du corpus" in page


# --- Duplication ----------------------------------------------------------------


@pytest.mark.django_db
def test_la_duplication_reprend_les_reglages_d_affichage():
    from apps.concours import services
    from datetime import date

    mission = creer_mission()
    source = creer_concours(mission, police_arabe=PoliceArabe.NASKH, taille_texte_arabe=140)
    admin = Utilisateur.objects.create_superuser("admin-dup", password="x")
    copie = services.dupliquer_concours(
        source, auteur=admin, nom="Copie", edition="2028", date_debut=date(2028, 1, 1), date_fin=date(2028, 1, 2),
    ).concours
    assert (copie.police_arabe, copie.taille_texte_arabe) == (PoliceArabe.NASKH, 140)
