"""Administration des candidats, participations et consentements (§7.3, §16.2)."""
from django.contrib import admin, messages

from apps.audit.services import journaliser
from apps.candidats.models import Candidat, Consentement, Participation
from apps.candidats.services import inscrire
from apps.commun.admin import ROLES_ECRITURE, AdminDuClient, role_admin


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
    actions = ["admettre"]

    @admin.action(description="Admettre à concourir (candidats inscrits)")
    def admettre(self, request, queryset):
        if role_admin(request.user) not in ROLES_ECRITURE:
            self.message_user(request, "Seul le personnel du prestataire admet des candidats.", messages.ERROR)
            return
        admises = 0
        for participation in queryset.filter(statut=Participation.Statut.INSCRIT):
            participation.statut = Participation.Statut.ADMIS
            participation.save(update_fields=["statut", "modifie_le"])
            journaliser("participation.admise", organisation=participation.organisation, auteur=request.user, objet=participation,
                        details={"numero": participation.numero_candidat})
            admises += 1
        self.message_user(request, f"{admises} candidat(s) admis à concourir ; les autres (retirés ou déjà admis) n'ont pas été touchés.", messages.SUCCESS)

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
