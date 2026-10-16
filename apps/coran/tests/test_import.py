"""Tests de l'import du corpus Tanzil (§12.2, règle absolue n°1).

Les tests fabriquent de PETITS fichiers XML neutres dans un dossier temporaire :
aucun texte coranique n'est saisi ici. Un seul test lit les vrais fichiers de
data/corpus pour vérifier les totaux (114 sourates, 6 236 versets).
"""
import hashlib
import re
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from apps.coran import services
from apps.coran.exceptions import CorpusDejaImporteError, CorpusInvalideError
from apps.coran.importation import calculer_empreinte_sha256, importer_corpus, lire_corpus
from apps.coran.models import Sourate, Verset, VersionCorpus

# Un texte avec une espace finale et un accent combinant (forme NFD) : il doit
# traverser l'import sans changer d'un seul octet.
TEXTE_ESPACE_FINAL = "texte-2-1 "
TEXTE_NFD = "é texte-2-2"

# (numéro, textes des versets, basmala)
SOURATES_MINI = [
    (1, ["texte-1-1", "texte-1-2"], ""),
    (2, [TEXTE_ESPACE_FINAL, TEXTE_NFD, "texte-2-3"], "basmala-de-test"),
    (9, ["texte-9-1", "texte-9-2"], ""),
]
# (numéro, nombre de versets, type Tanzil, ordre de révélation)
METADONNEES_MINI = [(1, 2, "Meccan", 5), (2, 3, "Medinan", 87), (9, 2, "Medinan", 113)]


def xml_texte(sourates, entete="Tanzil Quran Text (Uthmani, Version 1.1)"):
    lignes = ['<?xml version="1.0" encoding="utf-8" ?>']
    if entete:
        lignes.append(f"<!--\n#  {entete}\n-->")
    lignes.append("<quran>")
    for numero, textes, basmala in sourates:
        lignes.append(f'\t<sura index="{numero}" name="nom-arabe-{numero}">')
        for i, texte in enumerate(textes, 1):
            bismillah = f' bismillah="{basmala}"' if (i == 1 and basmala) else ""
            lignes.append(f'\t\t<aya index="{i}" text="{texte}"{bismillah} />')
        lignes.append("\t</sura>")
    lignes.append("</quran>")
    return "\n".join(lignes) + "\n"


def xml_metadonnees(metadonnees):
    lignes = ['<?xml version="1.0" encoding="utf-8" ?>', '<quran type="metadata">', '\t<suras alias="chapters">']
    for numero, ayas, type_tanzil, ordre in metadonnees:
        lignes.append(
            f'\t\t<sura index="{numero}" ayas="{ayas}" start="0" name="nom-arabe-{numero}" '
            f'tname="Translitteration-{numero}" ename="Nom-anglais-{numero}" '
            f'type="{type_tanzil}" order="{ordre}" rukus="1"/>'
        )
    lignes += ["\t</suras>", "</quran>"]
    return "\n".join(lignes) + "\n"


@pytest.fixture
def fichiers(tmp_path):
    """Écrit le mini corpus et renvoie (chemin du texte, chemin des métadonnées)."""
    texte = tmp_path / "texte.xml"
    meta = tmp_path / "meta.xml"
    texte.write_bytes(xml_texte(SOURATES_MINI).encode("utf-8"))
    meta.write_bytes(xml_metadonnees(METADONNEES_MINI).encode("utf-8"))
    return texte, meta


@pytest.fixture
def sans_controles(monkeypatch):
    """Neutralise les contrôles du §12.2 : le mini corpus n'a pas 114 sourates."""
    monkeypatch.setattr(services, "controler_corpus", lambda corpus: None)


# --- Empreinte --------------------------------------------------------------


def test_empreinte_sha256_correspond_au_contenu_du_fichier(tmp_path):
    fichier = tmp_path / "abc.bin"
    fichier.write_bytes(b"abc")

    assert calculer_empreinte_sha256(fichier) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


