from django.urls import path

from apps.resultats import views

app_name = "resultats"

urlpatterns = [
    path("documents/pv/<uuid:concours_id>/", views.proces_verbal, name="proces_verbal"),
    path("documents/export/<uuid:concours_id>/", views.export, name="export"),
]
