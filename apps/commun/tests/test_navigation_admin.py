"""Interface d'administration : menu latéral, compteurs cloisonnés, page de connexion, icônes d'action.

Le menu est de l'affichage, pas de la sécurité (les vues revérifient tout) ; mais ses compteurs
passent par la même requête filtrée que les listes : ils ne doivent jamais révéler un autre client (RM-20).
"""
import re

import pytest
from django.urls import reverse

from apps.commun.tests.outils import creer_candidat, creer_mission, creer_organisation, creer_utilisateur
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def compteur_du_menu(html: str, libelle: str):
    """Le nombre affiché dans la pastille du menu pour l'entrée `libelle`, ou None s'il n'y a pas de pastille."""
    motif = rf'<span class="q-label">{re.escape(libelle)}</span>\s*(?:<span class="q-badge"[^>]*>(\d+)</span>)?'
    trouve = re.search(motif, html)
    assert trouve, f"entrée « {libelle} » absente du menu"
    return int(trouve.group(1)) if trouve.group(1) else None


def libelles_du_menu(html: str) -> list[str]:
    return re.findall(r'<span class="q-label">([^<]+)</span>', html)


@pytest.mark.django_db
def test_la_page_de_connexion_porte_la_charte(client):
    reponse = client.get(reverse("admin:login"))
    html = reponse.content.decode()
    assert reponse.status_code == 200
    assert "q-login-card" in html and "Se connecter" in html
    assert "css/admin-quranova.css" in html
    assert 'name="username"' in html and 'name="password"' in html


@pytest.mark.django_db
def test_un_visiteur_non_connecte_n_a_pas_de_menu(client):
    reponse = client.get(reverse("admin:login"))
    assert "q-sidebar" not in reponse.content.decode()


@pytest.mark.django_db
def test_menu_groupe_avec_les_trois_sections_demandees(client):
    client.force_login(Utilisateur.objects.create_superuser("admin-nav", password="x"))
    html = client.get(reverse("admin:index")).content.decode()
    for titre in ("Candidats", "Clients", "Concours"):
        assert f"<span>{titre}</span>" in html  # titre de groupe repliable
    for libelle in ("Candidats", "Consentements", "Participations", "Missions", "Organisations",
                    "Catégories", "Concours", "Sessions", "Épreuves"):
        assert libelle in libelles_du_menu(html)


@pytest.mark.django_db
def test_rm20_les_compteurs_du_menu_ne_comptent_que_le_client_de_l_operateur(client):
    ma_mission = creer_mission()
    autre_mission = creer_mission()
    for _ in range(2):
        creer_candidat(ma_mission.organisation)
    for _ in range(5):
        creer_candidat(autre_mission.organisation)
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=ma_mission, utilisateur=operateur)
    client.force_login(operateur)

    html = client.get(reverse("admin:index")).content.decode()

    assert compteur_du_menu(html, "Candidats") == 2
    assert compteur_du_menu(html, "Missions") == 1


@pytest.mark.django_db
def test_le_menu_ne_propose_pas_ce_que_le_role_ne_peut_pas_voir(client):
    mission = creer_mission()
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)
    client.force_login(operateur)
    html = client.get(reverse("admin:index")).content.decode()
    assert "Utilisateurs" not in libelles_du_menu(html)
    # ... et la page elle-même reste interdite (le menu n'est pas la protection).
    assert client.get(reverse("admin:utilisateurs_utilisateur_changelist")).status_code == 403


@pytest.mark.django_db
def test_l_entree_active_du_menu_est_marquee(client):
    client.force_login(Utilisateur.objects.create_superuser("admin-actif", password="x"))
    html = client.get(reverse("admin:candidats_candidat_changelist")).content.decode()
    assert re.search(r'<a class="q-item is-active" href="/admin/candidats/candidat/"', html)
    assert 'aria-current="page"' in html


@pytest.mark.django_db
def test_la_liste_affiche_titre_compteur_et_bouton_ajouter(client):
    organisation = creer_organisation()
    creer_candidat(organisation)
    client.force_login(Utilisateur.objects.create_superuser("admin-liste", password="x"))
    html = client.get(reverse("admin:candidats_candidat_changelist")).content.decode()
    assert '<span class="q-count">1</span> élément' in html
    assert "q-btn q-btn-primary" in html and "Ajouter" in html
    assert 'data-can-delete="1"' in html


@pytest.mark.django_db
def test_une_liste_vide_affiche_l_etat_vide_avec_appel_a_l_action(client):
    client.force_login(Utilisateur.objects.create_superuser("admin-vide", password="x"))
    html = client.get(reverse("admin:candidats_candidat_changelist")).content.decode()
    assert "q-empty" in html and "Commencez par en ajouter un" in html


@pytest.mark.django_db
def test_une_liste_en_lecture_seule_n_offre_ni_ajout_ni_suppression(client):
    client.force_login(Utilisateur.objects.create_superuser("admin-ro", password="x"))
    html = client.get(reverse("admin:audit_entreeaudit_changelist")).content.decode()
    assert "q-btn q-btn-primary" not in html  # pas de bouton « Ajouter » sur le journal d'audit


@pytest.mark.django_db
def test_les_messages_sont_rendus_pour_devenir_des_toasts(client):
    client.force_login(Utilisateur.objects.create_superuser("admin-msg", password="x"))
    organisation = creer_organisation()
    candidat = creer_candidat(organisation)
    reponse = client.post(
        reverse("admin:candidats_candidat_change", args=[candidat.pk]),
        {"organisation": organisation.pk, "nom": "Nouveau", "prenom": candidat.prenom,
         "date_naissance": "01/05/1994", "ville": "Abidjan", "structure": "", "sexe": ""},
        follow=True,
    )
    html = reponse.content.decode()
    assert 'id="q-messages"' in html and 'class="success"' in html
    assert 'id="q-toasts"' in html


@pytest.mark.django_db
def test_le_logo_complet_est_utilise_et_non_l_embleme_rogne(client):
    html = client.get(reverse("admin:login")).content.decode()
    assert "quranova-logo.png" in html and "quranova-embleme.png" not in html
