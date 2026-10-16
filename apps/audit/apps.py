from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
    verbose_name = "Journal d'audit"

    def ready(self):
        from apps.audit import signaux  # noqa: F401  (branche l'enregistrement des connexions)
