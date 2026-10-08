# Chapitre 14 — L'administration : voir et manipuler les données

> **Étape du plan :** console provisoire (avant les écrans de gestion) · **Durée :** 2 à 3 heures · **Commit de référence :** `b3f5ae0` · **Résultat :** vous pouvez créer un client, une mission, un concours, des candidats, des jurés, des questions, des séries et des prestations **dans votre navigateur**, avec **23 tests**.

## Objectif

Jusqu'ici tout le travail était invisible : modèles, règles, services. Ce chapitre branche l'**administration Django** sur tous les modèles, pour que vous puissiez voir l'application. Ce n'est pas l'interface finale (les écrans de gestion viendront en HTMX), mais elle applique déjà les règles du projet.

## Ce qu'elle garantit

| Règle | Comment |
|---|---|
| **§6 rôles** | l'accès dépend du **rôle** : administrateur et opérateur écrivent ; le responsable client consulte et valide la configuration |
| **RM-20, règle n°3** | chaque liste est filtrée par client ; les menus déroulants aussi (impossible de rattacher une donnée à un autre client) |
| **REC-25, REC-29** | l'adresse d'une fiche d'un autre client ne divulgue rien |
| **RM-31** | seul le responsable client voit et lance « Valider la configuration » |
| **RM-27, §14.2** | l'état d'un concours, l'état d'une épreuve et les tirages ne s'écrivent pas à la main : on passe par des **actions** qui appellent les services |
| **Pas d'erreur 500** | une règle violée affiche un message rouge et n'enregistre rien |

## Décisions

| N° | Décision |
|---|---|
| D29 | Console provisoire : l'accès dépend du rôle (pas des permissions Django par modèle) ; `is_staff` est fixé à vrai à la création d'un compte. Limite connue : le cloisonnement est au niveau du client, pas encore de la mission. |
| D30 | États et tirages passent par les services (actions « Ouvrir », « Démarrer », « Valider »). Une participation se crée par `inscrire`, une série par `composer_serie`. |

## Étape A — Un petit service : démarrer un concours

Il manquait la transition « ouvert » → « en cours » (D25 : les tirages exigent un concours en cours). Ajoutez la fonction `demarrer_concours` à la fin de `apps\concours\services.py` (fichier complet ci-dessous).

**Fichier `apps\concours\services.py`**

