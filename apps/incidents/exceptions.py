"""Exceptions de l'application incidents."""


class IncidentInvalideError(Exception):
    """Une déclaration ou une résolution d'incident viole une règle (droit, cohérence, texte manquant)."""
