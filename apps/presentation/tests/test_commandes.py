"""Tests des commandes de présentation (§9.3, §13.5 ; RM-30, RM-25 ; REC-14, REC-24)."""
import threading
import uuid

import pytest
from django.db import connection

from apps.commun.tests.outils import creer_session, creer_utilisateur
from apps.prestations.models import Prestation, Tirage
from apps.presentation import services
from apps.presentation.models import CommandePresentation, EtatPresentation
from apps.presentation.tests.outils import commande, creer_prestation_tiree, operateur_de, presentation_demarree
from apps.utilisateurs.models import Utilisateur


@pytest.fixture
def tiree(db):
    prestation, epreuve, _ = creer_prestation_tiree()
    return prestation, prestation.session, operateur_de(epreuve)


# --- Préparer ------------------------------------------------------------------


@pytest.mark.django_db
def test_preparer_cree_l_etat_actif_en_version_1(tiree):
    prestation, session, operateur = tiree

    resultat = commande(session, "preparer", auteur=operateur, prestation=prestation)

    assert (resultat.statut, resultat.version) == ("appliquee", 1)
    etat = EtatPresentation.objects.get()
    assert etat.active and etat.phase == "preparee" and etat.index is None
    assert len(etat.plan) == 10  # 2 questions : intercalaires, 5 versets, fins de question, fin de série
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.TIRE  # rien n'est encore affiché


@pytest.mark.django_db
def test_preparer_exige_une_prestation_tiree(tiree):
    prestation, session, operateur = tiree
    Prestation.objects.filter(pk=prestation.pk).update(etat=Prestation.Etat.EN_ATTENTE)
    prestation.refresh_from_db()

    resultat = commande(session, "preparer", auteur=operateur, prestation=prestation)

    assert (resultat.statut, resultat.raison) == ("rejetee", "transition_interdite")
    assert EtatPresentation.objects.count() == 0


@pytest.mark.django_db
def test_preparer_refuse_une_prestation_d_une_autre_session(tiree):
    prestation, session, operateur = tiree
    autre_session = creer_session(session.concours)

    resultat = commande(autre_session, "preparer", auteur=operateur, prestation=prestation)

    assert resultat.statut == "rejetee"


@pytest.mark.django_db
def test_d41_on_ne_prepare_pas_une_autre_prestation_pendant_un_affichage():
    prestation, session, operateur, _ = presentation_demarree()
    prestation2, epreuve, _ = creer_prestation_tiree()  # autre prestation, autre concours : on la rattache à la session
    Prestation.objects.filter(pk=prestation2.pk).update(session=session)

    resultat = commande(session, "preparer", auteur=operateur, prestation=prestation2)

    assert (resultat.statut, resultat.raison) == ("rejetee", "transition_interdite")


# --- Parcours ------------------------------------------------------------------


@pytest.mark.django_db
def test_le_parcours_complet_met_a_jour_la_prestation():
    prestation, session, operateur, etat = presentation_demarree()
    assert (etat.version, etat.phase, etat.index) == (2, "affichage", 0)
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_AFFICHAGE

    assert commande(session, "pause", 2, auteur=operateur).etat.phase == "pause"
    prestation.refresh_from_db()
    assert prestation.etat == Prestation.Etat.EN_PAUSE
    assert commande(session, "reprendre", 3, auteur=operateur).version == 4
    suivante = commande(session, "suivante", 4, auteur=operateur)
    assert (suivante.statut, suivante.etat.index, suivante.version) == ("appliquee", 1, 5)
    termine = commande(session, "terminer", 5, auteur=operateur)
    prestation.refresh_from_db()
    assert termine.etat.phase == "terminee" and prestation.etat == Prestation.Etat.EN_NOTATION
    assert commande(session, "suivante", 6, auteur=operateur).raison == "transition_interdite"


@pytest.mark.django_db
def test_rm11_rien_n_avance_tout_seul_et_la_pause_bloque():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "pause", 2, auteur=operateur)

    resultat = commande(session, "suivante", 3, auteur=operateur)

    assert (resultat.statut, resultat.raison) == ("rejetee", "transition_interdite")
    assert EtatPresentation.objects.get().index == 0


@pytest.mark.django_db
def test_reafficher_rejoue_la_diapositive_sans_la_changer():
    prestation, session, operateur, _ = presentation_demarree()

    resultat = commande(session, "reafficher", 2, auteur=operateur)

    assert (resultat.etat.index, resultat.etat.rejeu, resultat.version) == (0, 1, 3)


# --- RM-30 : version, idempotence ------------------------------------------------


@pytest.mark.django_db
def test_rm30_une_commande_avec_une_version_obsolete_est_rejetee_et_ne_change_rien():
    prestation, session, operateur, _ = presentation_demarree()

    resultat = commande(session, "suivante", 1, auteur=operateur)  # la version courante est 2

    assert (resultat.statut, resultat.raison, resultat.version) == ("rejetee", "version_obsolete", 2)
    assert EtatPresentation.objects.get().index == 0


@pytest.mark.django_db
def test_rec24_deux_suivante_avec_la_meme_version_une_seule_est_appliquee():
    prestation, session, operateur, _ = presentation_demarree()

    premiere = commande(session, "suivante", 2, auteur=operateur)
    seconde = commande(session, "suivante", 2, auteur=operateur)  # double clic : même version attendue

    assert premiere.statut == "appliquee" and seconde.statut == "rejetee"
    assert seconde.raison == "version_obsolete" and seconde.version == 3
    assert EtatPresentation.objects.get().index == 1  # une seule diapositive franchie


