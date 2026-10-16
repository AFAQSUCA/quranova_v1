"""Petites aides de gabarit pour l'administration (icônes d'action des lignes)."""
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def peut_supprimer(context, cl) -> str:
    """« 1 » si l'utilisateur peut supprimer dans cette liste, sinon vide.

    Ce n'est qu'un confort d'affichage : la vue de suppression revérifie la permission côté serveur.
    """
    return "1" if cl.model_admin.has_delete_permission(context["request"]) else ""
