"""Le journal d'audit se consulte ; il ne s'écrit que par ``journaliser`` (§15.2)."""
from django.contrib import admin

from apps.audit.models import EntreeAudit
from apps.commun.admin import ConsultationSeule


@admin.register(EntreeAudit)
class EntreeAuditAdmin(ConsultationSeule):
    list_display = ("numero", "horodatage", "action", "auteur", "auteur_libelle", "objet_type", "terminal")
    list_filter = ("action", "organisation")
    search_fields = ("action", "objet_id", "auteur_libelle")
    date_hierarchy = "horodatage"
