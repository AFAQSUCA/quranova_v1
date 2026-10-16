"""Journal des incidents en salle (§13.6, phase 4 C1) : déclaration, résolution, cloisonnement, procès-verbal, export, bilan.

Un incident est un événement de la journée du concours (coupure, panne, Wi-Fi…) consigné par le personnel du prestataire ; il alimente le procès-verbal
(section « Incidents ») et le bilan du pilote (L-09).
"""
import zipfile
from datetime import timedelta
from io import BytesIO

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.commun.tests.outils import creer_concours, creer_mission, creer_organisation, creer_session, creer_utilisateur
from apps.incidents import services
from apps.incidents.exceptions import IncidentInvalideError
from apps.incidents.models import Incident
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.resultats import documents
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def salle(db):
    """Un concours, son opérateur affecté, et un opérateur d'une autre mission."""
    concours = creer_concours()
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    AffectationOperateur.objects.create(mission=concours.mission, utilisateur=operateur)
    return concours, operateur


def declarer(concours, operateur, **champs):
    valeurs = dict(type=Incident.Type.COUPURE_ELECTRICITE, description="Coupure secteur à 10 h 12, l'onduleur a pris le relais.")
    valeurs.update(champs)
    return services.declarer(concours, operateur, **valeurs)


# --- Déclaration ----------------------------------------------------------------------------------------------------------


def test_la_declaration_enregistre_l_incident_pour_le_bon_client_et_le_journalise(salle):
    concours, operateur = salle

    incident = declarer(concours, operateur, gravite=Incident.Gravite.MINEURE)

    assert incident.organisation_id == concours.organisation_id and incident.declare_par == operateur
    assert incident.gravite == "mineure" and incident.resolu_le is None
    assert incident.survenu_le <= timezone.now()
    assert EntreeAudit.objects.filter(action="incident.declare", objet_id=str(incident.pk), organisation=concours.organisation).count() == 1


def test_la_gravite_par_defaut_est_mineure(salle):
    concours, operateur = salle
    assert declarer(concours, operateur).gravite == Incident.Gravite.MINEURE


@pytest.mark.parametrize("description", ["", "   "])
def test_la_description_est_obligatoire(salle, description):
    concours, operateur = salle

    with pytest.raises(IncidentInvalideError, match="description"):
        declarer(concours, operateur, description=description)
    assert not Incident.objects.exists()


def test_un_incident_ne_peut_pas_etre_date_dans_le_futur(salle):
    concours, operateur = salle

    with pytest.raises(IncidentInvalideError, match="futur"):
        declarer(concours, operateur, survenu_le=timezone.now() + timedelta(hours=1))


def test_un_incident_peut_etre_declare_apres_coup_avec_son_heure_reelle(salle):
    concours, operateur = salle
    il_y_a_une_heure = timezone.now() - timedelta(hours=1)

    assert declarer(concours, operateur, survenu_le=il_y_a_une_heure).survenu_le == il_y_a_une_heure


def test_seul_le_personnel_affecte_a_la_mission_declare(salle):
    concours, _ = salle
    non_affecte = creer_utilisateur(Utilisateur.Role.OPERATEUR)  # opérateur d'aucune mission (RM-20)
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation)

    for intrus in (non_affecte, responsable):
        with pytest.raises(IncidentInvalideError, match="droit"):
            declarer(concours, intrus)
    assert services.declarer(
        concours, creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR), type=Incident.Type.AUTRE, description="Constat de l'administrateur."
    ).pk


def test_la_session_et_la_prestation_doivent_appartenir_au_concours(salle):
    concours, operateur = salle
    epreuve = creer_epreuve_ouverte(series=1)  # un AUTRE concours
    d_ailleurs = creer_prestation(epreuve)

    with pytest.raises(IncidentInvalideError, match="session"):
        declarer(concours, operateur, session=d_ailleurs.session)
    with pytest.raises(IncidentInvalideError, match="prestation"):
        declarer(concours, operateur, prestation=d_ailleurs)


def test_un_incident_peut_viser_une_session_et_une_prestation_du_concours(salle):
    concours, operateur = salle
    session = creer_session(concours)

    incident = declarer(concours, operateur, session=session)

    assert incident.session == session


