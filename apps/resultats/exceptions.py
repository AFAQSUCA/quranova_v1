"""Erreurs de l'application resultats."""


class NoteManquanteError(Exception):
    """Un critère n'a pas de note : on ne le convertit JAMAIS en zéro (RM-16)."""


class RegleNonPriseEnChargeError(Exception):
    """Une règle de classement ou de départage que le calcul automatique ne sait pas appliquer (§10.4)."""


class ClassementInvalideError(Exception):
    """Une validation ou une correction de classement refusée (RM-18, REC-39)."""
