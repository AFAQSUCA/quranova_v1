"""Administration des jurés (§7.4)."""
from django.contrib import admin

from apps.commun.admin import AdminDuClient, ConsultationSeule, InlineDuClient
from apps.jury.models import AffectationJury, CodeAccesJure, Jure


class AffectationInline(InlineDuClient):
    model = AffectationJury


@admin.register(Jure)
class JureAdmin(AdminDuClient):
    list_display = ("nom", "prenom", "role", "actif", "organisation")
    list_filter = ("role", "actif", "organisation")
    search_fields = ("nom", "prenom")
    inlines = [AffectationInline]


@admin.register(CodeAccesJure)
class CodeAccesJureAdmin(ConsultationSeule):
    """Les codes se génèrent par le service (le code en clair n'est jamais stocké, D23)."""

    list_display = ("jure", "session", "valide_du", "valide_jusqu_au", "revoque_le", "derniere_utilisation")
    list_filter = ("session",)
    exclude = ("empreinte",)
