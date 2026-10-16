"""Erreurs de l'application audit."""


class AuditImmuableError(Exception):
    """Une entrée du journal d'audit ne se modifie ni ne se supprime jamais (§15.2)."""
