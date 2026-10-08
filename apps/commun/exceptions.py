"""Exceptions partagées par toutes les applications."""


class IncoherenceOrganisationError(Exception):
    """L'organisation d'une donnée diffère de celle de son parent (règle absolue n°3, RM-20)."""
