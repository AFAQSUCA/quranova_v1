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
