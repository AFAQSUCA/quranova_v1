"""Exceptions de l'application utilisateurs."""


class AffectationInvalideError(Exception):
    """Une affectation d'opérateur à une mission viole une règle d'accès (§6.3)."""


class TropDEssaisConnexionError(Exception):
    """Trop d'échecs de connexion récents pour ce compte ou cette adresse : réessayer plus tard (§15.1)."""

    def __init__(self, attente_secondes):
        self.attente_secondes = attente_secondes
        minutes = max(1, -(-attente_secondes // 60))
        super().__init__(f"Trop d'échecs de connexion. Réessayez dans {minutes} minute{'s' if minutes > 1 else ''}.")
