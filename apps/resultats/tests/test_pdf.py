"""Procès-verbal et classements en PDF (§11, §17.1 ; WeasyPrint).

Le PDF est produit à partir du MÊME HTML que l'impression du navigateur : une seule source de vérité (REC-16 vaut donc aussi pour le PDF).
Les tests sont ignorés si WeasyPrint ou ses bibliothèques système (Pango) manquent sur la machine.
"""
import shutil
import subprocess
import time

import pytest
from django.urls import reverse

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_utilisateur
from apps.resultats import documents, pdf, validation
from apps.resultats.tests.test_documents import concours_de_candidats
from apps.resultats.tests.test_validation import exemple_complet
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def _weasyprint_disponible():
    try:
        pdf.html_vers_pdf("<p>essai</p>")
        return True
    except pdf.PdfIndisponibleError:
        return False


pytestmark = pytest.mark.skipif(not _weasyprint_disponible(), reason="WeasyPrint ou Pango indisponible sur cette machine")


def texte_du_pdf(contenu):
    """Le texte d'un PDF, via pdftotext si présent ; sinon on se contente de vérifier l'en-tête du fichier."""
    assert contenu.startswith(b"%PDF-")
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext absent : contenu du PDF non vérifiable ici")
    resultat = subprocess.run(["pdftotext", "-layout", "-", "-"], input=contenu, capture_output=True, check=True)
    return resultat.stdout.decode("utf-8")


# --- Conversion -------------------------------------------------------------------------------------------------------


def test_le_convertisseur_produit_un_pdf():
    contenu = pdf.html_vers_pdf("<h1>Procès-verbal é à ç</h1>")
    assert contenu.startswith(b"%PDF-")


@pytest.mark.parametrize("adresse", [
    "http://exemple.invalide/x.png", "https://exemple.invalide/x.css", "file:///etc/passwd", "ftp://exemple.invalide/x", "/etc/passwd",
])
def test_le_convertisseur_ne_va_jamais_chercher_hors_static_et_media(adresse):
    """Même si un contenu saisi finissait dans le HTML, le PDF ne lit ni le réseau ni un fichier arbitraire du serveur."""
    with pytest.raises(ValueError):
        pdf.chercher_ressource(adresse)


def test_le_convertisseur_retrouve_les_fichiers_statiques():
    ressource = pdf.chercher_ressource("http://pdf.local/static/img/quranova-logo.png")
    assert ressource["mime_type"] == "image/png" and ressource["file_obj"].read(4) == b"\x89PNG"


def test_les_traversees_de_dossier_sont_refusees():
    with pytest.raises(ValueError):
        pdf.chercher_ressource("http://pdf.local/media/../../etc/passwd")
    with pytest.raises(ValueError):
        pdf.chercher_ressource("http://pdf.local/static/%2e%2e/%2e%2e/etc/passwd")


def test_sans_weasyprint_le_message_explique_quoi_faire(monkeypatch):
    import builtins

    reel = builtins.__import__

    def sans_weasyprint(nom, *args, **kwargs):
        if nom == "weasyprint":
            raise OSError("cannot load library 'libpango-1.0-0'")
        return reel(nom, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sans_weasyprint)
    with pytest.raises(pdf.PdfIndisponibleError, match="Pango"):
        pdf.html_vers_pdf("<p>x</p>")


# --- Procès-verbal ----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_rec16_le_pv_pdf_ne_contient_aucun_resultat_non_valide():
    epreuve, *_ = exemple_complet()[:1]

    texte = texte_du_pdf(documents.proces_verbal_pdf(epreuve.categorie.concours))

    assert "PROVISOIRE" in texte and "Classement non validé" in texte
    assert "30,33" not in texte


