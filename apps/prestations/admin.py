"""Administration des prestations et des tirages (§8.3, §14.2)."""
from django.contrib import admin, messages
from django.urls import reverse

from apps.commun.admin import AdminDuClient, ConsultationSeule, appliquer_action
from apps.prestations import terminaux
from apps.prestations.exceptions import AppelInvalideError
from apps.prestations.models import Prestation, Terminal, Tirage


@admin.register(Prestation)
class PrestationAdmin(AdminDuClient):
    list_display = ("rang_passage", "participation", "epreuve", "session", "etat")
    list_filter = ("etat", "epreuve", "session")
    readonly_fields = ("etat",)  # l'état ne change que par les services (tirage, diaporama, notation)
    actions = ["appeler_au_tirage"]

    @admin.action(description="Appeler au tirage (terminal de la session)")
    def appeler_au_tirage(self, request, queryset):
        def appeler(prestation):
            actifs = list(prestation.session.terminaux.filter(type=Terminal.Type.TIRAGE, revoque_le__isnull=True))
            if len(actifs) != 1:
                raise AppelInvalideError(
                    f"{len(actifs)} terminal(aux) actif(s) pour cette session : il en faut exactement un."
                )
            terminaux.appeler_prestation(actifs[0], prestation, request.user)

        appliquer_action(request, queryset, appeler, "candidat appelé sur le terminal de tirage")


@admin.register(Tirage)
class TirageAdmin(ConsultationSeule):
    """Un tirage ne se crée que par ``effectuer_tirage`` et ne s'annule que par ``annuler_tirage`` (§14.2)."""

    list_display = ("prestation", "serie", "rang", "statut", "terminal", "cree_le")
    list_filter = ("statut", "prestation__epreuve")


@admin.register(Terminal)
class TerminalAdmin(AdminDuClient):
    """Une tablette de tirage. Le jeton n'est affiché qu'une fois, à la création (D31)."""

    list_display = ("nom", "type", "session", "prestation_appelee", "revoque_le", "derniere_activite")
    list_filter = ("session",)
    actions = ["liberer", "revoquer"]

    def get_fields(self, request, obj=None):
        return ("session", "nom", "type") if obj is None else ("session", "nom", "type", "prestation_appelee", "revoque_le", "derniere_activite")

    def get_readonly_fields(self, request, obj=None):
        return ("session", "nom", "type", "prestation_appelee", "revoque_le", "derniere_activite") if obj else ()

    def has_change_permission(self, request, obj=None):
        return False if obj else super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        def creer():
            terminal, jeton = terminaux.creer_terminal(obj.session, obj.nom, obj.type)
            obj.__dict__.update(terminal.__dict__)
            adresse = request.build_absolute_uri(reverse("prestations:ecran_tirage")) + "#" + jeton
            messages.warning(
                request,
                f"Terminal créé. Ouvrez cette adresse sur la tablette (elle ne sera plus affichée) : {adresse}",
            )

        self.executer_metier(request, creer)

    @admin.action(description="Libérer le terminal (retirer le candidat appelé)")
    def liberer(self, request, queryset):
        appliquer_action(request, queryset, terminaux.liberer_terminal, "terminal libéré")

    @admin.action(description="Révoquer le terminal (le jeton cesse de fonctionner)")
    def revoquer(self, request, queryset):
        appliquer_action(request, queryset, terminaux.revoquer_terminal, "terminal révoqué")
