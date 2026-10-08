# Chapitre 6 — Importer le corpus coranique

> **Étape du plan :** 0.4 · **Durée :** 3 heures · **Commit de référence :** `8139285` · **Résultat :** la commande `python manage.py import_corpus` charge 114 sourates et 6 236 versets, sans modifier une seule lettre.

## Objectif

Lire les fichiers du projet **Tanzil**, calculer leur empreinte SHA-256, et créer une `VersionCorpus` au statut « importée », avec ses sourates et ses versets. L'import est **tout ou rien**. Les **contrôles automatiques du §12.2** sont à écrire par vous (`TODO(human)`).

## Étape A — Se procurer les fichiers Tanzil (à la main)

> **Règle absolue n°1** : le texte coranique est **téléchargé** depuis le site officiel, jamais tapé, copié-collé ou corrigé.

1. Allez sur https://tanzil.net/download : texte **Uthmani**, format **XML**, options par défaut. Enregistrez le fichier sous `data\corpus\quran-uthmani.xml`.
2. Téléchargez aussi le fichier de métadonnées `quran-data.xml` (noms des sourates, nombre de versets), disponible sur le site Tanzil (page de documentation des métadonnées), et enregistrez-le dans `data\corpus\`.
3. Utilisez **« Enregistrer le lien sous… »** ou un téléchargement direct. **Ne copiez pas** le contenu d'une page du navigateur.

> **Piège rencontré :** un fichier copié depuis la page du navigateur commence par la phrase *« This XML file does not appear to have any style information… »*, qui n'est pas du XML. Vérifiez que la première ligne commence par `<?xml` :
>
> ```powershell
> Get-Content .\data\corpus\quran-data.xml -TotalCount 2
> ```

## Étape B — Empêcher Git de modifier ces fichiers

Sous Windows, Git peut convertir les fins de ligne. L'empreinte SHA-256 ne correspondrait alors plus au fichier d'origine. Créez `.gitattributes` à la racine :

**Fichier `.gitattributes`**

```text
data/corpus/* -text
```

## Étape C — Noter l'empreinte et la version

```powershell
Get-FileHash .\data\corpus\quran-uthmani.xml -Algorithm SHA256
Get-FileHash .\data\corpus\quran-data.xml -Algorithm SHA256
```

Notez les résultats, avec la **version Tanzil** (indiquée dans l'en-tête du fichier texte, par exemple *« Version 1.1 »*) et la **date de téléchargement**, dans le tableau de `data\corpus\LISEZMOI.md`.

```powershell
git add .gitattributes data\corpus
git commit -m "Corpus : fichiers Tanzil téléchargés tels quels et .gitattributes"
```

## Étape D — Les tests d'abord

Les tests fabriquent de **petits fichiers XML neutres** dans un dossier temporaire. Un seul test lit les vrais fichiers de `data\corpus`.

**Fichier `apps\coran\tests\test_import.py`**

```python
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
```

**Fichier `apps\coran\tests\test_controles_corpus.py`**

```python
"""Tests des contrôles automatiques du corpus (§12.2, point 3 ; REC-30).

Chaque test part d'un corpus CONFORME fabriqué en mémoire (114 sourates,
6 236 versets, textes neutres), puis le dégrade d'une seule façon.
"""
from dataclasses import replace

import pytest

from apps.coran import services
from apps.coran.exceptions import CorpusInvalideError
from apps.coran.importation import CorpusLu, SourateLue, VersetLu
from apps.coran.models import Sourate

# 113 sourates de 55 versets + 1 sourate de 21 versets = 6 236 versets.
NOMBRES_DE_VERSETS = [55] * 113 + [21]
assert sum(NOMBRES_DE_VERSETS) == 6236


def _sourate(numero, nombre_declare, numeros_versets, textes=None):
    textes = textes or [f"texte-{numero}-{n}" for n in numeros_versets]
    return SourateLue(
        numero=numero,
        nom_arabe=f"nom-arabe-{numero}",
        nom_translitteration=f"Translitteration-{numero}",
        nombre_versets=nombre_declare,
        type_revelation=Sourate.TypeRevelation.MECQUOISE,
        ordre_revelation=numero,
        basmala="",
        versets=tuple(VersetLu(n, t) for n, t in zip(numeros_versets, textes)),
    )


def corpus_conforme():
    sourates = tuple(
        _sourate(numero, nb, range(1, nb + 1))
        for numero, nb in enumerate(NOMBRES_DE_VERSETS, start=1)
    )
    return CorpusLu(
        version_source="1.1",
        nom_fichier="texte.xml",
        empreinte_sha256="0" * 64,
        sourates=sourates,
    )


def avec_sourate(corpus, indice, sourate):
    """Renvoie une copie du corpus où la sourate d'indice donné est remplacée."""
    sourates = list(corpus.sourates)
    sourates[indice] = sourate
    return replace(corpus, sourates=tuple(sourates))


def test_rec30_corpus_conforme_accepte():
    services.controler_corpus(corpus_conforme())  # ne doit rien lever


def test_rec30_113_sourates_refuse():
    corpus = corpus_conforme()
    corpus = replace(corpus, sourates=corpus.sourates[:-1])

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


def test_rec30_115_sourates_refuse():
    corpus = corpus_conforme()
    corpus = replace(corpus, sourates=corpus.sourates + (_sourate(115, 1, [1]),))

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


def test_rec30_numerotation_des_sourates_non_continue_refusee():
    """114 sourates, mais la n° 114 est remplacée par une n° 115 : il manque la 114."""
    corpus = corpus_conforme()
    derniere = corpus.sourates[-1]
    corpus = avec_sourate(corpus, -1, replace(derniere, numero=115))

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


def test_rec30_6235_versets_refuse():
    corpus = corpus_conforme()
    corpus = avec_sourate(corpus, -1, _sourate(114, 20, range(1, 21)))  # 21 -> 20 versets

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


def test_rec30_6237_versets_refuse():
    corpus = corpus_conforme()
    corpus = avec_sourate(corpus, -1, _sourate(114, 22, range(1, 23)))  # 21 -> 22 versets

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


def test_rec30_nombre_de_versets_different_des_metadonnees_refuse():
    """Le total reste 6 236, mais un verset est passé de la sourate 5 à la sourate 6."""
    corpus = corpus_conforme()
    corpus = avec_sourate(corpus, 4, _sourate(5, 55, range(1, 55)))  # lit 54, déclare 55
    corpus = avec_sourate(corpus, 5, _sourate(6, 55, range(1, 57)))  # lit 56, déclare 55

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


def test_rec30_numerotation_des_versets_discontinue_refusee():
    """Le nombre de versets est correct (55), mais la numérotation saute le n° 10."""
    corpus = corpus_conforme()
    numeros = list(range(1, 10)) + list(range(11, 57))
    assert len(numeros) == 55
    corpus = avec_sourate(corpus, 2, _sourate(3, 55, numeros))

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


def test_rec30_numerotation_des_versets_dupliquee_refusee():
    corpus = corpus_conforme()
    numeros = list(range(1, 55)) + [54]  # deux versets n° 54
    corpus = avec_sourate(corpus, 2, _sourate(3, 55, numeros))

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)


@pytest.mark.parametrize("texte", ["", "   "])
def test_rec30_verset_vide_refuse(texte):
    corpus = corpus_conforme()
    textes = [f"texte-3-{n}" for n in range(1, 56)]
    textes[9] = texte
    corpus = avec_sourate(corpus, 2, _sourate(3, 55, range(1, 56), textes))

    with pytest.raises(CorpusInvalideError):
        services.controler_corpus(corpus)
```

## Étape E — Le code de l'import

D'abord, deux exceptions (fichier complet à ce stade) :

**Fichier `apps\coran\exceptions.py`**

```python
"""Exceptions de l'application coran."""


class CorpusImmuableError(Exception):
    """Une écriture est refusée parce qu'elle violerait l'immuabilité du corpus (RM-27, §12.3)."""


class CorpusInvalideError(Exception):
    """Le corpus lu n'a pas la structure attendue ou échoue aux contrôles du §12.2."""


class CorpusDejaImporteError(Exception):
    """Un fichier de même empreinte SHA-256 a déjà été importé."""
```

Le module d'import, séparé de `services.py` parce qu'il utilise les modèles, alors que les modèles importent déjà `services.py` (importer les modèles depuis `services.py` créerait un import circulaire) :

**Fichier `apps\coran\importation.py`**

```python
"""Import du corpus Tanzil : lecture sans transformation, puis écriture en base (§12.2).

Ce module est séparé de services.py parce qu'il utilise les modèles, alors que les
modèles importent déjà services.py (importer les modèles depuis services.py créerait
un import circulaire).

Règle absolue n°1 : le texte coranique est repris tel quel du fichier Tanzil, sans
aucune transformation (ni normalisation Unicode, ni suppression d'espaces ou de signes).
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction

from apps.coran import services
from apps.coran.exceptions import CorpusDejaImporteError, CorpusInvalideError
from apps.coran.models import Sourate, Verset, VersionCorpus

# Vocabulaire Tanzil -> vocabulaire du projet.
TYPES_REVELATION = {
    "Meccan": Sourate.TypeRevelation.MECQUOISE,
    "Medinan": Sourate.TypeRevelation.MEDINOISE,
}


@dataclass(frozen=True)
class VersetLu:
    numero: int
    texte: str


@dataclass(frozen=True)
class SourateLue:
    numero: int
    nom_arabe: str
    nom_translitteration: str
    nombre_versets: int  # valeur DÉCLARÉE par les métadonnées, pas le nombre de versets lus
    type_revelation: str
    ordre_revelation: int
    basmala: str
    versets: tuple


@dataclass(frozen=True)
class CorpusLu:
    version_source: str
    nom_fichier: str
    empreinte_sha256: str
    sourates: tuple


def calculer_empreinte_sha256(chemin):
    """Empreinte SHA-256 des octets du fichier, lus par blocs (le fichier n'est jamais modifié)."""
    empreinte = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(65536), b""):
            empreinte.update(bloc)
    return empreinte.hexdigest()


def _entier(valeur, description):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        raise CorpusInvalideError(f"{description} : « {valeur} » n'est pas un entier.") from None


def _lire_xml(octets, description):
    try:
        return ET.fromstring(octets)
    except ET.ParseError as erreur:
        raise CorpusInvalideError(
            f"{description} n'est pas un XML valide ({erreur}). "
            "Le fichier doit être téléchargé tel quel depuis tanzil.net, pas copié depuis une page."
        ) from erreur


def _lire_version_source(octets):
    """Cherche « Version X.Y » dans le commentaire d'en-tête du fichier Tanzil."""
    commentaire = re.search(r"<!--(.*?)-->", octets.decode("utf-8", errors="replace"), re.DOTALL)
    version = re.search(r"Version\s+(\d+(?:\.\d+)*)", commentaire.group(1)) if commentaire else None
    if version is None:
        raise CorpusInvalideError(
            "Version Tanzil introuvable dans l'en-tête du fichier : indiquez-la avec --version-source."
        )
    return version.group(1)


def _lire_metadonnees(chemin_metadonnees):
    racine = _lire_xml(Path(chemin_metadonnees).read_bytes(), "Le fichier de métadonnées")
    liste = racine.find("suras")
    if liste is None:
        raise CorpusInvalideError("Le fichier de métadonnées ne contient pas de balise <suras>.")
    return {
        _entier(sura.get("index"), "Métadonnées : numéro de sourate"): sura
        for sura in liste.findall("sura")
    }


def lire_corpus(chemin_texte, chemin_metadonnees, version_source=None):
    """Lit les deux fichiers Tanzil et renvoie un CorpusLu, sans rien écrire en base."""
    chemin_texte = Path(chemin_texte)
    octets = chemin_texte.read_bytes()
    racine = _lire_xml(octets, f"Le fichier texte « {chemin_texte.name} »")
    metadonnees = _lire_metadonnees(chemin_metadonnees)

    sourates = []
    for sura in racine.findall("sura"):
        numero = _entier(sura.get("index"), "Numéro de sourate")
        meta = metadonnees.get(numero)
        if meta is None:
            raise CorpusInvalideError(f"Métadonnées absentes pour la sourate {numero}.")
        type_revelation = TYPES_REVELATION.get(meta.get("type"))
        if type_revelation is None:
            raise CorpusInvalideError(
                f"Sourate {numero} : type de révélation inconnu « {meta.get('type')} »."
            )
        ayas = sura.findall("aya")
        versets = []
        for aya in ayas:
            texte = aya.get("text")
            if texte is None:
                raise CorpusInvalideError(f"Sourate {numero} : verset sans attribut « text ».")
            versets.append(VersetLu(_entier(aya.get("index"), f"Sourate {numero} : numéro de verset"), texte))
        sourates.append(
            SourateLue(
                numero=numero,
                nom_arabe=sura.get("name") or "",
                nom_translitteration=meta.get("tname") or "",
                nombre_versets=_entier(meta.get("ayas"), f"Sourate {numero} : nombre de versets"),
                type_revelation=type_revelation,
                ordre_revelation=_entier(meta.get("order"), f"Sourate {numero} : ordre de révélation"),
                # La basmala de tête est portée par le verset 1 (attribut « bismillah »).
                basmala=(ayas[0].get("bismillah") or "") if ayas else "",
                versets=tuple(versets),
            )
        )

    return CorpusLu(
        version_source=version_source or _lire_version_source(octets),
        nom_fichier=chemin_texte.name,
        empreinte_sha256=hashlib.sha256(octets).hexdigest(),
        sourates=tuple(sourates),
    )


def importer_corpus(corpus, controler=None):
    """Écrit le corpus en base dans une VersionCorpus au statut « importée ».

    Tout ou rien : les contrôles du §12.2 s'exécutent AVANT toute écriture, et les
    écritures se font dans une transaction ; en cas d'erreur, rien ne subsiste.
    """
    controler = controler or services.controler_corpus

    existante = VersionCorpus.objects.filter(empreinte_sha256=corpus.empreinte_sha256).first()
    if existante is not None:
        raise CorpusDejaImporteError(
            f"Ce fichier a déjà été importé (version n° {existante.pk}, statut « {existante.get_statut_display()} »)."
        )

    controler(corpus)

    with transaction.atomic():
        version = VersionCorpus.objects.create(
            version_source=corpus.version_source,
            nom_fichier=corpus.nom_fichier,
            empreinte_sha256=corpus.empreinte_sha256,
            statut=VersionCorpus.Statut.IMPORTEE,
        )
        # bulk_create renvoie les sourates avec leur identifiant (PostgreSQL), dans le même ordre.
        sourates = Sourate.objects.bulk_create(
            [
                Sourate(
                    version=version,
                    numero=s.numero,
                    nom_arabe=s.nom_arabe,
                    nom_translitteration=s.nom_translitteration,
                    nombre_versets=s.nombre_versets,
                    type_revelation=s.type_revelation,
                    ordre_revelation=s.ordre_revelation,
                    basmala=s.basmala,
                )
                for s in corpus.sourates
            ]
        )
        Verset.objects.bulk_create(
            [
                Verset(sourate=sourate, numero=verset.numero, texte=verset.texte)
                for sourate, lue in zip(sourates, corpus.sourates)
                for verset in lue.versets
            ],
            batch_size=1000,
        )
    return version
```

La commande Django :

```powershell
New-Item -ItemType Directory apps\coran\management\commands | Out-Null
New-Item -ItemType File apps\coran\management\__init__.py, apps\coran\management\commands\__init__.py | Out-Null
```

**Fichier `apps\coran\management\commands\import_corpus.py`**

```python
"""Commande : importe le corpus coranique depuis les fichiers Tanzil (§12.2)."""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.coran.exceptions import CorpusDejaImporteError, CorpusInvalideError
from apps.coran.importation import importer_corpus, lire_corpus

DOSSIER_CORPUS = Path(settings.BASE_DIR) / "data" / "corpus"


class Command(BaseCommand):
    help = (
        "Importe le corpus coranique Tanzil en base, dans une version « importée ». "
        "Le texte est repris tel quel, sans aucune transformation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "fichier_texte",
            nargs="?",
            default=str(DOSSIER_CORPUS / "quran-uthmani.xml"),
            help="Fichier texte Tanzil (défaut : data/corpus/quran-uthmani.xml).",
        )
        parser.add_argument(
            "fichier_metadonnees",
            nargs="?",
            default=str(DOSSIER_CORPUS / "quran-data.xml"),
            help="Fichier de métadonnées Tanzil (défaut : data/corpus/quran-data.xml).",
        )
        parser.add_argument(
            "--version-source",
            help="Version Tanzil (sinon lue dans l'en-tête du fichier texte).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lance la lecture et les contrôles, puis annule sans rien enregistrer.",
        )

    def handle(self, *args, **options):
        for chemin in (options["fichier_texte"], options["fichier_metadonnees"]):
            if not Path(chemin).is_file():
                raise CommandError(f"Fichier introuvable : {chemin}")

        try:
            corpus = lire_corpus(
                options["fichier_texte"],
                options["fichier_metadonnees"],
                version_source=options["version_source"],
            )
            with transaction.atomic():
                version = importer_corpus(corpus)
                if options["dry_run"]:
                    transaction.set_rollback(True)
        except (CorpusInvalideError, CorpusDejaImporteError, IntegrityError) as erreur:
            raise CommandError(str(erreur)) from erreur

        nombre_versets = sum(len(s.versets) for s in corpus.sourates)
        resume = (
            f"{len(corpus.sourates)} sourates, {nombre_versets} versets, "
            f"version Tanzil {corpus.version_source}, empreinte SHA-256 {corpus.empreinte_sha256}."
        )
        if options["dry_run"]:
            self.stdout.write(f"Simulation réussie : {resume} Rien n'a été enregistré.")
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Version n° {version.pk} importée (statut « importée ») : {resume}")
            )
```

Enfin, `services.py` reçoit la fonction `controler_corpus`, **vide** pour l'instant (c'est votre `TODO(human)`). Fichier complet à ce stade :

**Fichier `apps\coran\services.py`**

```python
"""Règles métier du corpus (cf. §12.3 : versionnement et immutabilité).

Ces fonctions ne touchent pas à la base de données : elles reçoivent des
valeurs et lèvent ``CorpusImmuableError`` si l'opération est interdite.
Les modèles se chargent de lire l'état réel en base et d'appeler ces fonctions.
"""
from apps.coran.exceptions import CorpusImmuableError  # noqa: F401  (à utiliser ci-dessous)


def verifier_transition_statut(ancien_statut, nouveau_statut, date_validation):
    """Refuse un changement de statut d'une version du corpus qui n'est pas autorisé.

    Statuts possibles : « importee », « validee », « active », « retiree ».

    TODO(human) : écrivez la règle.
    - Quelles transitions sont permises (par exemple importee -> validee) ?
    - Peut-on revenir en arrière (validee -> importee) ? Pourquoi serait-ce dangereux ?
    - Une version peut-elle devenir « validee » sans date de validation (PV du référent) ?
    Levez CorpusImmuableError avec un message explicite si la transition est refusée.
    """


def verifier_ecriture_autorisee(statut_version):
    """Refuse toute écriture sur le contenu d'une version dont le statut est figé.

    « Écriture » = création, modification ou suppression d'une sourate, d'un verset,
    ou modification des champs d'identité de la version (empreinte, fichier...).

    TODO(human) : écrivez la règle.
    - Pour quels statuts le contenu est-il figé ?
    Levez CorpusImmuableError avec un message explicite si l'écriture est refusée.
    """


def controler_corpus(corpus):
    """Contrôles automatiques du §12.2, point 3, appliqués AVANT toute écriture en base.

    ``corpus`` est un ``CorpusLu`` (cf. importation.py) : ``corpus.sourates`` est un tuple de
    ``SourateLue`` ; chacune porte ``numero``, ``nombre_versets`` (valeur déclarée par les
    métadonnées Tanzil) et ``versets`` (tuple de ``VersetLu`` avec ``numero`` et ``texte``).

    TODO(human) : écrivez les contrôles, en levant CorpusInvalideError avec un message
    explicite (quelle sourate, quel verset, quelle valeur attendue) :
    - exactement 114 sourates, numérotées de 1 à 114 sans trou ni doublon ;
    - exactement 6 236 versets au total ;
    - pour chaque sourate, le nombre de versets lus est égal à ``nombre_versets`` ;
    - dans chaque sourate, la numérotation des versets est continue (1, 2, 3, ...) ;
    - aucun verset vide (texte composé uniquement d'espaces compris).
    Vous choisissez : s'arrêter à la première erreur, ou les collecter toutes dans un seul message.
    """
```

## Étape F — Constater l'état « rouge »

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
pytest -q
```

Attendu : `No changes detected` (aucun champ n'a changé) et **49 failed, 84 passed**. Les 49 échecs sont les 39 de la garde d'immuabilité (si vous n'avez pas encore fait le chapitre 4) et les 10 de `test_controles_corpus.py`.

## Étape G — À vous : écrire `controler_corpus` (`TODO(human)`)

La fonction reçoit le corpus **lu en mémoire**, avant toute écriture en base. Elle lève `CorpusInvalideError` avec un message explicite si :

- il n'y a pas exactement **114 sourates**, numérotées de 1 à 114 sans trou ;
- il n'y a pas exactement **6 236 versets** ;
- le nombre de versets lus d'une sourate diffère de `nombre_versets` (les métadonnées) ;
- la numérotation des versets d'une sourate n'est pas continue (1, 2, 3...) ;
- un verset est vide (espaces compris).

Vous choisissez de vous arrêter à la première erreur ou de les collecter toutes dans un seul message.

<details>
<summary>Solution (n'ouvrez qu'après avoir essayé)</summary>

```python
# Dans apps/coran/services.py, complétez l'import existant en haut du fichier :
#   from apps.coran.exceptions import CorpusImmuableError, CorpusInvalideError
# (au chapitre 7, ReferenceInvalideError s'y ajoutera aussi)
# puis remplacez la fonction vide controler_corpus par :

NOMBRE_DE_SOURATES = 114
NOMBRE_DE_VERSETS = 6236


def controler_corpus(corpus):
    """Contrôles automatiques du §12.2, point 3 : collecte toutes les erreurs, puis les signale."""
    erreurs = []

    numeros = [s.numero for s in corpus.sourates]
    if numeros != list(range(1, NOMBRE_DE_SOURATES + 1)):
        erreurs.append(
            f"{len(numeros)} sourates lues ; attendu : les sourates 1 à {NOMBRE_DE_SOURATES}, sans trou ni doublon"
        )

    total = sum(len(s.versets) for s in corpus.sourates)
    if total != NOMBRE_DE_VERSETS:
        erreurs.append(f"{total} versets lus ; attendu : {NOMBRE_DE_VERSETS}")

    for sourate in corpus.sourates:
        lus = len(sourate.versets)
        if lus != sourate.nombre_versets:
            erreurs.append(
                f"sourate {sourate.numero} : {lus} versets lus, {sourate.nombre_versets} annoncés par les métadonnées"
            )
        if [v.numero for v in sourate.versets] != list(range(1, lus + 1)):
            erreurs.append(f"sourate {sourate.numero} : numérotation des versets discontinue ou dupliquée")
        for verset in sourate.versets:
            if not verset.texte.strip():
                erreurs.append(f"verset {sourate.numero}:{verset.numero} : texte vide")

    if erreurs:
        raise CorpusInvalideError("Corpus invalide : " + " ; ".join(erreurs) + ".")
```

</details>

```powershell
pytest apps\coran\tests\test_controles_corpus.py
pytest
```

Attendu (avec la garde d'immuabilité du chapitre 4 aussi) : **133 passed**.

## Étape H — Importer pour de vrai

```powershell
python manage.py migrate
python manage.py import_corpus --dry-run
python manage.py import_corpus
python manage.py import_corpus
```

Attendu :

1. `--dry-run` : `Simulation réussie : 114 sourates, 6236 versets ... Rien n'a été enregistré.`
2. L'import réel : `Version n° ... importée (statut « importée ») : 114 sourates, 6236 versets ...`
3. Le deuxième import réel est **refusé** : `Ce fichier a déjà été importé (version n° ..., statut « Importée »).`

(Le numéro de version peut être supérieur à 1 : le `--dry-run` consomme un numéro de séquence, même annulé.)

```powershell
git add apps
git commit -m "Corpus : commande import_corpus, tests et contrôles du §12.2"
```

## Pour comprendre

- **Tout ou rien** : les contrôles s'exécutent **avant** l'écriture, et l'écriture se fait dans une transaction. Une version à moitié importée, avec des sourates sans versets, serait pire qu'aucun import.
- **Aucune transformation** : le parseur XML lit les attributs ; on vérifie dans le test sur les vrais fichiers, **sans le parseur** (une expression régulière sur les octets du fichier), que les 6 236 textes de la base sont identiques à ceux du fichier.
- **Contrôles injectables** : `importer_corpus(corpus, controler=...)`. Les petits corpus de test n'ont pas 114 sourates : les tests de l'import neutralisent vos contrôles, qui ont leurs propres tests.
- **`bulk_create`** contourne `save()` (donc la garde du chapitre 4). C'est acceptable ici : une version « importée » reste modifiable. Le futur déclencheur PostgreSQL fermera ce contournement pour les versions validées.
- **Basmala** : portée par l'attribut `bismillah` du verset 1 des sourates 2 à 114 (sauf la 9). Elle est copiée dans `Sourate.basmala` ; la numérotation des versets reste intacte (§12.4).

## Questions de compréhension

1. Pourquoi veut-on que l'import soit **tout ou rien** ?
2. Dans le test d'aller-retour, pourquoi relit-on les textes avec une expression régulière plutôt qu'avec le même parseur XML que l'import ?
3. Pourquoi le corpus est-il importé avant d'être validé, et pourquoi la version reste-t-elle « importée » ?

<details>
<summary>Réponses</summary>

1. Une version partielle (sourates sans versets, nombres incohérents) serait pire qu'aucune : un concours pourrait s'appuyer dessus. Tout ou rien garantit qu'une version existante est complète.
2. Si le parseur modifiait un texte (par exemple en remplaçant une tabulation par une espace), l'import et le test se tromperaient de la même façon et le test ne verrait rien. Une lecture indépendante des octets détecte le problème.
3. La validation est un acte humain (le référent coranique compare un échantillon au Mushaf de Médine et signe un procès-verbal). Le logiciel ne peut pas valider seul : il prépare une version « importée », que le référent valide ensuite (§12.2, points 5 à 7).
</details>

## Journal d'apprentissage

Notez : ce qu'est une empreinte SHA-256 et à quoi elle sert ici ; pourquoi un fichier copié depuis un navigateur est refusé.
