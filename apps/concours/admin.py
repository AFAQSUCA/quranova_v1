"""Administration de la configuration d'un concours (§7.2, RM-27, RM-31)."""
import os
import tempfile

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse

from apps.candidats.importation import importer_candidats
from apps.commun.admin import ERREURS_METIER, AdminDuClient, InlineDuClient, appliquer_action, role_admin
from django.db import transaction
from apps.concours import polices, services
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from apps.coran.models import Verset
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.prestations.services import ouvrir_epreuve
from apps.resultats import services as services_resultats
from apps.resultats import validation
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles


TAILLE_MAXIMALE_IMPORT = 5 * 1024 * 1024  # 5 Mo : très au-dessus d'un fichier de 500 candidats


class ImportCandidatsForm(forms.Form):
    """Téléversement d'un fichier CSV de candidats (§7.3) ; la simulation est cochée par défaut."""

    fichier = forms.FileField(label="Fichier CSV des candidats", help_text="Séparateur « ; », UTF-8 ou Windows-1252. Utilisez le modèle fourni au client.")
    simuler = forms.BooleanField(required=False, initial=True, label="Simuler seulement (contrôler le fichier sans rien enregistrer)")

    def clean_fichier(self):
        fichier = self.cleaned_data["fichier"]
        if fichier.size == 0:
            raise forms.ValidationError("Le fichier est vide.")
        if fichier.size > TAILLE_MAXIMALE_IMPORT:
            raise forms.ValidationError("Le fichier est trop volumineux (5 Mo au plus).")
        return fichier


