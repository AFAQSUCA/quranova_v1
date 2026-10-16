"""Administration des comptes et des affectations d'opérateurs (§6)."""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from apps.commun.admin import AdminDuClient, role_admin
from apps.utilisateurs import otp
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Réservé à l'administrateur QURANOVA.

    D29 : pendant le développement, l'administration sert de console aux trois rôles ;
    ``is_staff`` est donc fixé à vrai pour tout compte actif (l'accès réel dépend du rôle).
    """

    list_display = ("username", "role", "organisation", "is_active", "deuxieme_facteur")
    actions = ["reinitialiser_2fa"]
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("QURANOVA", {"fields": ("role", "organisation")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("QURANOVA", {"fields": ("role", "organisation")}),)

    def _admin_seulement(self, request):
        return role_admin(request.user) == Utilisateur.Role.ADMINISTRATEUR

    def has_module_permission(self, request):
        return self._admin_seulement(request)

    has_view_permission = has_add_permission = has_change_permission = has_delete_permission = (
        lambda self, request, obj=None: self._admin_seulement(request)
    )

    @admin.display(description="2FA activée", boolean=True)
    def deuxieme_facteur(self, obj):
        return otp.appareil_confirme(obj) is not None

    @admin.action(description="Réinitialiser le deuxième facteur (téléphone perdu)")
    def reinitialiser_2fa(self, request, queryset):
        if not self._admin_seulement(request):
            self.message_user(request, "Réservé à l'administrateur.", messages.ERROR)
            return
        for cible in queryset:
            otp.reinitialiser(cible, request.user)
            self.message_user(request, f"{cible} : deuxième facteur réinitialisé ; il devra l'activer de nouveau à sa prochaine connexion.", messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        obj.is_staff = True
        super().save_model(request, obj, form, change)


@admin.register(AffectationOperateur)
class AffectationOperateurAdmin(AdminDuClient):
    list_display = ("utilisateur", "mission", "organisation")
    list_filter = ("organisation",)
