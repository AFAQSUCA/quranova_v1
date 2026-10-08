"""Tests de l'administration : accès par rôle, cloisonnement des clients (RM-20, REC-25, REC-29),
tirages protégés, règles métier signalées sans erreur 500."""
import pytest
from django.contrib import admin
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.candidats.models import Candidat, Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_mission,
    creer_organisation,
    creer_participation,
    creer_session,
    creer_utilisateur,
)
from apps.concours.models import Concours
from apps.prestations.models import Prestation, Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation, creer_tirage
from apps.questions.models import Question, Serie
from apps.questions.services import obtenir_lot
from apps.questions.tests.outils import creer_question
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def url(modele, action, *args):
    return reverse(f"admin:{modele._meta.app_label}_{modele._meta.model_name}_{action}", args=args)


def messages_de(reponse):
    return " | ".join(str(m) for m in get_messages(reponse.wsgi_request))


@pytest.fixture
def administrateur(db, client):
    utilisateur = Utilisateur.objects.create_superuser("admin-test", password="x")
    client.force_login(utilisateur)
    return utilisateur


def operateur_de(mission, client):
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=mission, utilisateur=operateur)
    client.force_login(operateur)
    return operateur


# --- Pages ---------------------------------------------------------------------


@pytest.mark.django_db
def test_toutes_les_listes_de_l_administration_s_affichent(administrateur, client):
    creer_epreuve_ouverte(series=2)
    for modele in admin.site._registry:
        reponse = client.get(url(modele, "changelist"))
        assert reponse.status_code == 200, modele


@pytest.mark.django_db
def test_les_formulaires_de_creation_s_affichent(administrateur, client):
    for modele, model_admin in admin.site._registry.items():
        if model_admin.has_add_permission(type("R", (), {"user": administrateur})()):
            assert client.get(url(modele, "add")).status_code == 200, modele


# --- Accès par rôle ------------------------------------------------------------


@pytest.mark.django_db
def test_un_anonyme_est_renvoye_vers_la_connexion(client):
    reponse = client.get(url(Concours, "changelist"))

    assert reponse.status_code == 302 and "login" in reponse.url


@pytest.mark.django_db
def test_un_responsable_client_consulte_sans_pouvoir_ecrire(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    client.force_login(responsable)

    assert client.get(url(Concours, "changelist")).status_code == 200
    assert client.get(url(Concours, "add")).status_code == 403
    assert client.get(url(Candidat, "add")).status_code == 403


@pytest.mark.django_db
def test_un_utilisateur_inactif_ou_hors_equipe_n_entre_pas(client):
    sans_acces = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=False)
    client.force_login(sans_acces)

    assert client.get(url(Concours, "changelist")).status_code == 302


@pytest.mark.django_db
def test_seul_l_administrateur_gere_les_comptes(client):
    client.force_login(creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True))
    assert client.get(url(Utilisateur, "changelist")).status_code == 403


@pytest.mark.django_db
def test_un_compte_cree_dans_l_administration_peut_se_connecter_a_l_administration(administrateur, client):
    reponse = client.post(
        url(Utilisateur, "add"),
        {"username": "nouvel-operateur", "password1": "Mot-de-passe-solide-42", "password2": "Mot-de-passe-solide-42",
         "role": "operateur"},
    )

    assert reponse.status_code == 302
    assert Utilisateur.objects.get(username="nouvel-operateur").is_staff is True


# --- Cloisonnement des clients -------------------------------------------------


@pytest.mark.django_db
def test_rm20_un_operateur_ne_voit_que_les_donnees_de_ses_clients(client):
    mission = creer_mission()
    mien = creer_candidat(mission.organisation, nom="Visible")
    autre = creer_candidat(creer_organisation(), nom="Invisible")
    operateur_de(mission, client)

    reponse = client.get(url(Candidat, "changelist"))

    contenu = reponse.content.decode()
    assert "Visible" in contenu and "Invisible" not in contenu
    assert client.get(url(Candidat, "change", mien.pk)).status_code == 200


