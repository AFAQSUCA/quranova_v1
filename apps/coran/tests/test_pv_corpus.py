"""Procès-verbal de validation du corpus (L-07) et actions d'administration (validation, activation)."""
import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_utilisateur
from apps.coran import documents, validation
from apps.coran.importation import importer_corpus, lire_corpus
from apps.coran.models import ValidationCorpus, Verset, VersionCorpus
from apps.resultats import pdf
from apps.utilisateurs.models import Utilisateur

TEXTE = settings.BASE_DIR / "data" / "corpus" / "quran-uthmani.xml"
META = settings.BASE_DIR / "data" / "corpus" / "quran-data.xml"

pytestmark = pytest.mark.skipif(not (TEXTE.is_file() and META.is_file()), reason="Fichiers Tanzil absents de data/corpus")


@pytest.fixture
def version(db):
    return importer_corpus(lire_corpus(TEXTE, META))


@pytest.fixture
def administrateur(db):
    return creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True)


# --- Document -------------------------------------------------------------------------------------------------------------


def test_le_pv_identifie_la_version_les_controles_et_l_echantillon_avec_le_texte_exact_de_la_base(version, administrateur):
    html = documents.proces_verbal_corpus(version, administrateur)

    assert version.empreinte_sha256 in html and "Tanzil" in html and "Mushaf de Médine" in html
    assert html.count("Réussi") == 5 and "ÉCHEC" not in html
    trone = Verset.objects.get(sourate__version=version, sourate__numero=2, numero=255).texte
    assert trone in html and 'lang="ar" dir="rtl"' in html  # le texte est montré tel quel, sans rien modifier
    assert "Rendu typographique" in html and "Le référent coranique" in html and "Signature" in html


def test_le_pv_d_une_version_dont_un_controle_echoue_dit_qu_elle_ne_peut_pas_etre_validee(version):
    Verset.objects.filter(sourate__version=version, sourate__numero=1, numero=1).update(texte="altéré")

    html = documents.proces_verbal_corpus(version)

    assert "ÉCHEC" in html and "ne peut PAS être validée" in html


def test_le_pv_d_une_version_validee_porte_le_nom_du_referent_et_la_date(version, administrateur):
    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate(), qualite="Imam")
    version.refresh_from_db()

    html = documents.proces_verbal_corpus(version, administrateur)

    assert "Cheikh Test" in html and "Imam" in html and "validée</strong>" in html


def test_la_generation_du_pv_est_journalisee(version, administrateur):
    documents.proces_verbal_corpus(version, administrateur)

    assert EntreeAudit.objects.filter(action="document.pv_corpus_genere").count() == 1


def test_le_pv_existe_aussi_en_pdf(version, administrateur):
    try:
        contenu = documents.proces_verbal_corpus_pdf(version, administrateur)
    except pdf.PdfIndisponibleError:
        pytest.skip("WeasyPrint ou Pango indisponible sur cette machine")
    assert contenu.startswith(b"%PDF-") and len(contenu) > 20_000


# --- Vues -------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nom", ["coran:proces_verbal", "coran:proces_verbal_pdf"])
def test_seul_l_administrateur_ouvre_le_pv_du_corpus(client, version, administrateur, nom):
    url = reverse(nom, args=[version.pk])
    assert client.get(url).status_code == 302  # anonyme : vers la connexion

    for role in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.RESPONSABLE_CLIENT):
        client.force_login(creer_utilisateur(role, is_staff=True))
        assert client.get(url).status_code == 404
    client.force_login(administrateur)
    reponse = client.get(url)
    assert reponse.status_code in (200, 503)  # 503 seulement si WeasyPrint manque sur la machine
    if reponse.status_code == 200:
        assert reponse["Cache-Control"] == "no-store"


def test_une_version_inconnue_donne_404(client, administrateur):
    client.force_login(administrateur)
    assert client.get(reverse("coran:proces_verbal", args=[999999])).status_code == 404


# --- Administration -----------------------------------------------------------------------------------------------------------


def url_liste():
    return reverse("admin:coran_versioncorpus_changelist")


def poster(client, version, action, **plus):
    return client.post(url_liste(), {"action": action, "_selected_action": [str(version.pk)], **plus})


def test_le_formulaire_de_validation_puis_l_enregistrement(client, version, administrateur):
    client.force_login(administrateur)

    page = poster(client, version, "enregistrer_la_validation")
    assert page.status_code == 200 and "Enregistrer la validation" in page.content.decode()

    sans_attestation = poster(client, version, "enregistrer_la_validation", appliquer="1", referent_nom="Cheikh Test", date_signature=str(timezone.localdate()))
    assert sans_attestation.status_code == 200 and not ValidationCorpus.objects.exists()  # l'attestation du PV signé est obligatoire

    reponse = poster(client, version, "enregistrer_la_validation", appliquer="1", referent_nom="Cheikh Test",
                     referent_qualite="Imam", date_signature=str(timezone.localdate()), atteste="on")
    assert reponse.status_code == 302
    version.refresh_from_db()
    assert version.statut == VersionCorpus.Statut.VALIDEE and ValidationCorpus.objects.get().referent_nom == "Cheikh Test"


def test_l_activation_par_l_administration(client, version, administrateur):
    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate())
    client.force_login(administrateur)

    poster(client, version, "activer")

    version.refresh_from_db()
    assert version.statut == VersionCorpus.Statut.ACTIVE


def test_un_operateur_n_a_aucune_action_sur_le_corpus_meme_en_forcant_la_requete(client, version):
    client.force_login(creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True))

    page = client.get(url_liste())
    poster(client, version, "enregistrer_la_validation", appliquer="1", referent_nom="X", date_signature=str(timezone.localdate()), atteste="on")
    poster(client, version, "activer")

    assert "Enregistrer la validation" not in page.content.decode()
    version.refresh_from_db()
    assert version.statut == VersionCorpus.Statut.IMPORTEE and not ValidationCorpus.objects.exists()


def test_la_fiche_de_la_version_propose_le_pv_et_affiche_la_validation(client, version, administrateur):
    client.force_login(administrateur)
    fiche = reverse("admin:coran_versioncorpus_change", args=[version.pk])

    avant = client.get(fiche).content.decode()
    assert reverse("coran:proces_verbal", args=[version.pk]) in avant and "Non validée" in avant

    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate())
    assert "Cheikh Test" in client.get(fiche).content.decode()
