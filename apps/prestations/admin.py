"""Administration des prestations et des tirages (§8.3, §14.2)."""
from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.commun.admin import ERREURS_METIER, AdminDuClient, ConsultationSeule, appliquer_action
from apps.jury import fiches
from apps.jury.exceptions import EvaluationIncompleteError, EvaluationInterditeError, NoteInvalideError
from apps.jury.models import Jure
from apps.prestations import terminaux
from apps.prestations.exceptions import AppelInvalideError
from apps.prestations.models import Prestation, Terminal, Tirage


def formulaire_fiche(prestation, donnees):
    """Formulaire de saisie d'une fiche papier : un champ par critère du barème de CETTE épreuve, le juré, le motif obligatoire."""
    champs = {
        "jure": forms.ModelChoiceField(
            queryset=Jure.objects.filter(affectations__epreuve_id=prestation.epreuve_id, actif=True).order_by("nom", "prenom"), label="Juré"),
        "reference": forms.CharField(max_length=40, required=False, label="Référence de la fiche", help_text="Imprimée en haut de la fiche (FS-…)."),
    }
    for critere in prestation.epreuve.criteres.order_by("ordre"):
        champs[f"note_{critere.pk}"] = forms.CharField(
            max_length=10, required=False, label=f"{critere.libelle} (sur {critere.maximum.normalize():f}, coef. {critere.coefficient.normalize():f})",
            help_text="Laisser vide seulement si la case de la fiche est vide : la saisie sera refusée (jamais comptée zéro).")
    champs["observation"] = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Observation")
    champs["motif"] = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Motif de la saisie différée", help_text="Pourquoi la fiche papier a été utilisée (obligatoire).")
    return type("FormulaireFiche", (forms.Form,), champs)(donnees)


@admin.register(Prestation)
class PrestationAdmin(AdminDuClient):
    list_display = ("rang_passage", "participation", "epreuve", "session", "etat")
    list_filter = ("etat", "epreuve", "session")
    readonly_fields = ("etat",)  # l'état ne change que par les services (tirage, diaporama, notation)
    actions = ["appeler_au_tirage", "saisir_fiche_de_secours"]

    @admin.action(description="Saisir une fiche de secours (papier) d'un juré")
    def saisir_fiche_de_secours(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Sélectionnez une seule prestation.", messages.ERROR)
            return None
        prestation = queryset.select_related("epreuve", "participation__candidat", "session").get()
        formulaire = formulaire_fiche(prestation, request.POST if request.POST.get("appliquer") else None)
        if request.POST.get("appliquer") and formulaire.is_valid():
            d = formulaire.cleaned_data
            notes = {str(c.pk): d.get(f"note_{c.pk}", "") for c in prestation.epreuve.criteres.all()}
            try:
                fiches.saisir_fiche(request.user, d["jure"], prestation, notes, d["motif"], observation=d["observation"], reference=d["reference"])
            except (*ERREURS_METIER, EvaluationIncompleteError, EvaluationInterditeError, NoteInvalideError) as erreur:
                formulaire.add_error(None, str(erreur))
            else:
                self.message_user(request, f"Fiche de {d['jure'].nom_complet} saisie (motif consigné). Évaluation validée.", messages.SUCCESS)
                return HttpResponseRedirect(reverse("admin:prestations_prestation_changelist"))
        return TemplateResponse(request, "admin/prestations/saisir_fiche.html", {
            **self.admin_site.each_context(request), "title": "Saisir une fiche de secours", "prestation": prestation, "form": formulaire, "opts": self.model._meta})

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
            if terminal.type == Terminal.Type.SCENE:
                chemin = reverse("presentation:ecran_scene", args=[terminal.session_id])
            else:
                chemin = reverse("prestations:ecran_tirage")
            adresse = request.build_absolute_uri(chemin) + "#" + jeton
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
