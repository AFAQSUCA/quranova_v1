from django.urls import path
from django.views.generic import TemplateView

from apps.prestations import api

app_name = "prestations"

urlpatterns = [
    path("tirage/", TemplateView.as_view(template_name="tirage.html"), name="ecran_tirage"),
    path("api/tirage/etat/", api.etat, name="api_etat"),
    path("api/tirage/", api.tirer, name="api_tirer"),
]
