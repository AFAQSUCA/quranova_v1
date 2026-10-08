"""Identité visuelle : logo et couleurs du client sur les écrans et le procès-verbal ; QURANOVA reste discret."""
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.clients.marque import marque_du_client
from apps.commun.tests.outils import creer_concours, creer_mission, creer_organisation, creer_session


def test_la_marque_sans_logo_ni_couleur_est_vide(db):
    marque = marque_du_client(creer_organisation())
    assert marque["logo_url"] == "" and marque["couleur_principale"] == ""


def test_une_couleur_mal_formee_n_est_jamais_reprise(db):
    organisation = creer_organisation()
    organisation.couleur_principale = 'red;"><script>'  # ne passerait pas la base, mais la marque se défend seule
    assert marque_du_client(organisation)["couleur_principale"] == ""


def test_l_ecran_scene_affiche_le_logo_et_la_couleur_du_client(client, db):
    organisation = creer_organisation(couleur_principale="#112233")
    organisation.logo.save("al-nour.png", ContentFile(b"png"), save=True)
    concours = creer_concours(mission=creer_mission(organisation))
    session = creer_session(concours)

    html = client.get(reverse("presentation:ecran_scene", args=[session.pk])).content.decode()

    assert "al-nour" in html and "--client-principal: #112233" in html
    assert "marque-quranova" in html  # le sceau QURANOVA est toujours là, discret
    assert "img/favicon" in html


def test_la_scene_sans_logo_affichent_le_nom_du_client(client, db):
    session = creer_session(creer_concours())

    html = client.get(reverse("presentation:ecran_scene", args=[session.pk])).content.decode()

    assert "marque-client" in html and session.concours.organisation.nom in html
    assert "<img src=\"/media" not in html


def test_la_page_d_accueil_porte_le_logo_quranova(client, db):
    html = client.get("/").content.decode()
    assert "quranova-logo" in html


def test_la_tablette_du_jure_porte_la_marque_du_client(client, db):
    session = creer_session(creer_concours())

    html = client.get(reverse("jury:ecran_jury", args=[session.pk])).content.decode()

    assert session.concours.organisation.nom in html and "marque-quranova" in html


def test_le_pv_porte_le_logo_du_client_et_celui_de_quranova(db):
    from apps.resultats import documents

    organisation = creer_organisation()
    organisation.logo.save("al-nour.png", ContentFile(b"png"), save=True)
    concours = creer_concours(mission=creer_mission(organisation))

    html = documents.proces_verbal(concours)

    assert "al-nour" in html and "quranova-logo" in html and "Document produit avec QURANOVA" in html
