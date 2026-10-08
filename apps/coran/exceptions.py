"""Exceptions de l'application coran."""


class CorpusImmuableError(Exception):
    """Une écriture est refusée parce qu'elle violerait l'immuabilité du corpus (RM-27, §12.3)."""


class CorpusInvalideError(Exception):
    """Le corpus lu n'a pas la structure attendue ou échoue aux contrôles du §12.2."""


class CorpusDejaImporteError(Exception):
    """Un fichier de même empreinte SHA-256 a déjà été importé."""
