from django.urls import path

from apps.presentation import views

app_name = "presentation"

urlpatterns = [
    path("scene/<uuid:session_id>/", views.ecran_scene, name="ecran_scene"),
    path("commande/<uuid:session_id>/", views.ecran_commande, name="ecran_commande"),
    path("api/operateur/session/<uuid:session_id>/prestations/", views.prestations_de_la_session, name="prestations"),
]