# --- Résolution -----------------------------------------------------------------------------------------------------------------


def test_la_resolution_consigne_ce_qui_a_ete_fait_et_la_duree(salle):
    concours, operateur = salle
    incident = declarer(concours, operateur, survenu_le=timezone.now() - timedelta(minutes=12))

    services.resoudre(incident, operateur, "Routeur de rechange branché, même SSID.")

    incident.refresh_from_db()
    assert incident.resolu_le is not None and incident.resolution.startswith("Routeur")
    assert timedelta(minutes=11) < incident.duree < timedelta(minutes=13)
    assert EntreeAudit.objects.filter(action="incident.resolu", objet_id=str(incident.pk)).count() == 1


def test_une_resolution_sans_texte_est_refusee(salle):
    concours, operateur = salle
    incident = declarer(concours, operateur)

    with pytest.raises(IncidentInvalideError, match="résolution"):
        services.resoudre(incident, operateur, "  ")
    incident.refresh_from_db()
    assert incident.resolu_le is None


def test_on_ne_resout_pas_deux_fois_un_incident(salle):
    concours, operateur = salle
    incident = declarer(concours, operateur)
    services.resoudre(incident, operateur, "Fait.")

    with pytest.raises(IncidentInvalideError, match="déjà"):
        services.resoudre(incident, operateur, "Encore.")


def test_la_resolution_ne_peut_pas_preceder_l_incident(salle):
    concours, operateur = salle
    incident = declarer(concours, operateur, survenu_le=timezone.now() - timedelta(minutes=5))

    with pytest.raises(IncidentInvalideError, match="avant"):
        services.resoudre(incident, operateur, "Fait.", resolu_le=timezone.now() - timedelta(minutes=30))


def test_seul_le_personnel_affecte_resout(salle):
    concours, operateur = salle
    incident = declarer(concours, operateur)

    with pytest.raises(IncidentInvalideError, match="droit"):
        services.resoudre(incident, creer_utilisateur(Utilisateur.Role.OPERATEUR), "Fait.")


def test_un_incident_non_resolu_n_a_pas_de_duree(salle):
    concours, operateur = salle
    assert declarer(concours, operateur).duree is None


# --- Bilan ----------------------------------------------------------------------------------------------------------------------------


def test_le_bilan_compte_par_type_et_gravite_et_cumule_les_durees(salle):
    concours, operateur = salle
    debut = timezone.now() - timedelta(hours=2)
    a = declarer(concours, operateur, type=Incident.Type.PANNE_ROUTEUR, gravite=Incident.Gravite.BLOQUANTE, survenu_le=debut)
    services.resoudre(a, operateur, "Routeur de secours.", resolu_le=debut + timedelta(minutes=4))
    b = declarer(concours, operateur, type=Incident.Type.PANNE_TABLETTE_JURE, survenu_le=debut + timedelta(minutes=30))
    services.resoudre(b, operateur, "Tablette de rechange.", resolu_le=debut + timedelta(minutes=32))
    declarer(concours, operateur, type=Incident.Type.WIFI_COUPE)  # non résolu

    bilan = services.bilan(concours)

    assert bilan["total"] == 3 and bilan["bloquants"] == 1 and bilan["non_resolus"] == 1
    assert bilan["par_type"] == {"Panne du routeur Wi-Fi": 1, "Panne d'une tablette de juré": 1, "Coupure du Wi-Fi": 1}
    assert bilan["duree_cumulee"] == timedelta(minutes=6)


def test_le_bilan_ne_compte_que_le_concours_demande(salle):
    concours, operateur = salle
    declarer(concours, operateur)
    autre = creer_concours(creer_mission(creer_organisation()))

    assert services.bilan(autre)["total"] == 0


# --- Administration (cloisonnement par client, RM-20) ----------------------------------------------------------------------------------


def test_l_operateur_declare_depuis_l_administration_et_se_voit_comme_declarant(client, salle):
    concours, operateur = salle
    client.force_login(operateur)

    reponse = client.post(reverse("admin:incidents_incident_add"), {
        "concours": str(concours.pk), "type": "panne_routeur", "gravite": "bloquante",
        "survenu_le_0": timezone.localdate().isoformat(), "survenu_le_1": "10:05:00", "description": "Le routeur ne répond plus.",
    })

    assert reponse.status_code == 302, getattr(reponse, "context", None) and reponse.context["adminform"].form.errors
    incident = Incident.objects.get()
    assert incident.declare_par == operateur and incident.organisation_id == concours.organisation_id


