"""Routes racine du projet QURANOVA."""
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
