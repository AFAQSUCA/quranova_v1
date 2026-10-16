"""Formulaire de connexion de l'administration : explique le verrou au lieu d'afficher « identifiants incorrects »."""
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError

from apps.commun.reseau import adresse_du_client
from apps.utilisateurs import connexion
from apps.utilisateurs.exceptions import TropDEssaisConnexionError


class FormulaireConnexionAdmin(AdminAuthenticationForm):
    def clean(self):
        identifiant = self.cleaned_data.get("username")
        if identifiant:
            try:
                connexion.verifier_limite(identifiant, adresse_du_client(self.request) if self.request is not None else "")
            except TropDEssaisConnexionError as erreur:
                raise ValidationError(str(erreur), code="verrouille") from None
        return super().clean()