@pytest.mark.django_db
def test_apres_validation_le_pv_pdf_donne_les_rangs_et_les_scores_comme_le_html():
    epreuve, _, _, _, responsable = exemple_complet()
    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    texte = texte_du_pdf(documents.proces_verbal_pdf(epreuve.categorie.concours, responsable))

    assert "Procès-verbal définitif" in texte and "30,33" in texte and "Candidat-A" in texte and "ex aequo" in texte
    assert "Page 1" in texte  # pied de page paginé (@page)


@pytest.mark.django_db
def test_le_pv_pdf_est_journalise_une_seule_fois_sans_compter_l_html():
    epreuve, _, _, _, responsable = exemple_complet()
    concours = epreuve.categorie.concours

    documents.proces_verbal_pdf(concours, responsable)

    assert EntreeAudit.objects.filter(action="document.pv_pdf_genere", objet_id=str(concours.pk)).count() == 1
    assert EntreeAudit.objects.filter(action="document.pv_genere", objet_id=str(concours.pk)).count() == 0


@pytest.mark.django_db
def test_rec42_le_pv_pdf_de_500_candidats_est_genere_en_moins_de_30_secondes():
    concours, responsable = concours_de_candidats(500)

    debut = time.perf_counter()
    contenu = documents.proces_verbal_pdf(concours, responsable)
    duree = time.perf_counter() - debut

    assert duree < 30, f"{duree:.1f} s"
    assert contenu.startswith(b"%PDF-") and len(contenu) > 10_000


# --- Classements par catégorie ----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_les_classements_pdf_ne_montrent_que_les_classements_valides():
    epreuve, _, _, _, responsable = exemple_complet()
    concours = epreuve.categorie.concours

    avant = texte_du_pdf(documents.classements_pdf(concours, responsable))
    assert "n'a pas encore été validé" in avant and "Candidat-A" not in avant

    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    apres = texte_du_pdf(documents.classements_pdf(concours, responsable))
    assert epreuve.categorie.nom in apres and "Candidat-A" in apres and "30,33" in apres


# --- Vues -------------------------------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("nom", ["proces_verbal_pdf", "classements_pdf"])
def test_la_vue_pdf_sert_un_pdf_en_telechargement(client, nom):
    epreuve, _, _, _, responsable = exemple_complet()
    concours = epreuve.categorie.concours
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=concours.mission, utilisateur=operateur)
    client.force_login(operateur)

    reponse = client.get(reverse(f"resultats:{nom}", args=[concours.pk]))

    assert reponse.status_code == 200 and reponse["Content-Type"] == "application/pdf"
    assert "attachment" in reponse["Content-Disposition"] and ".pdf" in reponse["Content-Disposition"]
    assert reponse["Cache-Control"] == "no-store" and reponse.content.startswith(b"%PDF-")


@pytest.mark.django_db
@pytest.mark.parametrize("nom", ["proces_verbal_pdf", "classements_pdf"])
def test_rec29_un_utilisateur_sans_acces_obtient_404_et_un_anonyme_est_renvoye_vers_la_connexion(client, nom):
    epreuve, *_ = exemple_complet()
    concours = epreuve.categorie.concours
    url = reverse(f"resultats:{nom}", args=[concours.pk])
    assert client.get(url).status_code == 302

    client.force_login(creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True))  # non affecté à cette mission
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_si_le_pdf_est_indisponible_la_vue_explique_et_renvoie_vers_la_version_imprimable(client, monkeypatch):
    epreuve, *_ = exemple_complet()
    concours = epreuve.categorie.concours
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=concours.mission, utilisateur=operateur)
    client.force_login(operateur)

    def indisponible(*args, **kwargs):
        raise pdf.PdfIndisponibleError("Pango est introuvable sur ce serveur.")

    monkeypatch.setattr(documents, "proces_verbal_pdf", indisponible)
    reponse = client.get(reverse("resultats:proces_verbal_pdf", args=[concours.pk]))

    assert reponse.status_code == 503
    contenu = reponse.content.decode()
    assert "Pango" in contenu and reverse("resultats:proces_verbal", args=[concours.pk]) in contenu
