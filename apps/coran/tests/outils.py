"""Fonctions utilitaires partagées par les tests de l'application coran."""
import itertools

from apps.coran.models import Sourate, Verset, VersionCorpus

_compteur_versions = itertools.count(1)
_compteur_sourates = itertools.count(1)
_compteur_versets = itertools.count(1)


def creer_version(**champs):
    """Crée une version de test avec une empreinte SHA-256 unique et valide."""
    n = next(_compteur_versions)
    valeurs = {
        "version_source": "1.0",
        "nom_fichier": "quran-uthmani.xml",
        "empreinte_sha256": f"{n:064x}",
    }
    valeurs.update(champs)
    return VersionCorpus.objects.create(**valeurs)


def creer_sourate(version=None, **champs):
    """Crée une sourate de test ; numéro et ordre de révélation sont uniques par défaut."""
    n = next(_compteur_sourates)
    valeurs = {
        "version": version or creer_version(),
        "numero": n,
        "nom_arabe": f"nom-arabe-de-test-{n}",
        "nom_translitteration": f"Sourate-test-{n}",
        "nombre_versets": 7,
        "type_revelation": Sourate.TypeRevelation.MECQUOISE,
        "ordre_revelation": n,
    }
    valeurs.update(champs)
    return Sourate.objects.create(**valeurs)


def creer_verset(sourate=None, **champs):
    """Crée un verset de test ; le numéro est unique par défaut et le texte est neutre."""
    n = next(_compteur_versets)
    valeurs = {
        "sourate": sourate or creer_sourate(),
        "numero": n,
        "texte": f"texte-de-test-{n}",
    }
    valeurs.update(champs)
    return Verset.objects.create(**valeurs)
