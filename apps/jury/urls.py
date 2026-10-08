from django.urls import path

from apps.jury import api, views

app_name = "jury"

urlpatterns = [
    path("jury/<uuid:session_id>/", views.ecran_jury, name="ecran_jury"),
    path("api/jury/<uuid:session_id>/connexion/", api.ouvrir, name="api_connexion"),
    path("api/jury/<uuid:session_id>/prestations/", api.prestations, name="api_prestations"),
    path("api/jury/<uuid:session_id>/prestations/<uuid:prestation_id>/evaluation/", api.evaluation, name="api_evaluation"),
    path("api/jury/<uuid:session_id>/prestations/<uuid:prestation_id>/evaluation/valider/", api.valider, name="api_valider"),
    path("api/jury/<uuid:session_id>/prestations/<uuid:prestation_id>/evaluation/correction/", api.correction, name="api_correction"),
]
