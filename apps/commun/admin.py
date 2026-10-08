"""Socle de l'administration : accès par rôle, cloisonnement par client, erreurs métier lisibles.

Pendant les phases de développement, l'administration Django sert de console provisoire
(les vrais écrans de gestion viendront ensuite). Elle applique déjà les règles du projet :

- l'accès dépend du RÔLE (§6), pas des permissions Django par modèle ;
- chaque liste est filtrée par client (règle absolue n°3, RM-20), y compris les menus
  déroulants des formulaires, pour qu'on ne puisse pas rattacher une donnée à un autre client ;
- une règle métier violée donne un message d'erreur, jamais une page d'erreur 500.
"""
from django.contrib import admin, messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect

from apps.candidats.exceptions import ParticipationInvalideError, TirageImpossibleError
from apps.clients.models import Organisation
from apps.commun.exceptions import IncoherenceOrganisationError
from apps.commun.models import ModeleDuClient
from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.jury.exceptions import AffectationInvalideError as AffectationJuryInvalideError
from apps.prestations.exceptions import (
    AnnulationInvalideError,
    AppelInvalideError,
    OuvertureEpreuveRefuseeError,
    PrestationInvalideError,
    TerminalInvalideError,
    TirageInvalideError,
)
from apps.questions.exceptions import QuestionInvalideError, SerieInvalideError
from apps.utilisateurs.exceptions import AffectationInvalideError
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

ERREURS_METIER = (
    IncoherenceOrganisationError,
    ParticipationInvalideError,
    TirageImpossibleError,
    ConfigurationInvalideError,
    ValidationRefuseeError,
    AffectationInvalideError,
    AffectationJuryInvalideError,
    PrestationInvalideError,
    TirageInvalideError,
    AnnulationInvalideError,
    AppelInvalideError,
    OuvertureEpreuveRefuseeError,
    QuestionInvalideError,
    SerieInvalideError,
    IntegrityError,
)

ROLES_ECRITURE = (Utilisateur.Role.ADMINISTRATEUR, Utilisateur.Role.OPERATEUR)
ROLES_LECTURE = ROLES_ECRITURE + (Utilisateur.Role.RESPONSABLE_CLIENT,)


def role_admin(utilisateur):
    """Le rôle effectif dans l'administration, ou ``None`` si l'accès est refusé."""
    if not (utilisateur.is_active and utilisateur.is_staff):
        return None
    if utilisateur.is_superuser:
        return Utilisateur.Role.ADMINISTRATEUR
    return utilisateur.role


def organisations_visibles(utilisateur):
    """``None`` = toutes les organisations ; sinon l'ensemble des identifiants autorisés (RM-20)."""
    role = role_admin(utilisateur)
    if role == Utilisateur.Role.ADMINISTRATEUR:
        return None
    if role == Utilisateur.Role.RESPONSABLE_CLIENT:
        return {utilisateur.organisation_id}
    if role == Utilisateur.Role.OPERATEUR:
        return set(missions_accessibles(utilisateur).values_list("organisation_id", flat=True))
    return set()


class AdminDuClient(admin.ModelAdmin):
    """Base de toute administration d'une table client."""

    champ_organisation = "organisation"  # pour Organisation : "pk"

    # --- accès par rôle ---
    def has_module_permission(self, request):
        return role_admin(request.user) in ROLES_LECTURE

    def has_view_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_LECTURE

    def has_add_permission(self, request):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_change_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_delete_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    # --- cloisonnement par client ---
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        visibles = organisations_visibles(request.user)
        if visibles is None:
            return queryset
        return queryset.filter(**{f"{self.champ_organisation}__in": visibles})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        visibles = organisations_visibles(request.user)
        cible = db_field.remote_field.model
        if visibles is not None and "queryset" not in kwargs:
            if issubclass(cible, ModeleDuClient):
                kwargs["queryset"] = cible._default_manager.filter(organisation_id__in=visibles)
            elif cible is Organisation:
                kwargs["queryset"] = Organisation.objects.filter(pk__in=visibles)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        # L'organisation d'une donnée dépendante est recopiée de son parent (ModeleDuClient).
        if getattr(self.model, "PARENTS_CLIENT", ()):
            exclude.append("organisation")
        return exclude

    # --- erreurs métier : un message, pas une erreur 500 ---
    def executer_metier(self, request, fonction):
        """Exécute ``fonction`` ; une règle métier violée devient un message, et rien n'est enregistré."""
        try:
            with transaction.atomic():
                fonction()
        except ERREURS_METIER as erreur:
            messages.error(request, f"Enregistrement refusé : {erreur}")
            request._echec_metier = True

    def save_model(self, request, obj, form, change):
        self.executer_metier(request, lambda: super(AdminDuClient, self).save_model(request, obj, form, change))

    def save_related(self, request, form, formsets, change):
        if not getattr(request, "_echec_metier", False):
            super().save_related(request, form, formsets, change)

    def response_add(self, request, obj, post_url_continue=None):
        if getattr(request, "_echec_metier", False):
            return HttpResponseRedirect(request.get_full_path())
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if getattr(request, "_echec_metier", False):
            return HttpResponseRedirect(request.get_full_path())
        return super().response_change(request, obj)


class InlineDuClient(admin.TabularInline):
    """Base des tableaux imbriqués : même cloisonnement et mêmes exclusions."""

    extra = 0

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        visibles = organisations_visibles(request.user)
        cible = db_field.remote_field.model
        if visibles is not None and "queryset" not in kwargs and issubclass(cible, ModeleDuClient):
            kwargs["queryset"] = cible._default_manager.filter(organisation_id__in=visibles)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if getattr(self.model, "PARENTS_CLIENT", ()):
            exclude.append("organisation")
        return exclude

    def has_view_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_LECTURE

    def has_add_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_change_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE

    def has_delete_permission(self, request, obj=None):
        return role_admin(request.user) in ROLES_ECRITURE


class ConsultationSeule(AdminDuClient):
    """Une donnée qui se consulte mais ne s'écrit que par les services (ex. un tirage, §14.2)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def appliquer_action(request, queryset, fonction, succes):
    """Applique un service à chaque objet sélectionné ; un message par succès ou par refus."""
    for objet in queryset:
        try:
            with transaction.atomic():
                fonction(objet)
        except (*ERREURS_METIER, NotImplementedError) as erreur:
            messages.error(request, f"{objet} : {erreur}")
        else:
            messages.success(request, f"{objet} : {succes}.")