# --- Lecture : aucune transformation ----------------------------------------


def test_regle_absolue_1_lecture_sans_aucune_transformation_du_texte(fichiers):
    corpus = lire_corpus(*fichiers)

    textes = [v.texte for v in corpus.sourates[1].versets]
    assert textes == [TEXTE_ESPACE_FINAL, TEXTE_NFD, "texte-2-3"]
    assert textes[0].endswith(" ")
    assert "́" in textes[1]


def test_lecture_de_la_basmala_vide_pour_les_sourates_1_et_9(fichiers):
    corpus = lire_corpus(*fichiers)

    basmalas = {s.numero: s.basmala for s in corpus.sourates}
    assert basmalas == {1: "", 2: "basmala-de-test", 9: ""}


def test_lecture_des_metadonnees_de_la_sourate(fichiers):
    sourate_2 = lire_corpus(*fichiers).sourates[1]

    assert sourate_2.numero == 2
    assert sourate_2.nom_arabe == "nom-arabe-2"
    assert sourate_2.nom_translitteration == "Translitteration-2"
    assert sourate_2.nombre_versets == 3
    assert sourate_2.type_revelation == Sourate.TypeRevelation.MEDINOISE
    assert sourate_2.ordre_revelation == 87


def test_lecture_de_la_version_source_dans_l_entete(fichiers):
    corpus = lire_corpus(*fichiers)

    assert corpus.version_source == "1.1"
    assert corpus.nom_fichier == "texte.xml"
    assert corpus.empreinte_sha256 == calculer_empreinte_sha256(fichiers[0])


def test_version_source_exigee_si_l_entete_est_absent(tmp_path):
    texte, meta = tmp_path / "t.xml", tmp_path / "m.xml"
    texte.write_bytes(xml_texte(SOURATES_MINI, entete="").encode("utf-8"))
    meta.write_bytes(xml_metadonnees(METADONNEES_MINI).encode("utf-8"))

    with pytest.raises(CorpusInvalideError):
        lire_corpus(texte, meta)
    assert lire_corpus(texte, meta, version_source="1.2").version_source == "1.2"


def test_fichier_copie_depuis_le_navigateur_est_refuse(tmp_path):
    """Régression : un fichier dont la 1re ligne est un message du navigateur n'est pas du XML."""
    texte, meta = tmp_path / "t.xml", tmp_path / "m.xml"
    texte.write_bytes(
        b"This XML file does not appear to have any style information associated with it.\n<quran/>\n"
    )
    meta.write_bytes(xml_metadonnees(METADONNEES_MINI).encode("utf-8"))

    with pytest.raises(CorpusInvalideError):
        lire_corpus(texte, meta, version_source="1.1")


@pytest.mark.parametrize("declaration", [
    b'<!DOCTYPE quran [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>',  # « milliard de rires » en miniature
    b'<!doctype quran [<!entity x SYSTEM "file:///etc/passwd">]>',                                  # entité externe, en minuscules
    b"<!ENTITY y 'z'>",
])
def test_rec28_un_fichier_avec_doctype_ou_entite_est_refuse_avant_l_analyse(tmp_path, declaration):
    """Un fichier Tanzil authentique n'a ni DOCTYPE ni ENTITY : on refuse tout XML qui en porte (attaques par entités)."""
    texte, meta = tmp_path / "t.xml", tmp_path / "m.xml"
    texte.write_bytes(b"<?xml version='1.0'?>\n" + declaration + b"\n<quran/>\n")
    meta.write_bytes(xml_metadonnees(METADONNEES_MINI).encode("utf-8"))

    with pytest.raises(CorpusInvalideError, match="DOCTYPE ou ENTITY"):
        lire_corpus(texte, meta, version_source="1.1")


