"""Les opérations sensibles laissent une trace dans le journal d'audit (§15.2 ; REC-07)."""
import uuid

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.urls import reverse

from apps.audit import services
from apps.audit.models import EntreeAudit
from apps.candidats.importation import importer_candidats
from apps.commun.tests.outils import creer_categorie, creer_concours, creer_utilisateur, configuration_complete, creer_version_validee
from apps.concours import services as services_concours
from apps.presentation.tests.outils import commande, creer_prestation_tiree, operateur_de, presentation_demarree
from apps.prestations import services as services_prestations
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.utilisateurs.models import Utilisateur


def entrees(action):
    return list(EntreeAudit.objects.filter(action=action))


# --- Tirage et annulation ------------------------------------------------------------


@pytest.mark.django_db
def test_un_tirage_est_journalise_avec_la_serie_le_terminal_et_le_candidat():
    epreuve = creer_epreuve_ouverte(series=3)
    prestation = creer_prestation(epreuve)

    tirage = services_prestations.effectuer_tirage(prestation, uuid.uuid4(), terminal="Tablette 1")

    (entree,) = entrees("tirage.effectue")
    assert entree.organisation == epreuve.organisation and entree.terminal == "Tablette 1"
    assert entree.objet_type == "Tirage" and entree.objet_id == str(tirage.pk)
    assert entree.details["serie"] == tirage.serie.libelle and entree.details["rang"] == 1
    assert entree.details["candidat"] == prestation.participation.numero_candidat
    assert services.verifier_chaine(epreuve.organisation) == []


@pytest.mark.django_db
def test_rec07_une_demande_rejouee_ne_journalise_qu_une_fois():
    prestation = creer_prestation(creer_epreuve_ouverte(series=3))
    demande = uuid.uuid4()

    services_prestations.effectuer_tirage(prestation, demande)
    services_prestations.effectuer_tirage(prestation, demande)

    assert len(entrees("tirage.effectue")) == 1


@pytest.mark.django_db
def test_un_tirage_refuse_ne_laisse_aucune_trace():
    epreuve = creer_epreuve_ouverte(series=0)  # lot vide : tirage bloqué

    with pytest.raises(Exception):
        services_prestations.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())

    assert EntreeAudit.objects.count() == 0


@pytest.mark.django_db
def test_l_annulation_est_journalisee_avec_son_auteur_et_son_motif():
    epreuve = creer_epreuve_ouverte(series=2)
    tirage = services_prestations.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4())
    operateur = creer_utilisateur()

    services_prestations.annuler_tirage(tirage, operateur, "Erreur d'appel du candidat")

    (entree,) = entrees("tirage.annule")
    assert entree.auteur == operateur and entree.details["motif"] == "Erreur d'appel du candidat"
    assert entree.details["diapositive_affichee"] is False


# --- Diaporama ------------------------------------------------------------------------


@pytest.mark.django_db
def test_le_retour_a_la_diapositive_precedente_est_journalise_mais_pas_suivante():
    prestation, session, operateur, _ = presentation_demarree()
    commande(session, "suivante", 2, auteur=operateur)
    assert entrees("diaporama.precedente") == []

    commande(session, "precedente", 3, auteur=operateur)

    (entree,) = entrees("diaporama.precedente")
    assert entree.auteur == operateur and entree.objet_id == str(prestation.pk)
    assert entree.details == {"version": 4, "diapositive": 0}


@pytest.mark.django_db
def test_une_commande_rejetee_n_est_pas_journalisee_comme_un_retour_en_arriere():
    prestation, session, operateur, _ = presentation_demarree()

    commande(session, "precedente", 2, auteur=operateur)  # première diapositive : interdit

    assert entrees("diaporama.precedente") == []


# --- Import, configuration -----------------------------------------------------------------


def csv(chemin, lignes):
    chemin.write_text("nom;prenom;categorie\n" + "".join(f"{n};{p};Juniors\n" for n, p in lignes), encoding="utf-8")
    return chemin


