"""Exceptions de l'application coran."""


class CorpusImmuableError(Exception):
    """Une écriture est refusée parce qu'elle violerait l'immuabilité du corpus (RM-27, §12.3)."""
