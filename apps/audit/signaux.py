"""Enregistre les connexions des utilisateurs dans le journal d'audit (§15.2)."""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.audit.services import journaliser


@receiver(user_logged_in)
def journaliser_connexion(sender, request, user, **kwargs):
    adresse = request.META.get("REMOTE_ADDR", "") if request is not None else ""
    journaliser(
        "connexion", organisation=getattr(user, "organisation", None), auteur=user,
        objet=user, terminal=adresse, details={"role": user.role},
    )