```python
"""Règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31)."""
import hashlib
import json

from django.utils import timezone

from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.concours.models import Concours
from apps.coran.models import VersionCorpus
from apps.utilisateurs.models import Utilisateur


def _statut_actuel_du_corpus(version_id):
    """Statut lu dans la base : l'objet en mémoire peut être périmé."""
    return VersionCorpus.objects.filter(pk=version_id).values_list("statut", flat=True).first()


def _verifier_version_utilisable(version_id):
    if _statut_actuel_du_corpus(version_id) not in (
        VersionCorpus.Statut.VALIDEE,
        VersionCorpus.Statut.ACTIVE,
    ):
        raise ConfigurationInvalideError(
            "Seule une version du corpus validée ou active peut être utilisée par un concours (RM-09)."
        )


def definir_version_corpus(concours, version):
    """Rattache une version du corpus au concours ; impossible après l'ouverture (RM-27)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La version du corpus est figée à l'ouverture du concours (RM-27)."
        )
    _verifier_version_utilisable(version.pk)
    concours.version_corpus = version
    concours.save(update_fields=["version_corpus", "modifie_le"])


def problemes_de_configuration(concours):
    """Liste ce qui manque pour que la configuration soit validable (vide si tout est en ordre)."""
    categories = list(concours.categories.order_by("nom"))
    if not categories:
        return ["Le concours n'a aucune catégorie."]
    problemes = []
    for categorie in categories:
        epreuves = list(categorie.epreuves.order_by("ordre"))
        if not epreuves:
            problemes.append(f"La catégorie « {categorie.nom} » n'a aucune épreuve.")
        for epreuve in epreuves:
            if not epreuve.criteres.exists():
                problemes.append(f"L'épreuve « {epreuve.nom} » n'a aucun critère de notation.")
    return problemes


def empreinte_configuration(concours):
    """Empreinte SHA-256 de la configuration : catégories, épreuves, barème et réglages de tirage.

    Sert à détecter qu'une configuration a changé APRÈS avoir été validée (RM-31).
    """
    description = []
    for categorie in concours.categories.order_by("nom"):
        epreuves = []
        for epreuve in categorie.epreuves.order_by("ordre"):
            epreuves.append(
                {
                    "nom": epreuve.nom,
                    "ordre": epreuve.ordre,
                    "P": epreuve.questions_par_serie,
                    "T": epreuve.tirages_par_candidat,
                    "reutilisation_autre_candidat": epreuve.reutilisation_autre_candidat,
                    "reutilisation_meme_candidat_autre_epreuve": (
                        epreuve.reutilisation_meme_candidat_autre_epreuve
                    ),
                    "exclusion_definitive": epreuve.exclusion_definitive,
                    "mode_affichage": epreuve.mode_affichage,
                    "affichage_scene": epreuve.affichage_scene,
                    "criteres": [
                        {
                            "libelle": critere.libelle,
                            "ordre": critere.ordre,
                            "maximum": str(critere.maximum),
                            "coefficient": str(critere.coefficient),
                        }
                        for critere in epreuve.criteres.order_by("ordre")
                    ],
                }
            )
        description.append(
            {
                "nom": categorie.nom,
                "discipline": categorie.discipline,
                "age_minimum": categorie.age_minimum,
                "age_maximum": categorie.age_maximum,
                "effectif_prevu": categorie.effectif_prevu,
                "regle_classement": categorie.regle_classement,
                "regle_departage": categorie.regle_departage,
                "epreuves": epreuves,
            }
        )
    texte = json.dumps(description, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def valider_configuration(concours, utilisateur):
    """Le responsable du client valide la configuration du concours (RM-31, §6.2).

    Le prestataire exécute, le client valide : ni l'opérateur ni l'administrateur ne peuvent le faire.
    """
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != concours.organisation_id
    ):
        raise ValidationRefuseeError(
            "Seul le responsable du client concerné peut valider la configuration du concours."
        )
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La configuration ne se valide que pour un concours en brouillon."
        )
    problemes = problemes_de_configuration(concours)
    if problemes:
        raise ConfigurationInvalideError("Configuration incomplète : " + " ".join(problemes))
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError(
            "Aucune version du corpus n'est rattachée au concours (RM-27)."
        )
    concours.configuration_validee_par = utilisateur
    concours.configuration_validee_le = timezone.now()
    concours.configuration_empreinte = empreinte_configuration(concours)
    concours.save(
        update_fields=[
            "configuration_validee_par",
            "configuration_validee_le",
            "configuration_empreinte",
            "modifie_le",
        ]
    )


def ouvrir_concours(concours):
    """Ouvre un concours : configuration validée et inchangée, corpus validé ou actif (RM-27, RM-31)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            f"Seul un concours en brouillon peut être ouvert (état actuel : {concours.get_etat_display()})."
        )
    if concours.configuration_validee_le is None:
        raise ConfigurationInvalideError(
            "La configuration n'a pas été validée par le responsable du client (RM-31)."
        )
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError("Aucune version du corpus n'est rattachée au concours.")
    _verifier_version_utilisable(concours.version_corpus_id)
    if empreinte_configuration(concours) != concours.configuration_empreinte:
        raise ConfigurationInvalideError(
            "La configuration a changé depuis sa validation : "
            "le responsable du client doit la valider de nouveau (RM-31)."
        )
    concours.etat = Concours.Etat.OUVERT
    concours.save(update_fields=["etat", "modifie_le"])


def demarrer_concours(concours):
    """Passe un concours « ouvert » à « en cours » : les tirages deviennent possibles (D25)."""
    if concours.etat != Concours.Etat.OUVERT:
        raise ConfigurationInvalideError(
            f"Seul un concours ouvert peut démarrer (état actuel : {concours.get_etat_display()})."
        )
    concours.etat = Concours.Etat.EN_COURS
    concours.save(update_fields=["etat", "modifie_le"])
```

## Étape B — Le socle de l'administration

