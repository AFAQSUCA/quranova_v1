"""Erreurs de l'application presentation."""


class PlanImpossibleError(Exception):
    """Le plan des diapositives ne peut pas être construit (prestation sans tirage valide, etc.)."""
