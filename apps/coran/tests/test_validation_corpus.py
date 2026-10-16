"""Validation du corpus par le référent coranique (§12.2, §12.3 ; jalon J0, livrable L-07).

Contrôles automatiques (dont l'aller-retour sur le fichier source), échantillon de relecture, procès-verbal à signer, enregistrement de la
validation (administrateur seulement), activation. Les contrôles lourds utilisent les VRAIS fichiers Tanzil de data/corpus (importés dans la base de test).
"""
import hashlib
import shutil

import pytest
from django.conf import settings
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_utilisateur
from apps.coran import validation
from apps.coran.exceptions import CorpusImmuableError, CorpusInvalideError, ValidationCorpusRefuseeError
from apps.coran.importation import importer_corpus, lire_corpus
from apps.coran.models import Sourate, ValidationCorpus, Verset, VersionCorpus
from apps.coran.tests.outils import creer_sourate, creer_version
from apps.utilisateurs.models import Utilisateur

DOSSIER = settings.BASE_DIR / "data" / "corpus"
TEXTE, META = DOSSIER / "quran-uthmani.xml", DOSSIER / "quran-data.xml"

pytestmark = pytest.mark.skipif(not (TEXTE.is_file() and META.is_file()), reason="Fichiers Tanzil absents de data/corpus")


@pytest.fixture
def version(db):
    return importer_corpus(lire_corpus(TEXTE, META))


@pytest.fixture
def administrateur(db):
    return creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True)


def par_libelle(controles):
    return {c.libelle: c for c in controles}


# --- Contrôles automatiques ---------------------------------------------------------------------------------------------------


def test_les_controles_automatiques_passent_sur_les_vrais_fichiers_tanzil(version):
    controles = validation.controles_automatiques(version)

    assert [c.libelle for c in controles] == [
        "114 sourates, numérotées de 1 à 114", "6 236 versets", "nombre de versets de chaque sourate conforme aux métadonnées",
        "aucun verset vide, numérotation continue", "aller-retour : texte de la base identique au fichier source, octet par octet",
    ]
    assert all(c.ok for c in controles), [(c.libelle, c.detail) for c in controles if not c.ok]


def test_un_verset_altere_en_base_fait_echouer_l_aller_retour(version):
    """Garde-fou contre toute corruption (disque, import manuel, SQL direct) : on compare à la source, pas à la base elle-même."""
    verset = Verset.objects.get(sourate__version=version, sourate__numero=2, numero=255)
    Verset.objects.filter(pk=verset.pk).update(texte=verset.texte + "x")  # update() : contourne les gardes du modèle, comme le ferait du SQL direct

    controle = par_libelle(validation.controles_automatiques(version))["aller-retour : texte de la base identique au fichier source, octet par octet"]

    assert not controle.ok and "2:255" in controle.detail


def test_l_aller_retour_est_impossible_sans_le_fichier_source_et_la_validation_est_alors_refusee(version, administrateur, tmp_path):
    controle = par_libelle(validation.controles_automatiques(version, dossier=tmp_path))["aller-retour : texte de la base identique au fichier source, octet par octet"]
    assert not controle.ok and "introuvable" in controle.detail.lower()

    with pytest.raises(CorpusInvalideError, match="Contrôles"):
        validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate(), dossier=tmp_path)
    version.refresh_from_db()
    assert version.statut == VersionCorpus.Statut.IMPORTEE


def test_le_fichier_source_est_retrouve_par_son_empreinte_pas_par_son_nom(version, tmp_path):
    shutil.copy(TEXTE, tmp_path / "copie-renommee.xml")
    shutil.copy(META, tmp_path / "quran-data.xml")

    assert validation.trouver_fichier_source(version, tmp_path).name == "copie-renommee.xml"
    (tmp_path / "copie-renommee.xml").write_bytes(TEXTE.read_bytes() + b" ")  # une copie altérée n'est pas le fichier de cette version
    assert validation.trouver_fichier_source(version, tmp_path) is None


def test_un_corpus_incomplet_echoue_aux_controles_de_structure(db):
    petite = creer_version()
    creer_sourate(petite, numero=1, nombre_versets=7, ordre_revelation=1)

    controles = par_libelle(validation.controles_automatiques(petite))

    assert not controles["114 sourates, numérotées de 1 à 114"].ok and not controles["6 236 versets"].ok


# --- Échantillon de relecture ------------------------------------------------------------------------------------------------------


def test_l_echantillon_contient_les_passages_imposes_par_le_cdc(version):
    echantillon = validation.echantillon_de_relecture(version)
    references = {e.reference for e in echantillon}

    assert {f"1:{n}" for n in range(1, 8)} <= references            # sourate 1
    assert {"2:255", "2:282"} <= references                           # verset du Trône, plus long verset
    assert {f"36:{n}" for n in range(1, 84)} <= references            # sourate 36
    assert {f"112:{n}" for n in range(1, 5)} | {f"113:{n}" for n in range(1, 6)} | {f"114:{n}" for n in range(1, 7)} <= references


