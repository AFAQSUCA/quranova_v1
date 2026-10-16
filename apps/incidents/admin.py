"""Journal des incidents dans l'administration : le personnel déclare et résout ; personne ne modifie l'historique ni ne supprime (§13.6)."""
from django.contrib import admin

from apps.commun.admin import ROLES_ECRITURE, AdminDuClient, role_admin
from apps.incidents import services
from apps.incidents.models import Incident


@admin.register(Incident)
class IncidentAdmin(AdminDuClient):
    list_display = ("survenu_le", "type", "gravite", "concours", "description_courte", "resolu_le", "duree")
    list_filter = ("gravite", "type", "concours")
    search_fields = ("description", "resolution")
    date_hierarchy = "survenu_le"
    raw_id_fields = ("prestation",)

    @admin.display(description="Description")
    def description_courte(self, obj):
        return (obj.description[:80] + "…") if len(obj.description) > 80 else obj.description

    @admin.display(description="Durée")
    def duree(self, obj):
        return "—" if obj.duree is None else str(obj.duree).split(".")[0]

    def has_delete_permission(self, request, obj=None):
        return False  # un incident ne s'efface jamais : c'est une trace

    def get_fields(self, request, obj=None):
        base = ["concours", "session", "prestation", "type", "gravite", "survenu_le", "description"]
        return base if obj is None else base + ["declare_par", "resolu_le", "resolution"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        if obj.resolu_le is not None:
            return self.get_fields(request, obj)  # un incident résolu ne se réécrit plus
        # Avant résolution : seuls la résolution et son heure se saisissent ; la déclaration d'origine reste telle qu'elle a été faite.
        return ["concours", "session", "prestation", "type", "gravite", "survenu_le", "description", "declare_par"]

    def save_model(self, request, obj, form, change):
        if role_admin(request.user) not in ROLES_ECRITURE:
            return
        if not change:
            self.executer_metier(request, lambda: services.enregistrer_declaration(obj, request.user))
            return
        ancien = Incident.objects.get(pk=obj.pk)
        if ancien.resolu_le is None and (obj.resolution or "").strip():
            self.executer_metier(request, lambda: services.resoudre(ancien, request.user, obj.resolution, obj.resolu_le))
