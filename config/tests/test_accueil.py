"""Test « smoke » : vérifie que le projet démarre et que la page d'accueil répond."""
from django.urls import reverse


def test_page_accueil_repond(client):
    reponse = client.get(reverse("accueil"))

    assert reponse.status_code == 200
    assert "QURANOVA" in reponse.content.decode()