def test_sourate_sans_metadonnees_refusee(tmp_path):
    texte, meta = tmp_path / "t.xml", tmp_path / "m.xml"
    texte.write_bytes(xml_texte(SOURATES_MINI).encode("utf-8"))
    meta.write_bytes(xml_metadonnees(METADONNEES_MINI[:2]).encode("utf-8"))  # sans la sourate 9

    with pytest.raises(CorpusInvalideError):
        lire_corpus(texte, meta)


# --- Import en base ---------------------------------------------------------


@pytest.mark.django_db
def test_import_cree_une_version_importee_avec_son_empreinte(fichiers, sans_controles):
    version = importer_corpus(lire_corpus(*fichiers))

    assert version.statut == VersionCorpus.Statut.IMPORTEE
    assert version.source == "Tanzil"
    assert version.version_source == "1.1"
    assert version.empreinte_sha256 == calculer_empreinte_sha256(fichiers[0])
    assert version.date_validation is None


@pytest.mark.django_db
def test_import_ecrit_sourates_et_versets(fichiers, sans_controles):
    version = importer_corpus(lire_corpus(*fichiers))

    assert version.sourates.count() == 3
    assert Verset.objects.filter(sourate__version=version).count() == 7
    sourate_2 = version.sourates.get(numero=2)
    assert sourate_2.basmala == "basmala-de-test"
    assert sourate_2.type_revelation == Sourate.TypeRevelation.MEDINOISE
    assert version.sourates.get(numero=1).basmala == ""
    assert version.sourates.get(numero=9).basmala == ""


@pytest.mark.django_db
def test_regle_absolue_1_texte_ecrit_en_base_octet_pour_octet(fichiers, sans_controles):
    version = importer_corpus(lire_corpus(*fichiers))

    versets = Verset.objects.filter(sourate__version=version, sourate__numero=2).order_by("numero")
    attendu = [TEXTE_ESPACE_FINAL, TEXTE_NFD, "texte-2-3"]
    assert [v.texte for v in versets] == attendu
    assert [v.texte.encode("utf-8") for v in versets] == [t.encode("utf-8") for t in attendu]


@pytest.mark.django_db
def test_meme_fichier_ne_peut_pas_etre_importe_deux_fois(fichiers, sans_controles):
    importer_corpus(lire_corpus(*fichiers))

    with pytest.raises(CorpusDejaImporteError):
        importer_corpus(lire_corpus(*fichiers))
    assert VersionCorpus.objects.count() == 1


@pytest.mark.django_db
def test_import_annule_si_un_controle_echoue(fichiers):
    def controle_qui_echoue(corpus):
        raise CorpusInvalideError("contrôle de test en échec")

    with pytest.raises(CorpusInvalideError):
        importer_corpus(lire_corpus(*fichiers), controler=controle_qui_echoue)

    assert VersionCorpus.objects.count() == 0
    assert Sourate.objects.count() == 0
    assert Verset.objects.count() == 0


@pytest.mark.django_db
def test_import_annule_si_la_base_refuse_une_donnee(tmp_path, sans_controles):
    """Tout ou rien : une sourate n° 115 viole la contrainte, rien ne doit rester en base."""
    texte, meta = tmp_path / "t.xml", tmp_path / "m.xml"
    sourates = SOURATES_MINI + [(115, ["texte-115-1"], "")]
    texte.write_bytes(xml_texte(sourates).encode("utf-8"))
    meta.write_bytes(xml_metadonnees(METADONNEES_MINI + [(115, 1, "Meccan", 114)]).encode("utf-8"))

    with pytest.raises(Exception):
        importer_corpus(lire_corpus(texte, meta))

    assert VersionCorpus.objects.count() == 0
    assert Sourate.objects.count() == 0
    assert Verset.objects.count() == 0


# --- Commande ---------------------------------------------------------------


@pytest.mark.django_db
def test_commande_import_corpus_de_bout_en_bout(fichiers, sans_controles):
    sortie = StringIO()

    call_command("import_corpus", str(fichiers[0]), str(fichiers[1]), stdout=sortie)

    assert VersionCorpus.objects.count() == 1
    assert Verset.objects.count() == 7
    assert "3 sourates" in sortie.getvalue()
    assert "7 versets" in sortie.getvalue()


