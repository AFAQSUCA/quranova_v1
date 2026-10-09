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
