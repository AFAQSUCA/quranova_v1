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