class DuplicationForm(forms.Form):
    """Paramètres de la nouvelle édition (REC-02)."""

    nom = forms.CharField(max_length=200)
    edition = forms.CharField(max_length=50, label="Édition", help_text="Millésime ou numéro d'édition de la copie.")
    date_debut = forms.DateField(label="Date de début", widget=forms.DateInput(attrs={"type": "date"}))
    date_fin = forms.DateField(label="Date de fin", widget=forms.DateInput(attrs={"type": "date"}))
    mission = forms.ModelChoiceField(queryset=None, label="Mission", help_text="Une mission du même client.")

    def __init__(self, *args, source, utilisateur, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mission"].queryset = missions_accessibles(utilisateur).filter(organisation=source.organisation)
        self.fields["mission"].initial = source.mission_id
        self.fields["nom"].initial = source.nom


@admin.register(Concours)
class ConcoursAdmin(AdminDuClient):
    list_display = ("nom", "edition", "mission", "etat", "version_corpus", "configuration_validee_le")
    list_filter = ("etat", "organisation")
    search_fields = ("nom", "edition")
    actions = ["valider_la_configuration", "ouvrir", "demarrer", "dupliquer", "importer_les_candidats"]

    def get_readonly_fields(self, request, obj=None):
        # L'état et la validation ne changent que par les services (RM-27, RM-31, D14).
        lecture = ["etat", "configuration_validee_par", "configuration_validee_le", "configuration_empreinte", "documents", "apercu_police"]
        if obj is not None and obj.etat != Concours.Etat.BROUILLON:
            lecture.append("version_corpus")  # figée à l'ouverture (RM-27)
        return lecture

    def get_fieldsets(self, request, obj=None):
        """Les réglages d'affichage du texte arabe forment une section à part, avec un aperçu."""
        champs_police = ("police_arabe", "police_arabe_fichier", "taille_texte_arabe", "apercu_police")
        sections = []
        for titre, options in super().get_fieldsets(request, obj):
            reste = tuple(c for c in options["fields"] if c not in champs_police)
            sections.append((titre, {**options, "fields": reste}))
        sections.append(("Affichage du texte arabe (scène, jury, commande)", {
            "fields": champs_police,
            "description": "Réglage visuel seulement : le texte des versets reste exactement celui du corpus importé.",
        }))
        return sections

    @admin.display(description="Aperçu")
    def apercu_police(self, obj):
        """Premier verset du corpus du concours, rendu avec les réglages ENREGISTRÉS (le texte vient du corpus, jamais saisi)."""
        if obj is None or obj.pk is None:
            return "Enregistrez le concours pour voir l'aperçu."
        if not obj.version_corpus_id:
            return "Choisissez d'abord la version du corpus : l'aperçu utilise son premier verset."
        verset = Verset.objects.filter(sourate__version_id=obj.version_corpus_id).order_by("sourate__numero", "numero").first()
        if verset is None:
            return "Cette version du corpus ne contient aucun verset."
        t = polices.typographie(obj)
        # Le CSS ne contient que des constantes, un nombre borné et une adresse vérifiée (voir apps/concours/polices.py).
        css_sur = mark_safe(polices.css(obj))  # nosec B703 B308
        return format_html(
            '<style>{}</style><p lang="ar" dir="rtl" style="font-family: var(--police-coran); font-size: {}px; line-height: 1.95; margin: 0;">{}</p>'
            '<p class="help">Verset {}:{} — tel qu\'il sera affiché (taille de la scène à {} %).</p>',
            css_sur, round(32 * t["echelle"]), verset.texte, verset.sourate.numero, verset.numero, round(t["echelle"] * 100),
        )

    @admin.display(description="Documents à remettre")
    def documents(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        return format_html(
            '<a href="{}" target="_blank">Procès-verbal (imprimable)</a> · <a href="{}">Procès-verbal (PDF)</a> · '
            '<a href="{}">Classements par catégorie (PDF)</a> · <a href="{}">Export des données (CSV)</a> · '
            '<a href="{}">Modèle d\'import des candidats (CSV)</a>',
            reverse("resultats:proces_verbal", args=[obj.pk]), reverse("resultats:proces_verbal_pdf", args=[obj.pk]),
            reverse("resultats:classements_pdf", args=[obj.pk]), reverse("resultats:export", args=[obj.pk]),
            reverse("candidats:modele_import", args=[obj.pk]),
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if role_admin(request.user) == Utilisateur.Role.RESPONSABLE_CLIENT:
            return {"valider_la_configuration": actions["valider_la_configuration"]}
        actions.pop("valider_la_configuration", None)  # le client valide, le prestataire exécute
        return actions

    @admin.action(description="Importer des candidats (fichier CSV)")
    def importer_les_candidats(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Sélectionnez un seul concours.", messages.ERROR)
            return None
        concours = queryset.get()
        if role_admin(request.user) not in (Utilisateur.Role.ADMINISTRATEUR, Utilisateur.Role.OPERATEUR):
            self.message_user(request, "Seul le personnel du prestataire importe des candidats.", messages.ERROR)
            return None
        soumis = request.POST.get("appliquer")
        formulaire = ImportCandidatsForm(request.POST if soumis else None, request.FILES if soumis else None)
        contexte = {**self.admin_site.each_context(request), "title": "Importer des candidats", "concours": concours, "form": formulaire, "opts": self.model._meta}
        if soumis and formulaire.is_valid():
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temporaire:
                for morceau in formulaire.cleaned_data["fichier"].chunks():
                    temporaire.write(morceau)
            try:
                rapport = importer_candidats(concours, temporaire.name, simuler=formulaire.cleaned_data["simuler"], auteur=request.user)
            finally:
                os.unlink(temporaire.name)
            return TemplateResponse(request, "admin/concours/import_candidats_rapport.html", {**contexte, "rapport": rapport})
        return TemplateResponse(request, "admin/concours/import_candidats.html", contexte)

    @admin.action(description="Dupliquer vers une nouvelle édition")
    def dupliquer(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Sélectionnez un seul concours à dupliquer.", messages.ERROR)
            return None
        source = queryset.get()
        formulaire = DuplicationForm(
            request.POST if request.POST.get("appliquer") else None, source=source, utilisateur=request.user
        )
        if request.POST.get("appliquer") and formulaire.is_valid():
            d = formulaire.cleaned_data
            try:
                with transaction.atomic():
                    resultat = services.dupliquer_concours(
                        source, auteur=request.user, nom=d["nom"], edition=d["edition"], date_debut=d["date_debut"],
                        date_fin=d["date_fin"], mission=d["mission"],
                    )
            except ERREURS_METIER as erreur:
                formulaire.add_error(None, str(erreur))
            else:
                self.message_user(
                    request,
                    f"Copie créée : {resultat.categories} catégorie(s), {resultat.epreuves} épreuve(s), {resultat.criteres} critère(s), "
                    f"{resultat.series} série(s). Validation de la configuration à refaire.",
                    messages.SUCCESS,
                )
                for avertissement in resultat.avertissements:
                    self.message_user(request, avertissement, messages.WARNING)
                return HttpResponseRedirect(reverse("admin:concours_concours_change", args=[resultat.concours.pk]))
        return TemplateResponse(
            request, "admin/concours/dupliquer.html",
            {**self.admin_site.each_context(request), "title": "Dupliquer un concours", "source": source, "form": formulaire, "opts": self.model._meta},
        )

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
    readonly_fields = ("fiches_de_secours",)

    @admin.display(description="Fiches de notation de secours")
    def fiches_de_secours(self, obj):
        if obj is None or obj.pk is None:
            return "—"
        return format_html(
            '<a href="{}" target="_blank">Imprimer (une fiche par prestation et par juré)</a> · <a href="{}">PDF</a>',
            reverse("jury:fiches_secours", args=[obj.pk]), reverse("jury:fiches_secours_pdf", args=[obj.pk]),
        )
