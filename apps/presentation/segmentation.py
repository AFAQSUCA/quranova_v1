"""Découpage d'un verset trop long en plusieurs diapositives (§9.2, REC-33).

Règle absolue n°1 : le texte n'est JAMAIS modifié. Découper, c'est choisir où couper ; ce n'est ni
reformater, ni supprimer une espace, ni normaliser un caractère.
"""


def segmenter_verset(texte, taille_max):
    """Découpe ``texte`` en segments d'au plus ``taille_max`` caractères, en coupant ENTRE DEUX MOTS.

    TODO(human) : écrivez l'algorithme de découpage. Contrat (voir ``test_segmentation.py``) :
    - la concaténation des segments est STRICTEMENT identique à ``texte`` (aucun caractère perdu,
      ajouté, réordonné ni dupliqué) ;
    - on ne coupe jamais à l'intérieur d'un mot ; l'espace qui sépare deux mots reste à la FIN du
      segment qui précède (un segment commence donc toujours par un mot) ;
    - un segment ne dépasse pas ``taille_max`` caractères (espace finale comprise), SAUF s'il ne contient
      qu'un seul mot plus long que ``taille_max`` : on ne coupe pas un mot ;
    - un texte qui tient en une diapositive donne une liste d'un seul segment ;
    - aucun segment vide ; ``taille_max`` inférieur à 1 lève ``ValueError``.
    Indice : parcourez les mots (``re.findall(r"\\S+\\s*", texte)`` en garde les espaces de fin) et
    remplissez le segment courant tant que le mot suivant y tient.
    """
    raise NotImplementedError("TODO(human) : segmentation d'un verset (voir la docstring)")
