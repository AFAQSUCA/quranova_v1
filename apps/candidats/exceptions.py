"""Exceptions de l'application candidats."""


class ParticipationInvalideError(Exception):
    """Une participation est incohérente (par exemple une catégorie qui n'est pas celle du concours)."""


class TirageImpossibleError(Exception):
    """Le tirage ne peut pas être déclenché pour cette participation (§14.2, RM-28)."""


class ParticipationNonAdmiseError(TirageImpossibleError):
    """La participation n'est pas admise : aucun tirage (§14.2)."""


class ConsentementManquantError(TirageImpossibleError):
    """Le consentement parental requis n'est pas enregistré : aucun tirage (RM-28, règle absolue n°6)."""
