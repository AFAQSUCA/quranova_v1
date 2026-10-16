"""Administration des clients et de leurs missions (§7.1)."""
from django.contrib import admin

from apps.clients.models import Mission, Organisation
from apps.commun.admin import AdminDuClient


@admin.register(Organisation)
class OrganisationAdmin(AdminDuClient):
    champ_organisation = "pk"
    list_display = ("nom", "statut", "courriel", "telephone")
    list_filter = ("statut",)
    search_fields = ("nom",)


@admin.register(Mission)
class MissionAdmin(AdminDuClient):
    list_display = ("nom", "organisation", "lieu", "date_debut", "date_fin", "statut")
    list_filter = ("statut", "organisation")
    search_fields = ("nom", "lieu")
    date_hierarchy = "date_debut"
