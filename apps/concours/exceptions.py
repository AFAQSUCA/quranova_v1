"""Exceptions de l'application concours."""


class ConfigurationInvalideError(Exception):
    """La configuration d'un concours est incomplète, ou l'opération demandée n'est pas permise dans cet état."""


class ValidationRefuseeError(Exception):
    """Seul le responsable du client concerné peut valider la configuration (§6.2, RM-18, RM-31)."""
