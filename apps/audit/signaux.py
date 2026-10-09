"""Enregistre les connexions des utilisateurs dans le journal d'audit (§15.2)."""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.audit.services import journaliser
from apps.commun.reseau import adresse_du_client


@receiver(user_logged_in)
def journaliser_connexion(sender, request, user, **kwargs):
    adresse = adresse_du_client(request) if request is not None else ""
    journaliser(
        "connexion", organisation=getattr(user, "organisation", None), auteur=user,
        objet=user, terminal=adresse, details={"role": user.role},
    )
