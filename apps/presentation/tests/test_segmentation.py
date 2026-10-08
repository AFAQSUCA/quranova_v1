"""Tests de la segmentation d'un verset (§9.2, REC-33) — algorithme à écrire par vous.

Les textes de test sont NEUTRES (jamais un verset, règle n°1) : des mots inventés, et des suites de lettres
arabes avec signes diacritiques pour vérifier que les caractères Unicode ne sont ni normalisés ni cassés.
"""
import pytest

from apps.presentation.segmentation import segmenter_verset

MOTS_ARABES = ["ابتَ", "ثجحْ", "خدذُ", "رزسِ"]


def texte_neutre(n_mots, mot="mot"):
    return " ".join(f"{mot}{i}" for i in range(n_mots))


def texte_arabe(n_mots):
    return " ".join(MOTS_ARABES[i % 4] + MOTS_ARABES[(i + 1) % 4] for i in range(n_mots))


@pytest.mark.parametrize("texte", [texte_neutre(1), texte_neutre(40), texte_arabe(25), "a b c d e f g"])
@pytest.mark.parametrize("taille", [1, 5, 12, 30, 80, 500])
def test_rec33_la_concatenation_des_segments_est_identique_au_texte(texte, taille):
    assert "".join(segmenter_verset(texte, taille)) == texte


@pytest.mark.parametrize("texte", [texte_neutre(40), texte_arabe(25)])
@pytest.mark.parametrize("taille", [10, 30, 80])
def test_on_ne_coupe_jamais_a_l_interieur_d_un_mot(texte, taille):
    segments = segmenter_verset(texte, taille)

    mots_d_origine = texte.split()
    mots_des_segments = [mot for segment in segments for mot in segment.split()]
    assert mots_des_segments == mots_d_origine
    for segment in segments:
        assert not segment[0].isspace()  # un segment commence par un mot
    for segment in segments[:-1]:
        assert segment[-1] == " "  # l'espace de séparation reste à la fin du segment qui précède


@pytest.mark.parametrize("taille", [10, 30, 80])
def test_un_segment_ne_depasse_pas_la_taille_maximale(taille):
    for segment in segmenter_verset(texte_neutre(60), taille):
        assert len(segment) <= taille


def test_un_mot_plus_long_que_la_taille_n_est_pas_coupe():
    segments = segmenter_verset("court immensementlong fin", 8)

    assert segments == ["court ", "immensementlong ", "fin"]


def test_un_texte_court_donne_un_seul_segment():
    assert segmenter_verset("deux mots", 100) == ["deux mots"]


def test_exemple_simple_avec_l_espace_a_la_fin_du_segment():
    assert segmenter_verset("aaaa bbbb", 5) == ["aaaa ", "bbbb"]


def test_aucun_segment_vide():
    for segment in segmenter_verset(texte_neutre(30), 15):
        assert segment != ""


def test_les_caracteres_unicode_ne_sont_pas_normalises():
    texte = texte_arabe(10)

    assert "".join(segmenter_verset(texte, 12)) == texte
    assert all(c in texte for c in "".join(segmenter_verset(texte, 12)))


def test_le_resultat_est_deterministe():
    assert segmenter_verset(texte_neutre(50), 20) == segmenter_verset(texte_neutre(50), 20)


@pytest.mark.parametrize("taille", [0, -3])
def test_une_taille_invalide_est_refusee(taille):
    with pytest.raises(ValueError):
        segmenter_verset("texte", taille)
