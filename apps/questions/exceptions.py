"""Erreurs de l'application questions."""


class QuestionInvalideError(Exception):
    """Une question ou un passage coranique qui viole une règle (§8.4)."""


class SerieInvalideError(Exception):
    """Une série ou un lot qui viole une règle (RM-20, RM-22, RM-23)."""
