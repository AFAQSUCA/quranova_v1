"""Administration des jurés (§7.4)."""
from django import forms
from django.contrib import admin, messages
from django.template.response import TemplateResponse

from apps.commun.admin import ERREURS_METIER, AdminDuClient, ConsultationSeule, InlineDuClient, appliquer_action, organisations_visibles
from apps.concours.models import Session
from apps.jury import evaluations, services
from apps.jury.models import AffectationJury, CodeAccesJure, CorrectionNote, Jure


class RemiseCodesForm(forms.Form):
    session = forms.ModelChoiceField(queryset=Session.objects.none(), label="Session", help_text="Les codes ne valent que pour cette session.")

    def __init__(self, *args, jures, utilisateur, **kwargs):
        super().__init__(*args, **kwargs)
        visibles = organisations_visibles(utilisateur)
        sessions = Session.objects.filter(organisation_id__in={j.organisation_id for j in jures})
        if visibles is not None:
            sessions = sessions.filter(organisation_id__in=visibles)
        self.fields["session"].queryset = sessions.select_related("concours").order_by("-date", "nom")


class AffectationInline(InlineDuClient):
    model = AffectationJury


@admin.register(Jure)
class JureAdmin(AdminDuClient):
    list_display = ("nom", "prenom", "role", "actif", "organisation")
    list_filter = ("role", "actif", "organisation")
    search_fields = ("nom", "prenom")
    inlines = [AffectationInline]
    actions = ["remettre_les_codes"]

    @admin.action(description="Remettre un code d'accès pour une session (affiché une seule fois)")
    def remettre_les_codes(self, request, queryset):
        jures = list(queryset.order_by("nom", "prenom"))
        soumis = request.POST.get("appliquer")
        formulaire = RemiseCodesForm(request.POST if soumis else None, jures=jures, utilisateur=request.user)
        contexte = {**self.admin_site.each_context(request), "title": "Remettre les codes d'accès", "jures": jures, "form": formulaire, "opts": self.model._meta}
        if soumis and formulaire.is_valid():
            try:
                remis = services.remettre_codes(request.user, jures, formulaire.cleaned_data["session"])
            except ERREURS_METIER as erreur:
                formulaire.add_error(None, str(erreur))
            else:
                reponse = TemplateResponse(request, "admin/jury/codes_remis.html", {**contexte, "remis": remis, "session": formulaire.cleaned_data["session"]})
                reponse["Cache-Control"] = "no-store"
                return reponse
        return TemplateResponse(request, "admin/jury/remettre_codes.html", contexte)


@admin.register(CodeAccesJure)
class CodeAccesJureAdmin(ConsultationSeule):
    """Les codes se génèrent par le service (le code en clair n'est jamais stocké, D23)."""

    list_display = ("jure", "session", "valide_du", "valide_jusqu_au", "revoque_le", "derniere_utilisation")
    list_filter = ("session",)
    exclude = ("empreinte",)


@admin.register(CorrectionNote)
class CorrectionNoteAdmin(ConsultationSeule):
    """Demandes de correction d'une note validée (REC-17) : le responsable du client approuve ou refuse ; l'opérateur et le juré n'y touchent pas (RM-18)."""

    list_display = ("evaluation", "critere", "ancienne_valeur", "nouvelle_valeur", "motif", "statut", "demandee_le", "traitee_par")
    list_filter = ("statut",)
    actions = ["approuver", "refuser"]

    @admin.action(description="Approuver la correction (responsable du client)")
    def approuver(self, request, queryset):
        appliquer_action(request, queryset, lambda c: evaluations.traiter_correction(c, request.user, True), "correction approuvée, la note est modifiée")

    @admin.action(description="Refuser la correction (responsable du client)")
    def refuser(self, request, queryset):
        appliquer_action(request, queryset, lambda c: evaluations.traiter_correction(c, request.user, False), "correction refusée, la note est inchangée")