@pytest.mark.django_db
def test_rm30_une_commande_rejouee_n_est_jamais_appliquee_deux_fois():
    prestation, session, operateur, _ = presentation_demarree()
    identifiant = uuid.uuid4()
    premiere = commande(session, "suivante", 2, auteur=operateur, id_commande=identifiant)

    rejeu = commande(session, "suivante", 2, auteur=operateur, id_commande=identifiant)

    assert (premiere.statut, rejeu.statut, rejeu.version) == ("appliquee", "deja_traitee", 3)
    assert EtatPresentation.objects.get().index == 1
    assert CommandePresentation.objects.filter(id_commande=identifiant).count() == 1


@pytest.mark.django_db
def test_une_commande_rejetee_rejouee_donne_la_meme_reponse():
    prestation, session, operateur, _ = presentation_demarree()
    identifiant = uuid.uuid4()
    commande(session, "suivante", 1, auteur=operateur, id_commande=identifiant)

    rejeu = commande(session, "suivante", 1, auteur=operateur, id_commande=identifiant)

    assert (rejeu.statut, rejeu.raison) == ("rejetee", "version_obsolete")


@pytest.mark.django_db
def test_un_identifiant_de_commande_d_une_autre_session_est_refuse():
    prestation, session, operateur, _ = presentation_demarree()
    identifiant = uuid.uuid4()
    commande(session, "suivante", 2, auteur=operateur, id_commande=identifiant)
    autre_session = creer_session(session.concours)

    resultat = commande(autre_session, "suivante", 3, auteur=operateur, id_commande=identifiant)

    assert (resultat.statut, resultat.raison) == ("rejetee", "non_autorise")


@pytest.mark.django_db(transaction=True)
def test_rec24_deux_commandes_simultanees_une_seule_est_appliquee():
    prestation, session, operateur, _ = presentation_demarree()
    barriere = threading.Barrier(2)
    resultats = []

    def envoyer():
        try:
            barriere.wait()
            resultats.append(commande(session, "suivante", 2, auteur=operateur))
        finally:
            connection.close()

    fils = [threading.Thread(target=envoyer) for _ in range(2)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    assert sorted(r.statut for r in resultats) == ["appliquee", "rejetee"]
    assert EtatPresentation.objects.get().index == 1


# --- Permissions (REC-14) --------------------------------------------------------


@pytest.mark.django_db
def test_rec14_un_responsable_client_ne_commande_pas(tiree):
    prestation, session, _ = tiree
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=session.organisation)

    resultat = commande(session, "preparer", auteur=responsable, prestation=prestation)

    assert (resultat.statut, resultat.raison) == ("rejetee", "non_autorise")
    assert EtatPresentation.objects.count() == 0


@pytest.mark.django_db
def test_rm20_un_operateur_sans_acces_a_la_mission_ne_commande_pas(tiree):
    from apps.clients.models import Mission  # noqa: F401
    from apps.commun.tests.outils import creer_mission
    from apps.utilisateurs.models import AffectationOperateur

    prestation, session, _ = tiree
    etranger = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=creer_mission(), utilisateur=etranger)

    resultat = commande(session, "preparer", auteur=etranger, prestation=prestation)

    assert (resultat.statut, resultat.raison) == ("rejetee", "non_autorise")


@pytest.mark.django_db
def test_un_utilisateur_anonyme_ne_commande_pas(tiree):
    from django.contrib.auth.models import AnonymousUser

    prestation, session, _ = tiree

    assert commande(session, "preparer", auteur=AnonymousUser(), prestation=prestation).raison == "non_autorise"


@pytest.mark.django_db
def test_une_action_inconnue_est_rejetee():
    prestation, session, operateur, _ = presentation_demarree()

    resultat = commande(session, "exploser", 2, auteur=operateur)

    assert (resultat.statut, resultat.raison) == ("rejetee", "commande_inconnue")


@pytest.mark.django_db
def test_sans_presentation_active_les_commandes_sont_rejetees(tiree):
    _, session, operateur = tiree

    assert commande(session, "demarrer", 0, auteur=operateur).raison == "transition_interdite"


# --- Journal ----------------------------------------------------------------------


@pytest.mark.django_db
def test_toute_commande_est_journalisee_avec_son_auteur_et_le_retour_en_arriere_aussi():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)
    precedente = commande(session, "precedente", 3, auteur=operateur)
    commande(session, "suivante", 1, auteur=operateur)  # rejetée : version obsolète

    journal = list(CommandePresentation.objects.order_by("cree_le").values_list("action", "statut", "raison"))

    assert ("precedente", "appliquee", "") in journal
    assert ("suivante", "rejetee", "version_obsolete") in journal
    assert precedente.etat.index == 0
    assert set(CommandePresentation.objects.values_list("auteur", flat=True)) == {operateur.pk}


# --- RM-25 : diapositive affichée ---------------------------------------------------


@pytest.mark.django_db
def test_rm25_le_tirage_est_marque_des_qu_un_verset_est_affiche():
    prestation, session, operateur, _ = presentation_demarree()
    tirage = Tirage.objects.get(prestation=prestation)
    assert tirage.diapositive_affichee is False  # l'intercalaire ne compte pas

    commande(session, "suivante", 2, auteur=operateur)  # diapositive 1 : premier verset

    tirage.refresh_from_db()
    assert tirage.diapositive_affichee is True