**Fichier `apps\commun\admin.py`**

```python
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
    OuvertureEpreuveRefuseeError,
    PrestationInvalideError,
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
```

## Étape C — Les administrations de chaque application

**Fichier `apps\clients\admin.py`**

```python
"""Administration des clients et de leurs missions (§7.1)."""
from django.contrib import admin

from apps.clients.models import Mission, Organisation
from apps.commun.admin import AdminDuClient


@admin.register(Organisation)
class OrganisationAdmin(AdminDuClient):
    champ_organisation = "pk"
    list_display = ("nom", "statut", "courriel", "telephone")
    list_filter = ("statut",)
    search_fields = ("nom",)


@admin.register(Mission)
class MissionAdmin(AdminDuClient):
    list_display = ("nom", "organisation", "lieu", "date_debut", "date_fin", "statut")
    list_filter = ("statut", "organisation")
    search_fields = ("nom", "lieu")
    date_hierarchy = "date_debut"
```

**Fichier `apps\utilisateurs\admin.py`**

```python
"""Administration des comptes et des affectations d'opérateurs (§6)."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.commun.admin import AdminDuClient, role_admin
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Réservé à l'administrateur QURANOVA.

    D29 : pendant le développement, l'administration sert de console aux trois rôles ;
    ``is_staff`` est donc fixé à vrai pour tout compte actif (l'accès réel dépend du rôle).
    """

    list_display = ("username", "role", "organisation", "is_active")
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

    def save_model(self, request, obj, form, change):
        obj.is_staff = True
        super().save_model(request, obj, form, change)


@admin.register(AffectationOperateur)
class AffectationOperateurAdmin(AdminDuClient):
    list_display = ("utilisateur", "mission", "organisation")
    list_filter = ("organisation",)
```

**Fichier `apps\concours\admin.py`**

```python
"""Administration de la configuration d'un concours (§7.2, RM-27, RM-31)."""
from django.contrib import admin

from apps.commun.admin import AdminDuClient, InlineDuClient, appliquer_action, role_admin
from apps.concours import services
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve, Session
from apps.prestations.services import ouvrir_epreuve
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
    readonly_fields = ("etat",)
    actions = ["ouvrir"]

    @admin.action(description="Ouvrir l'épreuve (lot complet et suffisant)")
    def ouvrir(self, request, queryset):
        appliquer_action(request, queryset, ouvrir_epreuve, "épreuve ouverte")


@admin.register(Session)
class SessionAdmin(AdminDuClient):
    list_display = ("nom", "concours", "date", "lieu")
    list_filter = ("concours",)
```

**Fichier `apps\candidats\admin.py`**

```python
"""Administration des candidats, participations et consentements (§7.3, §16.2)."""
from django.contrib import admin

from apps.candidats.models import Candidat, Consentement, Participation
from apps.candidats.services import inscrire
from apps.commun.admin import AdminDuClient


@admin.register(Candidat)
class CandidatAdmin(AdminDuClient):
    list_display = ("nom", "prenom", "date_naissance", "ville", "structure", "organisation")
    list_filter = ("organisation", "sexe")
    search_fields = ("nom", "prenom", "ville", "structure")


@admin.register(Participation)
class ParticipationAdmin(AdminDuClient):
    list_display = ("numero_candidat", "candidat", "categorie", "statut")
    list_filter = ("statut", "concours", "categorie")
    search_fields = ("candidat__nom", "candidat__prenom")

    def get_fields(self, request, obj=None):
        if obj is None:  # à la création, le concours et le numéro sont attribués par le service
            return ("candidat", "categorie", "statut")
        return ("candidat", "concours", "categorie", "numero_candidat", "statut")

    def get_readonly_fields(self, request, obj=None):
        return ("concours", "numero_candidat", "candidat", "categorie") if obj else ()

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)

        def creer():
            # Création : le numéro est le suivant du concours, attribué sous verrou (D17).
            participation = inscrire(obj.candidat, obj.categorie)
            if obj.statut != participation.statut:
                participation.statut = obj.statut
                participation.save(update_fields=["statut", "modifie_le"])
            obj.__dict__.update(participation.__dict__)  # l'objet affiché est celui enregistré

        self.executer_metier(request, creer)


@admin.register(Consentement)
class ConsentementAdmin(AdminDuClient):
    list_display = ("participation", "representant_nom", "date_signature", "statut")
    list_filter = ("statut",)
```

