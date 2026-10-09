"""Règles d'accès aux données selon le rôle (§6.3, REC-29, RM-20)."""
from apps.clients.models import Mission
from apps.utilisateurs.models import Utilisateur


def missions_accessibles(utilisateur):
    """Renvoie les missions auxquelles ``utilisateur`` a le droit d'accéder.

    - administrateur : toutes (chaque accès devra être journalisé, cf. audit) ;
    - responsable client : celles de son organisation ;
    - opérateur : celles qui lui sont affectées ;
    - utilisateur désactivé ou anonyme : aucune.
    """
    if not getattr(utilisateur, "is_authenticated", False) or not utilisateur.is_active:
        return Mission.objects.none()
    if utilisateur.role == Utilisateur.Role.ADMINISTRATEUR:
        return Mission.objects.all()
    if utilisateur.role == Utilisateur.Role.RESPONSABLE_CLIENT:
        return Mission.objects.pour_organisation(utilisateur.organisation)
    if utilisateur.role == Utilisateur.Role.OPERATEUR:
        return Mission.objects.filter(affectations__utilisateur=utilisateur)
    return Mission.objects.none()
