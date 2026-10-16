"""Administration du corpus coranique : consultation seulement (§12.1, §12.3, §14.2).

Le texte coranique vient uniquement du fichier Tanzil, par la commande d'import.
Personne, pas même un superutilisateur, ne peut l'ajouter, le modifier ni le
supprimer depuis l'interface d'administration.
"""
from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.commun.admin import role_admin
from apps.coran import validation
from apps.coran.exceptions import CorpusImmuableError, CorpusInvalideError, ValidationCorpusRefuseeError
from apps.coran.models import Sourate, Verset, VersionCorpus
from apps.utilisateurs.models import Utilisateur

ERREURS_CORPUS = (CorpusImmuableError, CorpusInvalideError, ValidationCorpusRefuseeError)


class ValidationForm(forms.Form):
    """Ce que l'administrateur enregistre APRÈS que le référent a relu et signé le procès-verbal."""

    referent_nom = forms.CharField(max_length=200, label="Nom du référent coranique")
    referent_qualite = forms.CharField(max_length=200, required=False, label="Qualité", help_text="Par exemple : imam, enseignant de qirāʾāt.")
    date_signature = forms.DateField(label="Date de signature du procès-verbal", widget=forms.DateInput(attrs={"type": "date"}), initial=timezone.localdate)
    atteste = forms.BooleanField(
        label="J'atteste avoir en main le procès-verbal signé : échantillon relu et comparé au Mushaf de Médine, rendu typographique validé.",
    )


class LectureSeuleAdmin(admin.ModelAdmin):
    """Base commune : on peut consulter, jamais écrire.

    Quand ``has_change_permission`` renvoie False mais que la permission de
    consultation est accordée, Django affiche la fiche en lecture seule. Retirer
    ``has_delete_permission`` supprime aussi l'action « Supprimer la sélection ».
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VersionCorpus)
class VersionCorpusAdmin(LectureSeuleAdmin):
    list_display = ("source", "version_source", "riwaya", "statut", "date_import", "date_validation")
    list_filter = ("statut", "riwaya")
    readonly_fields = ("documents", "validation_du_referent")
    actions = ["enregistrer_la_validation", "activer"]

    @admin.display(description="Procès-verbal de validation")
    def documents(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        return format_html(
            '<a href="{}" target="_blank">Procès-verbal à signer (imprimable)</a> · <a href="{}">Procès-verbal (PDF)</a>',
            reverse("coran:proces_verbal", args=[obj.pk]), reverse("coran:proces_verbal_pdf", args=[obj.pk]),
        )

    @admin.display(description="Validation par le référent coranique")
    def validation_du_referent(self, obj):
        enregistree = getattr(obj, "validation", None) if obj is not None and obj.pk else None
        return str(enregistree) if enregistree else "Non validée."

    def get_actions(self, request):
        actions = super().get_actions(request)
        if role_admin(request.user) != Utilisateur.Role.ADMINISTRATEUR:
            return {}  # valider et activer sont réservés à l'administrateur QURANOVA (§12.3)
        return actions

    @admin.action(description="Enregistrer la validation du référent coranique")
    def enregistrer_la_validation(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Sélectionnez une seule version à valider.", messages.ERROR)
            return None
        version = queryset.get()
        soumis = request.POST.get("appliquer")
        formulaire = ValidationForm(request.POST if soumis else None)
        if soumis and formulaire.is_valid():
            d = formulaire.cleaned_data
            try:
                validation.valider_version(version, request.user, d["referent_nom"], d["date_signature"], qualite=d["referent_qualite"])
            except ERREURS_CORPUS as erreur:
                formulaire.add_error(None, str(erreur))
            else:
                self.message_user(request, f"Version {version.pk} validée par {d['referent_nom']}. Elle peut maintenant être activée.", messages.SUCCESS)
                return HttpResponseRedirect(reverse("admin:coran_versioncorpus_changelist"))
        return TemplateResponse(
            request, "admin/coran/valider_corpus.html",
            {**self.admin_site.each_context(request), "title": "Enregistrer la validation du corpus", "version": version, "form": formulaire, "opts": self.model._meta},
        )

    @admin.action(description="Activer pour les nouveaux concours")
    def activer(self, request, queryset):
        for version in queryset:
            try:
                validation.activer_version(version, request.user)
            except ERREURS_CORPUS as erreur:
                self.message_user(request, f"Version {version.pk} : {erreur}", messages.ERROR)
            else:
                self.message_user(request, f"Version {version.pk} activée.", messages.SUCCESS)


@admin.register(Sourate)
class SourateAdmin(LectureSeuleAdmin):
    list_display = ("numero", "nom_translitteration", "nom_arabe", "nombre_versets", "type_revelation", "version")
    list_filter = ("version", "type_revelation")
    list_select_related = ("version",)
    search_fields = ("nom_translitteration", "nom_arabe")


@admin.register(Verset)
class VersetAdmin(LectureSeuleAdmin):
    list_display = ("reference", "sourate")
    list_filter = ("sourate__version", "sourate")
    list_select_related = ("sourate",)
    show_full_result_count = False  # évite un COUNT(*) coûteux sur 6 236 lignes par version