**Fichier `apps\jury\admin.py`**

```python
"""Administration des jurés (§7.4)."""
from django.contrib import admin

from apps.commun.admin import AdminDuClient, ConsultationSeule, InlineDuClient
from apps.jury.models import AffectationJury, CodeAccesJure, Jure


class AffectationInline(InlineDuClient):
    model = AffectationJury


@admin.register(Jure)
class JureAdmin(AdminDuClient):
    list_display = ("nom", "prenom", "role", "actif", "organisation")
    list_filter = ("role", "actif", "organisation")
    search_fields = ("nom", "prenom")
    inlines = [AffectationInline]


@admin.register(CodeAccesJure)
class CodeAccesJureAdmin(ConsultationSeule):
    """Les codes se génèrent par le service (le code en clair n'est jamais stocké, D23)."""

    list_display = ("jure", "session", "valide_du", "valide_jusqu_au", "revoque_le", "derniere_utilisation")
    list_filter = ("session",)
    exclude = ("empreinte",)
```

**Fichier `apps\questions\admin.py`**

```python
"""Administration des questions, lots et séries (§8.2, §8.4)."""
from django import forms
from django.contrib import admin

from apps.commun.admin import AdminDuClient, ConsultationSeule, InlineDuClient, organisations_visibles
from apps.questions import services
from apps.questions.models import Lot, PassageCoranique, Question, QuestionDeSerie, Serie


class PassageInline(InlineDuClient):
    model = PassageCoranique
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Question)
class QuestionAdmin(AdminDuClient):
    """Création d'énoncés libres. Les passages coraniques se créent par ``creer_question_passage`` :
    le service vérifie les références dans le corpus avant d'écrire (REC-05)."""

    list_display = ("__str__", "type", "version_corpus", "organisation")
    list_filter = ("type", "organisation")
    search_fields = ("enonce",)
    inlines = [PassageInline]

    def get_inlines(self, request, obj):
        return [PassageInline] if obj else []  # rien à afficher à la création

    def get_readonly_fields(self, request, obj=None):
        return ("type", "version_corpus") if obj else ()

    def get_changeform_initial_data(self, request):
        return {"type": Question.Type.ENONCE}

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "type" and "choices" not in kwargs:
            kwargs["choices"] = [(Question.Type.ENONCE, "Énoncé")]
        return super().formfield_for_choice_field(db_field, request, **kwargs)


@admin.register(Lot)
class LotAdmin(ConsultationSeule):
    list_display = ("epreuve", "organisation")


class QuestionDeSerieInline(InlineDuClient):
    model = QuestionDeSerie
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class SerieForm(forms.ModelForm):
    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Cochez exactement P questions. Elles sont rangées dans l'ordre de leur création.",
    )

    class Meta:
        model = Serie
        fields = ("lot",)


@admin.register(Serie)
class SerieAdmin(AdminDuClient):
    """Une série se compose par ``composer_serie`` (RM-22, RM-23) ; elle ne se modifie pas ensuite."""

    list_display = ("__str__", "lot", "organisation")
    list_filter = ("lot__epreuve",)
    form = SerieForm
    inlines = [QuestionDeSerieInline]

    def get_inlines(self, request, obj):
        return [QuestionDeSerieInline] if obj else []

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            visibles = organisations_visibles(request.user)
            queryset = Question.objects.order_by("cree_le")
            if visibles is not None:
                queryset = queryset.filter(organisation_id__in=visibles)
            form.base_fields["questions"].queryset = queryset
        return form

    def get_fields(self, request, obj=None):
        return ("lot", "questions") if obj is None else ("lot", "numero")

    def get_readonly_fields(self, request, obj=None):
        return ("lot", "numero") if obj else ()

    def has_change_permission(self, request, obj=None):
        return False if obj else super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        def composer():
            serie = services.composer_serie(obj.lot, form.cleaned_data["questions"].order_by("cree_le"))
            obj.__dict__.update(serie.__dict__)  # l'objet affiché est celui enregistré

        self.executer_metier(request, composer)
```