@pytest.mark.django_db
def test_un_import_reel_est_journalise_une_simulation_non(tmp_path):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")
    fichier = csv(tmp_path / "candidats.csv", [("Diallo", "Awa"), ("Koné", "Ali")])

    importer_candidats(concours, fichier, simuler=True)
    assert entrees("candidats.importes") == []
    importer_candidats(concours, fichier, auteur=creer_utilisateur())

    (entree,) = entrees("candidats.importes")
    assert entree.details == {"fichier": "candidats.csv", "lignes": 2, "inscrits": 2}
    assert entree.objet_id == str(concours.pk)


@pytest.mark.django_db
def test_un_import_refuse_ne_laisse_aucune_trace(tmp_path):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")

    importer_candidats(concours, csv(tmp_path / "x.csv", [("", "Awa")]))

    assert entrees("candidats.importes") == []


@pytest.mark.django_db
def test_la_validation_de_la_configuration_et_l_ouverture_sont_journalisees():
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)
    from apps.commun.tests.outils import creer_mission

    concours = configuration_complete(creer_concours(creer_mission(responsable.organisation), version_corpus=creer_version_validee()))

    services_concours.valider_configuration(concours, responsable)
    services_concours.ouvrir_concours(concours)

    (validation,) = entrees("concours.configuration_validee")
    assert validation.auteur == responsable and validation.details["empreinte"] == concours.configuration_empreinte
    assert len(entrees("concours.ouvert")) == 1


# --- Connexions ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_une_connexion_est_journalisee(client):
    operateur = creer_utilisateur(is_staff=True)
    operateur.set_password("mot-de-passe-solide-42")
    operateur.save()

    client.login(username=operateur.username, password="mot-de-passe-solide-42")

    (entree,) = entrees("connexion")
    assert entree.auteur == operateur and entree.details == {"role": "operateur"}
    assert entree.organisation is None  # le personnel du prestataire n'appartient à aucun client


@pytest.mark.django_db
def test_la_connexion_d_un_responsable_client_va_dans_la_chaine_de_son_client(client):
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, is_staff=True)
    responsable.set_password("mot-de-passe-solide-42")
    responsable.save()

    client.login(username=responsable.username, password="mot-de-passe-solide-42")

    assert entrees("connexion")[0].organisation == responsable.organisation


# --- Commande de vérification et administration -----------------------------------------------------


@pytest.mark.django_db
def test_la_commande_verifier_audit_signale_une_chaine_intacte():
    from io import StringIO

    services.journaliser("a")
    sortie = StringIO()

    call_command("verifier_audit", stdout=sortie)

    assert "aucune anomalie" in sortie.getvalue()


@pytest.mark.django_db
def test_la_commande_verifier_audit_echoue_si_le_journal_est_altere():
    services.journaliser("a")
    services.journaliser("b")
    with connection.cursor() as curseur:
        curseur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        curseur.execute("ALTER TABLE audit_entreeaudit DISABLE TRIGGER USER")
        curseur.execute("UPDATE audit_entreeaudit SET action = 'falsifiee' WHERE numero = 1")

    with pytest.raises(CommandError, match="ALTÉRÉ"):
        call_command("verifier_audit")


@pytest.mark.django_db
def test_l_administration_consulte_le_journal_sans_pouvoir_l_ecrire(client):
    services.journaliser("a")
    client.force_login(Utilisateur.objects.create_superuser("admin-audit", password="x"))
    entree = EntreeAudit.objects.get(action="a")

    assert client.get(reverse("admin:audit_entreeaudit_changelist")).status_code == 200
    assert client.get(reverse("admin:audit_entreeaudit_change", args=[entree.pk])).status_code == 200
    assert client.get(reverse("admin:audit_entreeaudit_add")).status_code == 403
    assert client.post(reverse("admin:audit_entreeaudit_delete", args=[entree.pk]), {"post": "yes"}).status_code == 403
