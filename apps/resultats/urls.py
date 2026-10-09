from django.urls import path

from apps.resultats import views

app_name = "resultats"

urlpatterns = [
    path("documents/pv/<uuid:concours_id>/", views.proces_verbal, name="proces_verbal"),
    path("documents/pv/<uuid:concours_id>/pdf/", views.proces_verbal_pdf, name="proces_verbal_pdf"),
    path("documents/classements/<uuid:concours_id>/pdf/", views.classements_pdf, name="classements_pdf"),
    path("documents/export/<uuid:concours_id>/", views.export, name="export"),
]