def test_l_echantillon_ajoute_au_moins_1_pour_cent_de_versets_tires_sans_doublon(version):
    echantillon = validation.echantillon_de_relecture(version)
    hasard = [e for e in echantillon if e.motif == "tirage"]

    assert len(hasard) >= 63  # 1 % de 6 236 versets, arrondi au-dessus
    assert len({e.reference for e in echantillon}) == len(echantillon)  # chaque verset une seule fois
    obligatoires = {e.reference for e in echantillon if e.motif != "tirage"}
    assert not obligatoires & {e.reference for e in hasard}


def test_l_echantillon_est_reproductible_pour_une_meme_version(version):
    """Dérivé de l'empreinte du fichier : le procès-verbal régénéré demain porte exactement le même échantillon que celui signé aujourd'hui."""
    assert [e.reference for e in validation.echantillon_de_relecture(version)] == [e.reference for e in validation.echantillon_de_relecture(version)]


def test_l_echantillon_porte_le_texte_exact_de_la_base(version):
    for e in validation.echantillon_de_relecture(version)[:20]:
        sourate, numero = (int(x) for x in e.reference.split(":"))
        assert e.texte == Verset.objects.get(sourate__version=version, sourate__numero=sourate, numero=numero).texte


# --- Enregistrement de la validation ---------------------------------------------------------------------------------------------------


def test_la_validation_enregistre_le_referent_la_date_les_controles_et_passe_la_version_a_validee(version, administrateur):
    validee = validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate(), qualite="Imam, référent coranique")

    version.refresh_from_db()
    assert version.statut == VersionCorpus.Statut.VALIDEE and version.date_validation is not None
    assert (validee.referent_nom, validee.referent_qualite, validee.validee_par) == ("Cheikh Test", "Imam, référent coranique", administrateur)
    assert validee.controles and all(c["ok"] for c in validee.controles)
    attendu = hashlib.sha256((version.empreinte_sha256 + "|" + "|".join(e.reference for e in validation.echantillon_de_relecture(version))).encode()).hexdigest()
    assert validee.empreinte_echantillon == attendu
    assert EntreeAudit.objects.filter(action="corpus.valide").count() == 1


def test_seul_l_administrateur_valide_un_corpus(version):
    for role in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.RESPONSABLE_CLIENT):
        with pytest.raises(ValidationCorpusRefuseeError):
            validation.valider_version(version, creer_utilisateur(role), "Cheikh Test", timezone.localdate())
    assert not ValidationCorpus.objects.exists()


def test_le_nom_du_referent_est_obligatoire(version, administrateur):
    for nom in ("", "   "):
        with pytest.raises(CorpusInvalideError, match="référent"):
            validation.valider_version(version, administrateur, nom, timezone.localdate())


def test_une_date_de_signature_future_est_refusee(version, administrateur):
    from datetime import timedelta

    with pytest.raises(CorpusInvalideError, match="date"):
        validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate() + timedelta(days=2))


def test_on_ne_valide_pas_deux_fois_une_version(version, administrateur):
    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate())

    with pytest.raises(CorpusImmuableError):
        validation.valider_version(version, administrateur, "Autre", timezone.localdate())
    assert ValidationCorpus.objects.count() == 1


def test_apres_validation_le_texte_ne_peut_plus_changer(version, administrateur):
    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate())

    with pytest.raises(CorpusImmuableError):
        Verset.objects.filter(sourate__version=version).first().save()


# --- Activation -------------------------------------------------------------------------------------------------------------------------


def test_l_activation_exige_une_version_validee(version, administrateur):
    with pytest.raises(CorpusImmuableError):
        validation.activer_version(version, administrateur)  # encore « importée »

    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate())
    validation.activer_version(version, administrateur)
    version.refresh_from_db()
    assert version.statut == VersionCorpus.Statut.ACTIVE
    assert EntreeAudit.objects.filter(action="corpus.active").count() == 1


def test_seul_l_administrateur_active(version, administrateur):
    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate())

    with pytest.raises(ValidationCorpusRefuseeError):
        validation.activer_version(version, creer_utilisateur(Utilisateur.Role.OPERATEUR))


def test_on_n_active_pas_une_version_s_il_en_existe_deja_une_active_pour_la_meme_riwaya(version, administrateur):
    """Une seule version active par riwāya : une autre devrait être retirée d'abord, de façon réfléchie (les concours existants gardent la leur)."""
    ancienne = creer_version()
    VersionCorpus.objects.filter(pk=ancienne.pk).update(statut=VersionCorpus.Statut.ACTIVE)
    validation.valider_version(version, administrateur, "Cheikh Test", timezone.localdate())

    with pytest.raises(CorpusImmuableError, match="déjà active"):
        validation.activer_version(version, administrateur)
