"""Authentification du personnel avec limitation des essais (§15.1).

Le verrou est ici, dans le backend, et pas seulement dans le formulaire : toute voie d'authentification est limitée (défense en profondeur).
"""
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from apps.commun.reseau import adresse_du_client
from apps.utilisateurs import connexion
from apps.utilisateurs.exceptions import TropDEssaisConnexionError


class ModelBackendLimite(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        adresse = adresse_du_client(request) if request is not None else ""
        try:
            connexion.verifier_limite(username, adresse)
        except TropDEssaisConnexionError:
            raise PermissionDenied from None  # Django interprète : authentification refusée, on n'essaie pas d'autres backends
        utilisateur = super().authenticate(request, username=username, password=password, **kwargs)
        connexion.noter(username, adresse, reussie=utilisateur is not None)
        return utilisateur
