"""Administration de la configuration d'un concours (§7.2, RM-27, RM-31)."""
from django.contrib import admin

from apps.commun.admin import AdminDuClient, InlineDuClient, appliquer_action, role_admin
from apps.concours import services
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from django.utils.html import format_html, format_html_join

from apps.prestations.services import ouvrir_epreuve
from apps.resultats import services as services_resultats
from apps.resultats import validation
from apps.utilisateurs.models import Utilisateur


@admin.register(Concours)
class ConcoursAdmin(AdminDuClient):
    list_display = ("nom", "edition", "mission", "etat", "version_corpus", "configuration_validee_le")
    list_filter = ("etat", "organisation")
    search_fields = ("nom", "edition")
    actions = ["valider_la_configuration", "ouvrir", "demarrer"]

    def get_readonly_fields(self, request, obj=None):
        # L'état et la validation ne changent que par les services (RM-27, RM-31, D14).
        lecture = ["etat", "configuration_validee_par", "configuration_validee_le", "configuration_empreinte"]
        if obj is not None and obj.etat != Concours.Etat.BROUILLON:
            lecture.append("version_corpus")  # figée à l'ouverture (RM-27)
        return lecture

    def get_actions(self, request):
        actions = super().get_actions(request)
        if role_admin(request.user) == Utilisateur.Role.RESPONSABLE_CLIENT:
            return {"valider_la_configuration": actions["valider_la_configuration"]}
        actions.pop("valider_la_configuration", None)  # le client valide, le prestataire exécute
        return actions

    @admin.action(description="Valider la configuration (responsable client)")
    def valider_la_configuration(self, request, queryset):
        appliquer_action(request, queryset, lambda c: services.valider_configuration(c, request.user),
                         "configuration validée")

    @admin.action(description="Ouvrir le concours")
    def ouvrir(self, request, queryset):
        appliquer_action(request, queryset, services.ouvrir_concours, "concours ouvert")

    @admin.action(description="Démarrer le concours (les tirages deviennent possibles)")
    def demarrer(self, request, queryset):
        appliquer_action(request, queryset, services.demarrer_concours, "concours en cours")


@admin.register(Categorie)
class CategorieAdmin(AdminDuClient):
    list_display = ("nom", "concours", "discipline", "age_minimum", "age_maximum", "regle_classement")
    list_filter = ("discipline", "concours")
    search_fields = ("nom",)


class CritereInline(InlineDuClient):
    model = CritereNotation


@admin.register(Epreuve)
class EpreuveAdmin(AdminDuClient):
    list_display = ("nom", "categorie", "ordre", "questions_par_serie", "tirages_par_candidat", "etat")
    list_filter = ("etat", "categorie__concours")
    search_fields = ("nom",)
    inlines = [CritereInline]
    readonly_fields = ("etat", "classement_provisoire")
    actions = ["ouvrir", "valider_le_classement", "valider_le_classement_avec_egalites"]

    @admin.display(description="Classement provisoire (recalculé à chaque affichage)")
    def classement_provisoire(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        try:
            lignes = services_resultats.classement_provisoire(obj)
        except NotImplementedError as regle:
            return f"Calcul indisponible : {regle}"
        except Exception as erreur:  # une règle non prise en charge ne doit pas casser la fiche
            return f"Calcul indisponible : {erreur}"
        if not lignes:
            return "Aucun candidat en compétition."
        return format_html(
            "<table><tr><th>Rang</th><th>Candidat</th><th>Score</th><th>Évaluations</th><th></th></tr>{}</table>",
            format_html_join(
                "",
                "<tr><td>{}</td><td>n° {} — {}</td><td>{}</td><td>{}/{}</td><td>{}</td></tr>",
                (
                    (
                        ("—" if l["rang"] is None else f"{l['rang']}{' (ex aequo)' if l['ex_aequo'] else ''}"),
                        l["participation"].numero_candidat, l["participation"].candidat.nom_complet,
                        "—" if l["score"] is None else l["score"],
                        l["evaluations_validees"], l["evaluations_attendues"],
                        "" if l["complet"] else "notation incomplète : " + ", ".join(l["jures_manquants"]),
                    )
                    for l in lignes
                ),
            ),
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if role_admin(request.user) == Utilisateur.Role.RESPONSABLE_CLIENT:
            return {k: v for k, v in actions.items() if k.startswith("valider_le_classement")}
        for nom in ("valider_le_classement", "valider_le_classement_avec_egalites"):
            actions.pop(nom, None)  # le client valide, le prestataire exécute (RM-18)
        return actions

    @admin.action(description="Valider le classement définitif (responsable client)")
    def valider_le_classement(self, request, queryset):
        appliquer_action(request, queryset, lambda e: validation.valider_classement(e, request.user), "classement validé")

    @admin.action(description="Valider le classement définitif, en confirmant les ex aequo")
    def valider_le_classement_avec_egalites(self, request, queryset):
        appliquer_action(
            request, queryset, lambda e: validation.valider_classement(e, request.user, confirmer_egalites=True), "classement validé"
        )

    @admin.action(description="Ouvrir l'épreuve (lot complet et suffisant)")
    def ouvrir(self, request, queryset):
        appliquer_action(request, queryset, ouvrir_epreuve, "épreuve ouverte")


@admin.register(Session)
class SessionAdmin(AdminDuClient):
    list_display = ("nom", "concours", "date", "lieu")
    list_filter = ("concours",)