def test_un_operateur_ne_voit_pas_les_incidents_d_un_autre_client(client, salle):
    concours, operateur = salle
    declarer(concours, operateur)
    autre_concours = creer_concours(creer_mission(creer_organisation()))
    admin = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR)
    services.declarer(autre_concours, admin, type=Incident.Type.AUTRE, description="Incident d'un autre client.")
    client.force_login(operateur)

    page = client.get(reverse("admin:incidents_incident_changelist")).content.decode()

    assert "Coupure secteur" in page and "autre client" not in page


def test_le_responsable_client_consulte_sans_rien_pouvoir_ecrire(client, salle):
    concours, operateur = salle
    incident = declarer(concours, operateur)
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation, is_staff=True)
    client.force_login(responsable)

    assert client.get(reverse("admin:incidents_incident_changelist")).status_code == 200
    assert client.get(reverse("admin:incidents_incident_add")).status_code == 403
    assert client.post(reverse("admin:incidents_incident_delete", args=[incident.pk]), {"post": "yes"}).status_code == 403


def test_personne_ne_supprime_un_incident(client, salle):
    concours, operateur = salle
    incident = declarer(concours, operateur)
    client.force_login(operateur)

    assert client.post(reverse("admin:incidents_incident_delete", args=[incident.pk]), {"post": "yes"}).status_code == 403
    assert Incident.objects.filter(pk=incident.pk).exists()


def test_la_fiche_ne_laisse_modifier_que_la_resolution_et_la_resolution_passe_par_le_service(client, salle):
    concours, operateur = salle
    incident = declarer(concours, operateur)
    client.force_login(operateur)

    client.post(reverse("admin:incidents_incident_change", args=[incident.pk]), {
        "description": "Description réécrite après coup", "resolution": "Onduleur rechargé.", "resolu_le_0": timezone.localdate().isoformat(),
        "resolu_le_1": "23:59:00",
    })

    incident.refresh_from_db()
    assert incident.description.startswith("Coupure secteur")  # la description d'origine n'est pas réécrite (traçabilité)
    assert incident.resolution == "Onduleur rechargé." and incident.resolu_le is not None
    assert EntreeAudit.objects.filter(action="incident.resolu").count() == 1


# --- Procès-verbal et export -----------------------------------------------------------------------------------------------------------------


def test_le_proces_verbal_liste_les_incidents_declares_et_le_bilan(salle):
    concours, operateur = salle
    debut = timezone.now() - timedelta(hours=1)
    incident = declarer(concours, operateur, type=Incident.Type.PANNE_ROUTEUR, gravite=Incident.Gravite.BLOQUANTE, survenu_le=debut,
                        description="Routeur éteint par erreur.")
    services.resoudre(incident, operateur, "Rallumé.", resolu_le=debut + timedelta(minutes=3))

    html = documents.proces_verbal(concours, operateur)

    assert "Routeur éteint par erreur." in html and "Panne du routeur Wi-Fi" in html and "Rallumé." in html
    assert "1 incident déclaré" in html and "1 bloquant" in html


def test_le_proces_verbal_sans_incident_le_dit(salle):
    concours, operateur = salle

    assert "Aucun incident" in documents.proces_verbal(concours, operateur)


def test_le_texte_d_un_incident_est_echappe_dans_le_proces_verbal(salle):
    concours, operateur = salle
    declarer(concours, operateur, description="<script>alert(1)</script>")

    html = documents.proces_verbal(concours, operateur)

    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_l_export_contient_les_incidents_avec_neutralisation_des_formules(salle):
    concours, operateur = salle
    declarer(concours, operateur, description="=HYPERLINK(\"http://pirate\")")

    archive = zipfile.ZipFile(BytesIO(documents.exporter_donnees(concours, operateur)))
    contenu = archive.read("incidents.csv").decode("utf-8-sig")

    assert "incidents.csv" in archive.read("LISEZMOI.txt").decode("utf-8-sig")
    assert "'=HYPERLINK" in contenu and ";=HYPERLINK" not in contenu
