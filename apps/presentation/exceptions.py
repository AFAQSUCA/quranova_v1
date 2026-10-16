"""Erreurs de l'application presentation."""


class PlanImpossibleError(Exception):
    """Le plan des diapositives ne peut pas être construit (prestation sans tirage valide, etc.)."""


class TransitionInterditeError(Exception):
    """L'action demandée n'est pas permise dans l'état courant (§9.3)."""
