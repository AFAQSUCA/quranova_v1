"""Transitions de l'état de présentation (§9.3, RM-10, RM-11).

Fonction PURE : elle ne touche ni la base ni le réseau. Elle reçoit la position courante et l'action, et
renvoie la nouvelle position, ou refuse. Le service ``appliquer_commande`` se charge du reste (verrou,
version, journal).
"""
from dataclasses import dataclass, replace

from apps.presentation.exceptions import TransitionInterditeError  # noqa: F401

PREPAREE, AFFICHAGE, PAUSE, TERMINEE = "preparee", "affichage", "pause", "terminee"
ACTIONS = ("demarrer", "suivante", "precedente", "pause", "reprendre", "reafficher", "terminer")


@dataclass(frozen=True)
class Position:
    """Où en est la présentation : sa phase, la diapositive courante (``None`` si rien n'est affiché), le rejeu."""

    phase: str
    index: int | None = None
    rejeu: int = 0


def appliquer_transition(position, total, action):
    """Renvoie la ``Position`` après ``action``, ou lève ``TransitionInterditeError`` avec un message clair.

    TODO(human) : écrivez la règle. ``total`` est le nombre de diapositives du plan (les index vont de 0 à
    total - 1). Contrat (voir ``test_transitions.py``) :
    - ``demarrer`` : « préparée » -> « en affichage », à la diapositive 0 ;
    - ``suivante`` : seulement « en affichage » ; avance d'une diapositive ; INTERDITE à la dernière
      (l'opérateur doit « terminer ») : jamais de défilement automatique, jamais au-delà de la fin ;
    - ``precedente`` : seulement « en affichage » et pas à la première diapositive ; recule d'une ;
    - ``pause`` : « en affichage » -> « en pause » (même diapositive) ; ``reprendre`` : l'inverse ;
    - ``reafficher`` : seulement « en affichage » ; même diapositive, ``rejeu`` augmente de 1 ;
    - ``terminer`` : « en affichage » ou « en pause » -> « terminée » (la diapositive courante est conservée) ;
    - tout le reste est interdit, y compris toute action sur une présentation « terminée » et l'action
      « preparer » (qui n'est pas une transition : elle crée l'état) ou une action inconnue.
    La position reçue n'est jamais modifiée (``Position`` est figée) : renvoyez-en une nouvelle.
    """
    phase, index = position.phase, position.index
    if phase == TERMINEE:
        raise TransitionInterditeError("La présentation est terminée : plus aucune commande n'est possible.")
    if action == "demarrer":
        if phase != PREPAREE:
            raise TransitionInterditeError("La présentation est déjà démarrée.")
        return Position(AFFICHAGE, 0, position.rejeu)
    if phase == PREPAREE:
        raise TransitionInterditeError("La présentation n'est pas démarrée : utilisez « Démarrer ».")
    if action == "reprendre":
        if phase != PAUSE:
            raise TransitionInterditeError("La présentation n'est pas en pause.")
        return replace(position, phase=AFFICHAGE)
    if action == "terminer":
        return replace(position, phase=TERMINEE)  # depuis l'affichage ou la pause
    if phase == PAUSE:
        raise TransitionInterditeError("La présentation est en pause : reprenez avant de continuer.")
    # À partir d'ici, la phase est « affichage ».
    if action == "suivante":
        if index >= total - 1:
            raise TransitionInterditeError("C'est la dernière diapositive : utilisez « Terminer la prestation ».")
        return replace(position, index=index + 1)
    if action == "precedente":
        if index <= 0:
            raise TransitionInterditeError("C'est déjà la première diapositive.")
        return replace(position, index=index - 1)
    if action == "pause":
        return replace(position, phase=PAUSE)
    if action == "reafficher":
        return replace(position, rejeu=position.rejeu + 1)
    raise TransitionInterditeError(f"Action inconnue ou non permise ici : « {action} ».")