@pytest.mark.django_db
def test_rec25_rec29_un_identifiant_d_un_autre_client_n_est_pas_accessible(client):
    mission = creer_mission()
    autre = creer_candidat(creer_organisation())
    operateur_de(mission, client)

    reponse = client.get(url(Candidat, "change", autre.pk), follow=True)

    assert "Invisible" not in reponse.content.decode()
    assert reponse.redirect_chain  # renvoyé vers la liste, sans rien divulguer
    assert client.post(url(Candidat, "delete", autre.pk), {"post": "yes"}).status_code in (302, 404)
    assert Candidat.objects.filter(pk=autre.pk).exists()


@pytest.mark.django_db
def test_un_responsable_client_ne_voit_que_sa_propre_organisation(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    creer_concours(creer_mission(responsable.organisation), nom="Concours-Mien")
    creer_concours(creer_mission(), nom="Concours-Etranger")
    client.force_login(responsable)

    contenu = client.get(url(Concours, "changelist")).content.decode()

    assert "Concours-Mien" in contenu and "Concours-Etranger" not in contenu


@pytest.mark.django_db
def test_les_menus_deroulants_ne_proposent_pas_les_donnees_d_un_autre_client(client):
    mission = creer_mission()
    categorie = creer_categorie(creer_concours(mission))
    creer_candidat(mission.organisation, nom="Candidat-Mien")
    creer_candidat(creer_organisation(), nom="Candidat-Etranger")
    operateur_de(mission, client)

    contenu = client.get(url(Participation, "add")).content.decode()

    assert "Candidat-Mien" in contenu and "Candidat-Etranger" not in contenu


# --- Règles protégées ----------------------------------------------------------


@pytest.mark.django_db
def test_un_tirage_ne_s_ecrit_ni_ne_s_efface_dans_l_administration(administrateur, client):
    epreuve = creer_epreuve_ouverte(series=1)
    tirage = creer_tirage(creer_prestation(epreuve), epreuve.lot.series.get())

    assert client.get(url(Tirage, "add")).status_code == 403
    assert client.post(url(Tirage, "delete", tirage.pk), {"post": "yes"}).status_code == 403
    assert client.get(url(Tirage, "change", tirage.pk)).status_code == 200  # consultation
    assert Tirage.objects.count() == 1


@pytest.mark.django_db
def test_l_etat_d_un_concours_ne_se_change_pas_a_la_main(administrateur, client):
    concours = creer_concours(nom="Brouillon")

    client.post(
        url(Concours, "change", concours.pk),
        {"mission": concours.mission_id, "nom": "Brouillon", "edition": "2027", "format": "presentiel",
         "date_debut": "2027-01-20", "date_fin": "2027-01-21", "etat": "en_cours"},
    )

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.BROUILLON


@pytest.mark.django_db
def test_l_administrateur_ne_valide_pas_la_configuration(administrateur, client):
    reponse = client.post(
        url(Concours, "changelist"), {"action": "valider_la_configuration", "_selected_action": []}, follow=True
    )

    assert "Valider la configuration" not in reponse.content.decode()


@pytest.mark.django_db
def test_le_responsable_client_valide_la_configuration_depuis_l_administration(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    concours = creer_concours(creer_mission(responsable.organisation))
    client.force_login(responsable)

    reponse = client.post(
        url(Concours, "changelist"),
        {"action": "valider_la_configuration", "_selected_action": [str(concours.pk)]},
        follow=True,
    )

    assert reponse.status_code == 200
    assert "Configuration incomplète" in messages_de(reponse)  # aucune catégorie : refus lisible, pas d'erreur 500


# --- Règles métier : message, pas d'erreur 500 ---------------------------------


@pytest.mark.django_db
def test_une_regle_metier_violee_donne_un_message_et_rien_n_est_enregistre(administrateur, client):
    epreuve = creer_epreuve_ouverte(series=1)
    autre_categorie = creer_categorie(epreuve.categorie.concours)
    participation = creer_participation(autre_categorie)  # pas la catégorie de l'épreuve
    session = creer_session(epreuve.categorie.concours)

    reponse = client.post(
        url(Prestation, "add"),
        {"participation": participation.pk, "epreuve": epreuve.pk, "session": session.pk, "rang_passage": 1},
        follow=True,
    )

    assert reponse.status_code == 200
    assert "catégorie" in messages_de(reponse)
    assert Prestation.objects.count() == 0


@pytest.mark.django_db
def test_une_contrainte_de_base_donne_un_message(administrateur, client):
    mission = creer_mission()
    creer_concours(mission, nom="Doublon", edition="2027")

    reponse = client.post(
        url(Concours, "add"),
        {"mission": mission.pk, "nom": "Doublon", "edition": "2027", "format": "presentiel",
         "date_debut": "2027-01-20", "date_fin": "2027-01-21"},
        follow=True,
    )

    assert reponse.status_code == 200
    assert Concours.objects.filter(nom="Doublon").count() == 1


@pytest.mark.django_db
def test_une_participation_creee_dans_l_administration_recoit_son_numero(administrateur, client):
    concours = creer_concours()
    categorie = creer_categorie(concours)
    creer_participation(categorie, numero_candidat=41)
    candidat = creer_candidat(concours.organisation)

    reponse = client.post(
        url(Participation, "add"),
        {"candidat": candidat.pk, "categorie": categorie.pk, "statut": "admis"},
        follow=True,
    )

    assert reponse.status_code == 200
    participation = Participation.objects.get(candidat=candidat)
    assert participation.numero_candidat == 42 and participation.statut == "admis"
    assert participation.concours == concours


@pytest.mark.django_db
def test_une_serie_se_compose_dans_l_administration_avec_exactement_p_questions(administrateur, client):
    epreuve = creer_epreuve_ouverte(series=0, p=2)
    lot = obtenir_lot(epreuve)
    q1, q2, q3 = (creer_question(epreuve.organisation) for _ in range(3))

    refus = client.post(url(Serie, "add"), {"lot": lot.pk, "questions": [q1.pk]}, follow=True)
    assert "exactement 2" in messages_de(refus) and Serie.objects.count() == 0

    succes = client.post(url(Serie, "add"), {"lot": lot.pk, "questions": [q2.pk, q1.pk]}, follow=True)
    assert succes.status_code == 200
    serie = Serie.objects.get()
    assert [x.question for x in serie.questions_ordonnees.all()] == [q1, q2]  # ordre de création


@pytest.mark.django_db
def test_une_question_enonce_se_cree_dans_l_administration(administrateur, client):
    organisation = creer_organisation()

    client.post(
        url(Question, "add"),
        {"organisation": organisation.pk, "type": "enonce", "enonce": "Quel est le sens d'al-Fatiha ?"},
    )

    assert Question.objects.get().type == Question.Type.ENONCE


@pytest.mark.django_db
def test_demarrer_un_concours_ouvert(administrateur, client):
    from apps.concours.services import demarrer_concours

    epreuve = creer_epreuve_ouverte(series=1)
    Concours.objects.filter(pk=epreuve.categorie.concours_id).update(etat=Concours.Etat.OUVERT)
    concours = Concours.objects.get(pk=epreuve.categorie.concours_id)

    demarrer_concours(concours)

    concours.refresh_from_db()
    assert concours.etat == Concours.Etat.EN_COURS


@pytest.mark.django_db
def test_demarrer_refuse_un_concours_qui_n_est_pas_ouvert():
    from apps.concours.exceptions import ConfigurationInvalideError
    from apps.concours.services import demarrer_concours

    with pytest.raises(ConfigurationInvalideError):
        demarrer_concours(creer_concours())


@pytest.mark.django_db
def test_ouvrir_une_epreuve_signale_la_regle_non_ecrite_sans_erreur_500(administrateur, client):
    """Tant que ``series_necessaires`` (TODO(human)) n'est pas écrite, l'action explique et ne plante pas."""
    from apps.concours.models import Epreuve
    from apps.prestations import services

    epreuve = creer_epreuve_ouverte(series=2, etat=Epreuve.Etat.EN_PREPARATION)
    original = services.series_necessaires

    def non_ecrite(*args, **kwargs):
        raise NotImplementedError("TODO(human) : contrôle de suffisance")

    services.series_necessaires = non_ecrite
    try:
        reponse = client.post(
            url(Epreuve, "changelist"),
            {"action": "ouvrir", "_selected_action": [str(epreuve.pk)]},
            follow=True,
        )
    finally:
        services.series_necessaires = original

    assert reponse.status_code == 200 and "TODO(human)" in messages_de(reponse)
