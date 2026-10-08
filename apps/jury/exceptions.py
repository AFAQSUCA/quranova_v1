"""Exceptions de l'application jury."""


class AffectationInvalideError(Exception):
    """Une affectation de juré ou la génération d'un code d'accès n'est pas permise (§6.3, RM-20)."""


class CodeInvalideError(Exception):
    """Un code d'accès de juré est refusé.

    Le message affiché à l'écran reste volontairement vague (il ne dit pas si le code existe) ;
    la raison précise est dans ``raison``, pour le journal d'audit.
    """

    def __init__(self, raison):
        super().__init__("Code invalide ou expiré.")
        self.raison = raison


class EvaluationInterditeError(Exception):
    """Ce juré ne peut pas noter cette prestation maintenant (affectation, état de la prestation, §10, RM-15)."""


class NoteInvalideError(Exception):
    """Une valeur de note est refusée (hors barème, non numérique, critère d'une autre épreuve)."""


class EvaluationIncompleteError(Exception):
    """L'évaluation ne peut pas être validée : il manque des notes (RM-16, REC-12). Jamais converties en zéro."""

    def __init__(self, manquants):
        self.manquants = list(manquants)
        super().__init__("Évaluation incomplète : il manque " + ", ".join(self.manquants) + ".")


class EvaluationValideeError(Exception):
    """Une évaluation validée ne se modifie que par une correction approuvée (§10.2, REC-17)."""


class CorrectionInvalideError(Exception):
    """Une demande ou un traitement de correction est refusé."""
