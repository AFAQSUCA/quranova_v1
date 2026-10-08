"""Administration du corpus coranique : consultation seulement (§12.1, §12.3, §14.2).

Le texte coranique vient uniquement du fichier Tanzil, par la commande d'import.
Personne, pas même un superutilisateur, ne peut l'ajouter, le modifier ni le
supprimer depuis l'interface d'administration.
"""
from django.contrib import admin

from apps.coran.models import Sourate, Verset, VersionCorpus


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