**Fichier `apps\prestations\admin.py`**

```python
"""Administration des prestations et des tirages (§8.3, §14.2)."""
from django.contrib import admin

from apps.commun.admin import AdminDuClient, ConsultationSeule
from apps.prestations.models import Prestation, Tirage


@admin.register(Prestation)
class PrestationAdmin(AdminDuClient):
    list_display = ("rang_passage", "participation", "epreuve", "session", "etat")
    list_filter = ("etat", "epreuve", "session")
    readonly_fields = ("etat",)  # l'état ne change que par les services (tirage, diaporama, notation)


@admin.register(Tirage)
class TirageAdmin(ConsultationSeule):
    """Un tirage ne se crée que par ``effectuer_tirage`` et ne s'annule que par ``annuler_tirage`` (§14.2)."""

    list_display = ("prestation", "serie", "rang", "statut", "terminal", "cree_le")
    list_filter = ("statut", "prestation__epreuve")
```

## Étape D — Les tests

**Fichier `apps\commun\tests\test_admin.py`**

```python
"""Tests de l'administration : accès par rôle, cloisonnement des clients (RM-20, REC-25, REC-29),
tirages protégés, règles métier signalées sans erreur 500."""
import pytest
from django.contrib import admin
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.candidats.models import Candidat, Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_mission,
    creer_organisation,
    creer_participation,
    creer_session,
    creer_utilisateur,
)
from apps.concours.models import Concours
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage
from apps.questions.models import Question, Serie
from apps.questions.services import obtenir_lot
from apps.questions.tests.outils import creer_question
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def url(modele, action, *args):
    return reverse(f"admin:{modele._meta.app_label}_{modele._meta.model_name}_{action}", args=args)


def messages_de(reponse):
    return " | ".join(str(m) for m in get_messages(reponse.wsgi_request))


@pytest.fixture
def administrateur(db, client):
    utilisateur = Utilisateur.objects.create_superuser("admin-test", password="x")
    client.force_login(utilisateur)
    return utilisateur


def operateur_de(mission, client):
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)
    client.force_login(operateur)
    return operateur


# --- Pages ---------------------------------------------------------------------


@pytest.mark.django_db
def test_toutes_les_listes_de_l_administration_s_affichent(administrateur, client):
    creer_epreuve_ouverte(series=2)
    for modele in admin.site._registry:
        reponse = client.get(url(modele, "changelist"))
        assert reponse.status_code == 200, modele


@pytest.mark.django_db
def test_les_formulaires_de_creation_s_affichent(administrateur, client):
    for modele, model_admin in admin.site._registry.items():
        if model_admin.has_add_permission(type("R", (), {"user": administrateur})()):
            assert client.get(url(modele, "add")).status_code == 200, modele


# --- Accès par rôle ------------------------------------------------------------


@pytest.mark.django_db
def test_un_anonyme_est_renvoye_vers_la_connexion(client):
    reponse = client.get(url(Concours, "changelist"))

    assert reponse.status_code == 302 and "login" in reponse.url


@pytest.mark.django_db
def test_un_responsable_client_consulte_sans_pouvoir_ecrire(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    client.force_login(responsable)

    assert client.get(url(Concours, "changelist")).status_code == 200
    assert client.get(url(Concours, "add")).status_code == 403
    assert client.get(url(Candidat, "add")).status_code == 403


@pytest.mark.django_db
def test_un_utilisateur_inactif_ou_hors_equipe_n_entre_pas(client):
    sans_acces = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=False)
    client.force_login(sans_acces)

    assert client.get(url(Concours, "changelist")).status_code == 302


@pytest.mark.django_db
def test_seul_l_administrateur_gere_les_comptes(client):
    client.force_login(creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True))
    assert client.get(url(Utilisateur, "changelist")).status_code == 403


@pytest.mark.django_db
def test_un_compte_cree_dans_l_administration_peut_se_connecter_a_l_administration(administrateur, client):
    reponse = client.post(
        url(Utilisateur, "add"),
        {"username": "nouvel-operateur", "password1": "Mot-de-passe-solide-42", "password2": "Mot-de-passe-solide-42",
         "role": "operateur"},
    )

    assert reponse.status_code == 302
    assert Utilisateur.objects.get(username="nouvel-operateur").is_staff is True


# --- Cloisonnement des clients -------------------------------------------------


@pytest.mark.django_db
def test_rm20_un_operateur_ne_voit_que_les_donnees_de_ses_clients(client):
    mission = creer_mission()
    mien = creer_candidat(mission.organisation, nom="Visible")
    autre = creer_candidat(creer_organisation(), nom="Invisible")
    operateur_de(mission, client)

    reponse = client.get(url(Candidat, "changelist"))

    contenu = reponse.content.decode()
    assert "Visible" in contenu and "Invisible" not in contenu
    assert client.get(url(Candidat, "change", mien.pk)).status_code == 200


@pytest.mark.django_db
def test_rec25_rec29_un_identifiant_d_un_autre_client_n_est_pas_accessible(client):
    mission = creer_mission()
    autre = creer_candidat(creer_organisation())
    operateur_de(mission, client)

    reponse = client.get(url(Candidat, "change", autre.pk), follow=True)

    assert "Invisible" not in reponse.content.decode()
    assert reponse.redirect_chain  # renvoyé vers la liste, sans rien divulguer
    assert client.post(url(Candidat, "delete", autre.pk), {"post": "yes"}).status_code in (302, 404)
    assert Candidat.objects.filter(pk=autre.pk).exists()


@pytest.mark.django_db
def test_un_responsable_client_ne_voit_que_sa_propre_organisation(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    creer_concours(creer_mission(responsable.organisation), nom="Concours-Mien")
    creer_concours(creer_mission(), nom="Concours-Etranger")
    client.force_login(responsable)

    contenu = client.get(url(Concours, "changelist")).content.decode()

    assert "Concours-Mien" in contenu and "Concours-Etranger" not in contenu


@pytest.mark.django_db
def test_les_menus_deroulants_ne_proposent_pas_les_donnees_d_un_autre_client(client):
    mission = creer_mission()
    categorie = creer_categorie(creer_concours(mission))
    creer_candidat(mission.organisation, nom="Candidat-Mien")
    creer_candidat(creer_organisation(), nom="Candidat-Etranger")
    operateur_de(mission, client)

    contenu = client.get(url(Participation, "add")).content.decode()

    assert "Candidat-Mien" in contenu and "Candidat-Etranger" not in contenu


# --- Règles protégées ----------------------------------------------------------


@pytest.mark.django_db
def test_un_tirage_ne_s_ecrit_ni_ne_s_efface_dans_l_administration(administrateur, client):
    epreuve = creer_epreuve_ouverte(series=1)
    tirage = creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get())

    assert client.get(url(Tirage, "add")).status_code == 403
    assert client.post(url(Tirage, "delete", tirage.pk), {"post": "yes"}).status_code == 403
    assert client.get(url(Tirage, "change", tirage.pk)).status_code == 200  # consultation
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_l_etat_d_un_concours_ne_se_change_pas_a_la_main(administrateur, client):
    concours = creer_concours(nom="Brouillon")

    client.post(
        url(Concours, "change", concours.pk),
        {"mission": concours.mission_id, "nom": "Brouillon", "edition": "2027", "format": "presentiel",
         "date_debut": "2027-01-20", "date_fin": "2027-01-21", "etat": "en_cours"},
    )

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.BROUILLON


@pytest.mark.django_db
def test_l_administrateur_ne_valide_pas_la_configuration(administrateur, client):
    reponse = client.post(
        url(Concours, "changelist"), {"action": "valider_la_configuration", "_selected_action": []}, follow=True
    )

    assert "Valider la configuration" not in reponse.content.decode()


@pytest.mark.django_db
def test_le_responsable_client_valide_la_configuration_depuis_l_administration(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    concours = creer_concours(creer_mission(responsable.organisation))
    client.force_login(responsable)

    reponse = client.post(
        url(Concours, "changelist"),
        {"action": "valider_la_configuration", "_selected_action": [str(concours.pk)]},
        follow=True,
    )

    assert reponse.status_code == 200
    assert "Configuration incomplète" in messages_de(reponse)  # aucune catégorie : refus lisible, pas d'erreur 500


# --- Règles métier : message, pas d'erreur 500 ---------------------------------


@pytest.mark.django_db
def test_une_regle_metier_violee_donne_un_message_et_rien_n_est_enregistre(administrateur, client):
    epreuve = creer_epreuve_ouverte(series=1)
    autre_categorie = creer_categorie(epreuve.categorie.concours)
    participation = creer_participation(autre_categorie)  # pas la catégorie de l'épreuve
    session = creer_session(epreuve.categorie.concours)

    reponse = client.post(
        url(Prestation, "add"),
        {"participation": participation.pk, "epreuve": epreuve.pk, "session": session.pk, "rang_passage": 1},
        follow=True,
    )

    assert reponse.status_code == 200
    assert "catégorie" in messages_de(reponse)
    assert Prestation.objects.count() == 0


@pytest.mark.django_db
def test_une_contrainte_de_base_donne_un_message(administrateur, client):
    mission = creer_mission()
    creer_concours(mission, nom="Doublon", edition="2027")

    reponse = client.post(
        url(Concours, "add"),
        {"mission": mission.pk, "nom": "Doublon", "edition": "2027", "format": "presentiel",
         "date_debut": "2027-01-20", "date_fin": "2027-01-21"},
        follow=True,
    )

    assert reponse.status_code == 200
    assert Concours.objects.filter(nom="Doublon").count() == 1


@pytest.mark.django_db
def test_une_participation_creee_dans_l_administration_recoit_son_numero(administrateur, client):
    concours = creer_concours()
    categorie = creer_categorie(concours)
    creer_participation(categorie, numero_candidat=41)
    candidat = creer_candidat(concours.organisation)

    reponse = client.post(
        url(Participation, "add"),
        {"candidat": candidat.pk, "categorie": categorie.pk, "statut": "admis"},
        follow=True,
    )

    assert reponse.status_code == 200
    participation = Participation.objects.get(candidat=candidat)
    assert participation.numero_candidat == 42 and participation.statut == "admis"
    assert participation.concours == concours


@pytest.mark.django_db
def test_une_serie_se_compose_dans_l_administration_avec_exactement_p_questions(administrateur, client):
    epreuve = creer_epreuve_ouverte(series=0, p=2)
    lot = obtenir_lot(epreuve)
    q1, q2, q3 = (creer_question(epreuve.organisation) for _ in range(3))

    refus = client.post(url(Serie, "add"), {"lot": lot.pk, "questions": [q1.pk]}, follow=True)
    assert "exactement 2" in messages_de(refus) and Serie.objects.count() == 0

    succes = client.post(url(Serie, "add"), {"lot": lot.pk, "questions": [q2.pk, q1.pk]}, follow=True)
    assert succes.status_code == 200
    serie = Serie.objects.get()
    assert [x.question for x in serie.questions_ordonnees.all()] == [q1, q2]  # ordre de création


@pytest.mark.django_db
def test_une_question_enonce_se_cree_dans_l_administration(administrateur, client):
    organisation = creer_organisation()

    client.post(
        url(Question, "add"),
        {"organisation": organisation.pk, "type": "enonce", "enonce": "Quel est le sens d'al-Fatiha ?"},
    )

    assert Question.objects.get().type == Question.Type.ENONCE


@pytest.mark.django_db
def test_demarrer_un_concours_ouvert(administrateur, client):
    from apps.concours.services import demarrer_concours

    epreuve = creer_epreuve_ouverte(series=1)
    Concours.objects.filter(pk=epreuve.categorie.concours_id).update(etat=Concours.Etat.OUVERT)
    concours = Concours.objects.get(pk=epreuve.categorie.concours_id)

    demarrer_concours(concours)

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.EN_COURS


@pytest.mark.django_db
def test_demarrer_refuse_un_concours_qui_n_est_pas_ouvert():
    from apps.concours.exceptions import ConfigurationInvalideError
    from apps.concours.services import demarrer_concours

    with pytest.raises(ConfigurationInvalideError):
        demarrer_concours(creer_concours())


@pytest.mark.django_db
def test_ouvrir_une_epreuve_signale_la_regle_non_ecrite_sans_erreur_500(administrateur, client):
    """Tant que ``series_necessaires`` (TODO(human)) n'est pas écrite, l'action explique et ne plante pas."""
    from apps.concours.models import Epreuve
    from apps.prestations import services

    epreuve = creer_epreuve_ouverte(series=2, etat=Epreuve.Etat.EN_PREPARATION)
    original = services.series_necessaires

    def non_ecrite(*args, **kwargs):
        raise NotImplementedError("TODO(human) : contrôle de suffisance")

    services.series_necessaires = non_ecrite
    try:
        reponse = client.post(
            url(Epreuve, "changelist"),
            {"action": "ouvrir", "_selected_action": [str(epreuve.pk)]},
            follow=True,
        )
    finally:
        services.series_necessaires = original

    assert reponse.status_code == 200 and "TODO(human)" in messages_de(reponse)
```

