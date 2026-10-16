from django.urls import path

from apps.candidats import views

app_name = "candidats"

urlpatterns = [
    path("documents/modele-candidats/<uuid:concours_id>/", views.modele_import, name="modele_import"),
]
