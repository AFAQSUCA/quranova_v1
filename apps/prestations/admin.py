"""Administration des prestations et des tirages (§8.3, §14.2)."""
from django.contrib import admin

from apps.commun.admin import AdminDuClient, ConsultationSeule
from apps.prestations.models import Prestation, Tirage


@admin.register(Prestation)
class PrestationAdmin(AdminDuClient):
    list_display = ("rang_passage", "participation", "epreuve", "session", "etat")
    list_filter = ("etat", "epreuve", "session")
    readonly_fields = ("etat",)  # l'état ne change que par les services (tirage, diaporama, notation)


@admin.register(Tirage)
class TirageAdmin(ConsultationSeule):
    """Un tirage ne se crée que par ``effectuer_tirage`` et ne s'annule que par ``annuler_tirage`` (§14.2)."""

    list_display = ("prestation", "serie", "rang", "statut", "terminal", "cree_le")
    list_filter = ("statut", "prestation__epreuve")
