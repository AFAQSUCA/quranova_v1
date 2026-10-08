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