```powershell
pytest apps\commun\tests\test_admin.py
```

Attendu : `23 passed`.

## Étape E — Regarder l'application

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Ouvrez <http://127.0.0.1:8000/admin/> et connectez-vous. Parcours conseillé :

1. **Organisations** → créez un client (« Association Test »).
2. **Missions** → créez une mission pour ce client.
3. **Concours** → créez un concours (version du corpus : laissez vide pour l'instant, ou choisissez celle que vous avez importée).
4. **Catégories**, puis **Épreuves** (avec P = 1 pour commencer) et leurs **critères de notation** (tableau en bas de la fiche épreuve).
5. **Candidats** → créez-en quelques-uns, ou utilisez `python manage.py importer_candidats <uuid> fichier.csv`.
6. **Participations** → inscrivez un candidat à une catégorie : le numéro est attribué tout seul.
7. **Questions** → créez des énoncés ; **Séries** → cochez exactement P questions.
8. **Jurés** → créez un juré et affectez-le à une épreuve (tableau en bas de la fiche).

> **Pour aller jusqu'au tirage**, il faut un concours *en cours*, donc un corpus **validé** : écrivez d'abord les règles du chapitre 04 (`verifier_transition_statut`, `verifier_ecriture_autorisee`) et validez le corpus (jalon J0). Ensuite : le responsable client valide la configuration, puis les actions « Ouvrir le concours » et « Démarrer le concours ». Il faut aussi écrire `series_necessaires` et `series_admissibles` (chapitre 13).

### Créer les comptes de test

Dans **Utilisateurs** (réservé à l'administrateur) : un **opérateur** (puis une **affectation d'opérateur** à la mission) et un **responsable client** rattaché à l'organisation. Connectez-vous avec chacun dans une fenêtre de navigation privée : constatez que le responsable ne voit que son client et ne peut rien créer, et que l'opérateur ne voit que ses missions.

## Questions de compréhension

1. Pourquoi l'état d'un concours est-il en lecture seule dans le formulaire, alors que le champ existe en base ?
2. Pourquoi cacher le bouton « Valider la configuration » à l'administrateur ne suffit-il pas, et où le refus est-il réellement appliqué ?
3. Que se passerait-il si on ne filtrait que les listes, mais pas les menus déroulants ?

<details>
<summary>Réponses</summary>

1. Pour qu'il ne change que par les services, qui vérifient les conditions (configuration validée, corpus figé, empreinte inchangée : RM-27, RM-31).
2. Masquer une action ne protège rien (règle n°4). Le refus est appliqué par `valider_configuration`, qui exige que l'utilisateur soit le responsable du client concerné.
3. Un opérateur pourrait choisir, dans le menu d'une participation, un candidat d'un autre client : la donnée serait rattachée de travers. Le filtre des menus complète celui des listes, et `ModeleDuClient` refuse l'incohérence en dernier recours.
</details>

## Journal d'apprentissage

Notez trois choses que vous avez réussi à faire dans l'administration, et une que le système vous a refusée avec son message.

## Commit proposé

```text
Administration : console provisoire par rôle, cloisonnée par client
```
