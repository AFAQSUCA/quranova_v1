"""Routes racine du projet QURANOVA."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="accueil.html"), name="accueil"),
    path("admin/", admin.site.urls),
    path("", include("apps.prestations.urls")),
    path("", include("apps.presentation.urls")),
    path("", include("apps.jury.urls")),
    path("", include("apps.resultats.urls")),
]

if settings.DEBUG:
    # En développement seulement : Django sert les logos téléversés. En production, c'est Nginx (phase 3).
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from apps.utilisateurs.formulaires import FormulaireConnexionAdmin  # noqa: E402

admin.site.login_form = FormulaireConnexionAdmin
admin.site.site_header = "QURANOVA — Administration"
admin.site.site_title = "QURANOVA"
admin.site.index_title = "Gestion des concours"
