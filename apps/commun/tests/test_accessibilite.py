"""Garde-fous d'accessibilité (§18.2, REC-34) vérifiables sans navigateur : gabarits et feuilles de style.

L'audit complet (axe-core, cibles tactiles, focus, débordement à 320 px) se joue dans un vrai navigateur :
``scripts/audit-accessibilite.mjs`` (voir docs/recette/accessibilite.md).
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[3]
GABARITS = sorted((RACINE / "templates").glob("*.html"))


@pytest.mark.parametrize("gabarit", GABARITS, ids=lambda p: p.name)
def test_chaque_page_declare_sa_langue_et_un_titre(gabarit):
    if gabarit.name.startswith("_"):
        pytest.skip("fragment inclus dans une page")
    contenu = gabarit.read_text(encoding="utf-8")
    assert '<html lang="fr">' in contenu
    assert re.search(r"<title>[^<]+</title>", contenu)


@pytest.mark.parametrize("gabarit", GABARITS, ids=lambda p: p.name)
def test_aucune_page_n_interdit_le_zoom(gabarit):
    """WCAG 1.4.4 : agrandissement à 200 % — jamais ``user-scalable=no`` ni ``maximum-scale``."""
    contenu = gabarit.read_text(encoding="utf-8")
    assert "user-scalable" not in contenu and "maximum-scale" not in contenu


def test_le_proces_verbal_declare_sa_langue():
    assert '<html lang="fr">' in (RACINE / "templates" / "documents" / "pv.html").read_text(encoding="utf-8")


def test_la_scene_conserve_le_balayage_meme_en_mode_reduction_des_animations():
    """§18.2 : la réduction des animations vaut pour les écrans individuels ; l'écran scène garde le balayage de RM-12."""
    css = (RACINE / "frontend" / "src" / "scene" / "style.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" not in css
    assert "translateX(100%)" in css  # le balayage existe bien


def test_l_ecran_de_tirage_coupe_son_animation_en_mode_reduction_des_animations():
    css = (RACINE / "frontend" / "src" / "tirage" / "style.css").read_text(encoding="utf-8")
    ligne = next(l for l in css.splitlines() if "prefers-reduced-motion" in l)
    assert "animation: none" in ligne


def test_aucune_animation_ne_clignote_plus_de_trois_fois_par_seconde():
    """WCAG 2.3.1 : les seules animations en boucle sont des rotations d'une seconde (1 Hz), jamais un clignotement."""
    for css in (RACINE / "frontend" / "src").glob("*/style.css"):
        for durees in re.findall(r"animation:[^;]*?([\d.]+)s[^;]*infinite", css.read_text(encoding="utf-8")):
            assert float(durees) >= 0.34, f"{css}: animation infinie trop rapide ({durees} s)"
