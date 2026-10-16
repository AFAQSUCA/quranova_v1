from django.urls import path

from apps.utilisateurs import views

app_name = "utilisateurs"

urlpatterns = [
    path("compte/2fa/", views.verification_2fa, name="verification_2fa"),
]
