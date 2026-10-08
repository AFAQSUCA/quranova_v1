"""Exceptions de l'application utilisateurs."""


class AffectationInvalideError(Exception):
    """Une affectation d'opérateur à une mission viole une règle d'accès (§6.3)."""
