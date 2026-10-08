"""Erreurs de l'application prestations."""
from apps.candidats.exceptions import TirageImpossibleError


class PrestationInvalideError(Exception):
    """Une prestation incohérente (participation, épreuve ou session qui ne vont pas ensemble)."""


class TirageInvalideError(Exception):
    """Un tirage incohérent, ou une tentative de modifier un tirage enregistré (§14.2)."""


class TirageRefuseError(TirageImpossibleError):
    """Le tirage est refusé : état du concours, de l'épreuve ou de la prestation, ou quota atteint (§8.5)."""


class LotEpuiseError(TirageImpossibleError):
    """Aucune série admissible : le tirage est bloqué, l'opérateur doit compléter le lot (RM-21)."""


class OuvertureEpreuveRefuseeError(Exception):
    """L'épreuve ne peut pas être ouverte : lot absent, séries incomplètes ou insuffisantes (RM-22, RM-24)."""


class AnnulationInvalideError(Exception):
    """L'annulation d'un tirage est refusée (RM-25)."""


class TerminalInvalideError(Exception):
    """Jeton inconnu, révoqué ou absent : le terminal n'est pas authentifié (§15)."""


class AppelInvalideError(Exception):
    """L'opérateur ne peut pas appeler cette prestation sur ce terminal (§8.5, REC-14)."""


class PasDAppelError(TirageImpossibleError):
    """Aucun candidat n'est appelé sur ce terminal : l'opérateur doit d'abord l'appeler."""
