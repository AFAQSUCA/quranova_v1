"""Résolution d'un passage coranique en liste de versets (§8.4, §12.4).

Ce module est séparé de services.py parce qu'il lit la base de données, alors que
les modèles importent déjà services.py (import circulaire sinon). Les RÈGLES
(validation des références, traversée de sourates) restent dans services.py.

Règle absolue n°1 : les textes viennent uniquement du corpus importé, jamais d'une
reconstruction par concaténation (§8.4).
"""
from django.db.models import Q

from apps.coran import services
from apps.coran.exceptions import CorpusInvalideError, ReferenceInvalideError
from apps.coran.models import Sourate, Verset


def resoudre_passage(debut, fin, version):
    """Renvoie la liste ordonnée des ``Verset`` de ``debut`` à ``fin`` (bornes incluses).

    ``debut`` et ``fin`` sont des couples (sourate, verset), par exemple (2, 142) et (2, 150).
    ``version`` est la ``VersionCorpus`` dans laquelle on cherche (RM-27).
    Lève ``ReferenceInvalideError`` si une référence n'existe pas ou si la fin précède le début.
    """
    plan = dict(
        Sourate.objects.filter(version=version)
        .order_by("numero")
        .values_list("numero", "nombre_versets")
    )
    if not plan:
        raise ReferenceInvalideError(
            f"La version du corpus n° {version.pk} ne contient aucune sourate."
        )

    services.verifier_reference(plan, debut)
    services.verifier_reference(plan, fin)
    debut, fin = tuple(debut), tuple(fin)
    services.verifier_ordre_passage(debut, fin)

    references = services.references_du_passage(plan, debut, fin)
    _verifier_contrat(references, debut, fin)

    # Une seule requête : on regroupe les références par sourate en intervalles.
    bornes = {}
    for sourate, verset in references:
        bas, haut = bornes.get(sourate, (verset, verset))
        bornes[sourate] = (min(bas, verset), max(haut, verset))
    filtre = Q()
    for sourate, (bas, haut) in bornes.items():
        filtre |= Q(sourate__numero=sourate, numero__gte=bas, numero__lte=haut)
    versets = Verset.objects.filter(filtre, sourate__version=version).select_related("sourate")
    par_reference = {(v.sourate.numero, v.numero): v for v in versets}

    resultat = []
    for sourate, verset in references:
        if (sourate, verset) not in par_reference:
            raise CorpusInvalideError(
                f"Corpus incohérent : le verset {sourate}:{verset} est annoncé par les "
                f"métadonnées mais absent de la version n° {version.pk}."
            )
        resultat.append(par_reference[(sourate, verset)])
    return resultat


def _verifier_contrat(references, debut, fin):
    """Vérifie que la règle de traversée a rendu un résultat exploitable."""
    if (
        not references
        or tuple(references[0]) != debut
        or tuple(references[-1]) != fin
        or list(references) != sorted(set(map(tuple, references)))
    ):
        raise CorpusInvalideError(
            "La règle de traversée de sourates a renvoyé un résultat incohérent : "
            "la liste doit commencer au début du passage, finir à sa fin, "
            "être triée et sans doublon."
        )
