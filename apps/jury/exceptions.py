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
