"""Découpage d'un verset trop long en plusieurs diapositives (§9.2, REC-33).

Règle absolue n°1 : le texte n'est JAMAIS modifié. Découper, c'est choisir où couper ; ce n'est ni
reformater, ni supprimer une espace, ni normaliser un caractère.
"""
import re


def segmenter_verset(texte, taille_max):
    """Découpe ``texte`` en segments d'au plus ``taille_max`` caractères, en coupant ENTRE DEUX MOTS."""
    if taille_max < 1:
        raise ValueError("La taille maximale d'un segment doit être d'au moins 1 caractère.")
    # Chaque « mot » garde ses espaces de fin : en les recollant, on retrouve exactement le texte.
    mots = re.findall(r"\S+\s*", texte)
    segments, courant = [], ""
    for mot in mots:
        if courant and len(courant) + len(mot) > taille_max:
            segments.append(courant)
            courant = ""
        courant += mot
    if courant:
        segments.append(courant)
    return segments
