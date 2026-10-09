"""Les classements définitifs se consultent ; ils ne se créent que par la validation du responsable client (RM-18)."""
from django.contrib import admin

from apps.commun.admin import ConsultationSeule, InlineDuClient
from apps.resultats.models import Classement, LigneDeClassement


class LigneInline(InlineDuClient):
    model = LigneDeClassement
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Classement)
class ClassementAdmin(ConsultationSeule):
    list_display = ("epreuve", "version", "est_correction", "valide_par", "valide_le")
    list_filter = ("est_correction", "epreuve")
    inlines = [LigneInline]
