from django.urls import path

from apps.coran import views

app_name = "coran"

urlpatterns = [
    path("documents/corpus/<int:version_id>/pv/", views.proces_verbal, name="proces_verbal"),
    path("documents/corpus/<int:version_id>/pv/pdf/", views.proces_verbal_pdf, name="proces_verbal_pdf"),
]