@pytest.mark.django_db
def test_commande_dry_run_n_ecrit_rien(fichiers, sans_controles):
    sortie = StringIO()

    call_command("import_corpus", str(fichiers[0]), str(fichiers[1]), "--dry-run", stdout=sortie)

    assert VersionCorpus.objects.count() == 0
    assert Verset.objects.count() == 0
    assert "n'a été enregistré" in sortie.getvalue()


@pytest.mark.django_db
def test_commande_dry_run_lance_quand_meme_les_controles(fichiers, monkeypatch):
    def controle_qui_echoue(corpus):
        raise CorpusInvalideError("contrôle de test en échec")

    monkeypatch.setattr(services, "controler_corpus", controle_qui_echoue)

    with pytest.raises(CommandError, match="contrôle de test en échec"):
        call_command("import_corpus", str(fichiers[0]), str(fichiers[1]), "--dry-run")


@pytest.mark.django_db
def test_commande_fichier_introuvable(tmp_path):
    with pytest.raises(CommandError, match="introuvable"):
        call_command("import_corpus", str(tmp_path / "absent.xml"), str(tmp_path / "absent2.xml"))


@pytest.mark.django_db
def test_commande_signale_un_fichier_deja_importe(fichiers, sans_controles):
    call_command("import_corpus", str(fichiers[0]), str(fichiers[1]))

    with pytest.raises(CommandError, match="déjà"):
        call_command("import_corpus", str(fichiers[0]), str(fichiers[1]))


@pytest.mark.django_db
def test_commande_option_version_source(tmp_path, sans_controles):
    texte, meta = tmp_path / "t.xml", tmp_path / "m.xml"
    texte.write_bytes(xml_texte(SOURATES_MINI, entete="").encode("utf-8"))
    meta.write_bytes(xml_metadonnees(METADONNEES_MINI).encode("utf-8"))

    call_command("import_corpus", str(texte), str(meta), "--version-source", "9.9")

    assert VersionCorpus.objects.get().version_source == "9.9"


# --- Les vrais fichiers de data/corpus --------------------------------------

CHEMIN_TEXTE = settings.BASE_DIR / "data" / "corpus" / "quran-uthmani.xml"
CHEMIN_META = settings.BASE_DIR / "data" / "corpus" / "quran-data.xml"


@pytest.mark.django_db
@pytest.mark.skipif(
    not (CHEMIN_TEXTE.is_file() and CHEMIN_META.is_file()),
    reason="Fichiers Tanzil absents de data/corpus",
)
def test_rec30_import_des_vrais_fichiers_tanzil():
    """REC-30 : 114 sourates, 6 236 versets, empreinte conforme, texte identique au fichier."""
    version = importer_corpus(lire_corpus(CHEMIN_TEXTE, CHEMIN_META))

    assert version.sourates.count() == 114
    assert Verset.objects.filter(sourate__version=version).count() == 6236
    assert version.empreinte_sha256 == hashlib.sha256(CHEMIN_TEXTE.read_bytes()).hexdigest()
    # Basmala : absente des sourates 1 et 9, présente pour les 112 autres.
    assert version.sourates.exclude(basmala="").count() == 112
    assert set(version.sourates.filter(basmala="").values_list("numero", flat=True)) == {1, 9}
    # Contrôle d'aller-retour indépendant du parseur XML : on relit les textes bruts du fichier
    # avec une expression régulière et on les compare, dans l'ordre canonique, à ceux de la base.
    brut = CHEMIN_TEXTE.read_bytes().decode("utf-8")
    textes_fichier = re.findall(r'<aya index="\d+" text="([^"]*)"', brut)
    textes_base = list(
        Verset.objects.filter(sourate__version=version)
        .order_by("sourate__numero", "numero")
        .values_list("texte", flat=True)
    )
    assert textes_base == textes_fichier
