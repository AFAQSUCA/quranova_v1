"""Fonctions utilitaires partagées par les tests des applications clients, utilisateurs, etc."""
import itertools
from datetime import date

from apps.clients.models import Mission, Organisation
from apps.utilisateurs.models import Utilisateur

_compteur = itertools.count(1)


def creer_organisation(**champs):
    n = next(_compteur)
    valeurs = {"nom": f"Organisation-test-{n}"}
    valeurs.update(champs)
    return Organisation.objects.create(**valeurs)


def creer_mission(organisation=None, **champs):
    n = next(_compteur)
    valeurs = {
        "organisation": organisation or creer_organisation(),
        "nom": f"Mission-test-{n}",
        "lieu": "Abidjan",
        "date_debut": date(2027, 1, 20),
        "date_fin": date(2027, 1, 21),
    }
    valeurs.update(champs)
    return Mission.objects.create(**valeurs)


def creer_utilisateur(role=Utilisateur.Role.OPERATEUR, organisation=None, **champs):
    """Crée un utilisateur de test ; un responsable client reçoit une organisation s'il n'en a pas."""
    n = next(_compteur)
    if role == Utilisateur.Role.RESPONSABLE_CLIENT and organisation is None:
        organisation = creer_organisation()
    return Utilisateur.objects.create_user(
        username=f"utilisateur-test-{n}",
        password="mot-de-passe-de-test",
        role=role,
        organisation=organisation,
        **champs,
    )
