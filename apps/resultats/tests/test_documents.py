"""Procès-verbal et export des données (§11, §17.1 ; REC-16, REC-26, REC-42)."""
import csv
import io
import time
import uuid
import zipfile
from datetime import date

import pytest
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import EntreeAudit
from apps.candidats.models import Candidat, Consentement, Participation
from apps.commun.tests.outils import (
    creer_candidat, creer_consentement, creer_organisation, creer_participation, creer_utilisateur,
)
from apps.prestations import services as services_prestations
from apps.prestations.models import Prestation, Tirage
from apps.resultats import documents, validation
from apps.resultats.models import Classement, LigneDeClassement
from apps.resultats.tests.test_validation import exemple_complet
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


def lire_zip(contenu):
    archive = zipfile.ZipFile(io.BytesIO(contenu))
    return {nom: archive.read(nom).decode("utf-8-sig") for nom in archive.namelist()}


def lignes_csv(texte):
    return list(csv.reader(io.StringIO(texte), delimiter=";"))


# --- Procès-verbal -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_rec16_le_pv_ne_contient_aucun_resultat_non_valide():
    epreuve, *_ = exemple_complet()[:1]

    html = documents.proces_verbal(epreuve.categorie.concours)

    assert "PROVISOIRE" in html and "n'a pas été validé" in html or "non validé" in html
    assert "30,33" not in html and "Classement non validé" in html


@pytest.mark.django_db
def test_apres_validation_le_pv_est_definitif_avec_les_rangs_et_les_scores():
    epreuve, _, _, _, responsable = exemple_complet()
    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    html = documents.proces_verbal(epreuve.categorie.concours, responsable)

    assert "Procès-verbal définitif" in html and "Tous les classements ci-dessous ont été validés" in html
    assert "30,33" in html and "(ex aequo)" in html and "Candidat-A" in html  # le français écrit la virgule décimale
    assert f"par {responsable}" in html


@pytest.mark.django_db
def test_le_pv_montre_la_version_corrigee_et_son_motif():
    from apps.resultats.tests.test_validation import corriger_une_note

    epreuve, participations, jures, criteres, responsable = exemple_complet()
    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)
    corriger_une_note(epreuve, participations, jures, criteres, responsable)
    validation.corriger_classement(epreuve, responsable, "Note corrigée après approbation", confirmer_egalites=True)

    html = documents.proces_verbal(epreuve.categorie.concours)

    assert "Version 2" in html and "(corrigée)" in html and "Note corrigée après approbation" in html


@pytest.mark.django_db
def test_rec26_le_contenu_saisi_est_echappe_dans_le_pv():
    epreuve, participations, *_ = exemple_complet()
    Candidat.objects.filter(pk=participations["A"].candidat_id).update(nom="<script>alert(1)</script>")

    html = documents.proces_verbal(epreuve.categorie.concours)

    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


@pytest.mark.django_db
def test_un_mineur_sans_consentement_de_publication_n_apparait_qu_avec_l_initiale():
    epreuve, participations, _, _, responsable = exemple_complet()
    mineur = participations["C"]
    Candidat.objects.filter(pk=mineur.candidat_id).update(date_naissance=date(2015, 3, 3), nom="Traoré-secret", prenom="Awa")
    creer_consentement(mineur, consentement_publication_nom=False)
    validation.valider_classement(epreuve, responsable, confirmer_egalites=True)

    html = documents.proces_verbal(epreuve.categorie.concours)

    assert "Traoré-secret" not in html and "Awa T." in html


@pytest.mark.django_db
def test_un_mineur_avec_consentement_de_publication_apparait_en_entier():
    epreuve, participations, _, _, responsable = exemple_complet()
    mineur = participations["C"]
    Candidat.objects.filter(pk=mineur.candidat_id).update(date_naissance=date(2015, 3, 3), nom="Traoré-public", prenom="Awa")
    creer_consentement(mineur, consentement_publication_nom=True)

    html = documents.proces_verbal(epreuve.categorie.concours)

    assert "Awa Traoré-public" in html or "Awa" in html and "Traoré-public" in html


@pytest.mark.django_db
def test_le_pv_reprend_les_tirages_les_incidents_et_l_etat_du_journal_d_audit():
    epreuve, participations, jures, criteres, responsable = exemple_complet()
    epreuve2 = __import__("apps.prestations.tests.outils", fromlist=["x"]).creer_epreuve_ouverte(series=2)
    prestation = __import__("apps.prestations.tests.outils", fromlist=["x"]).creer_prestation(epreuve2)
    tirage = services_prestations.effectuer_tirage(prestation, uuid.uuid4(), terminal="Tablette 1")
    services_prestations.annuler_tirage(tirage, creer_utilisateur(), "Erreur d'appel du candidat")

    html = documents.proces_verbal(epreuve2.categorie.concours)

    assert "Tablette 1" in html and "Annulé" in html and "Erreur d&#x27;appel du candidat" in html
    assert "Tirage annulé : motif et auteur" in html
    assert "intacte" in html and "tirage.effectue" in html and "tirage.annule" in html


@pytest.mark.django_db
def test_le_pv_signale_un_journal_altere():
    epreuve, *_ = exemple_complet()
    organisation = epreuve.organisation
    from apps.audit.services import journaliser

    journaliser("a", organisation=organisation)
    with connection.cursor() as curseur:
        curseur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        curseur.execute("ALTER TABLE audit_entreeaudit DISABLE TRIGGER USER")
        curseur.execute("UPDATE audit_entreeaudit SET action = 'falsifiee' WHERE organisation_id = %s AND numero = 1", [organisation.pk])

    html = documents.proces_verbal(epreuve.categorie.concours)

    assert "ANOMALIE DÉTECTÉE" in html


@pytest.mark.django_db
def test_la_generation_du_pv_est_journalisee():
    epreuve, *_ = exemple_complet()
    operateur = creer_utilisateur()

    documents.proces_verbal(epreuve.categorie.concours, operateur)

    entree = EntreeAudit.objects.get(action="document.pv_genere")
    assert entree.auteur == operateur and entree.details == {"definitif": False}


# --- Export ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_l_export_contient_un_fichier_par_entite_avec_des_en_tetes_documentes():
    epreuve, *_ = exemple_complet()

    fichiers = lire_zip(documents.exporter_donnees(epreuve.categorie.concours))

    assert set(fichiers) == {"candidats.csv", "participations.csv", "prestations.csv", "tirages.csv", "notes.csv", "classements.csv", "LISEZMOI.txt"}
    for nom, (_, en_tetes) in documents.DOCUMENTATION.items():
        assert lignes_csv(fichiers[nom])[0] == en_tetes
        assert f"{nom} —" in fichiers["LISEZMOI.txt"]


@pytest.mark.django_db
def test_l_export_est_en_utf8_avec_point_virgule_et_les_accents_survivent():
    epreuve, participations, *_ = exemple_complet()
    Candidat.objects.filter(pk=participations["A"].candidat_id).update(nom="Koné", prenom="Élodie")
    contenu = documents.exporter_donnees(epreuve.categorie.concours)

    brut = zipfile.ZipFile(io.BytesIO(contenu)).read("candidats.csv")

    assert brut.startswith(b"\xef\xbb\xbf")  # marque UTF-8 : Excel reconnaît les accents
    assert any(ligne[1:3] == ["Koné", "Élodie"] for ligne in lignes_csv(brut.decode("utf-8-sig")))


@pytest.mark.django_db
def test_les_notes_exportees_sont_celles_des_evaluations_validees_seulement():
    epreuve, participations, jures, criteres, _ = exemple_complet()
    from apps.jury import evaluations
    from apps.prestations.models import Prestation

    prestation_a = Prestation.objects.get(participation=participations["A"])
    # Une note en brouillon d'un 4e juré n'est pas exportée
    nouveau = __import__("apps.commun.tests.outils", fromlist=["x"]).creer_jure(epreuve.organisation)
    from apps.jury.models import AffectationJury

    AffectationJury.objects.create(jure=nouveau, epreuve=epreuve)
    evaluations.enregistrer_brouillon(nouveau, prestation_a, {str(criteres[0].pk): 1})

    notes = lignes_csv(lire_zip(documents.exporter_donnees(epreuve.categorie.concours))["notes.csv"])[1:]

    assert len(notes) == 5 * 3 * 3  # 5 candidats x 3 jurés validés x 3 critères : le brouillon du 4e juré n'y est pas
    assert not any(ligne[2] == nouveau.nom_complet for ligne in notes)


@pytest.mark.django_db
def test_l_export_ne_contient_aucune_donnee_d_un_autre_client():
    epreuve, *_ = exemple_complet()
    from apps.commun.tests.outils import creer_categorie, creer_concours, creer_mission

    autre_client = creer_organisation()
    etranger = creer_candidat(autre_client, nom="Etranger-secret", prenom="X")
    creer_participation(creer_categorie(creer_concours(creer_mission(autre_client))), etranger)

    fichiers = lire_zip(documents.exporter_donnees(epreuve.categorie.concours))

    assert all("Etranger-secret" not in contenu for contenu in fichiers.values())


@pytest.mark.django_db
def test_rec26_une_formule_dans_un_nom_est_neutralisee_dans_le_tableur():
    epreuve, participations, *_ = exemple_complet()
    Candidat.objects.filter(pk=participations["A"].candidat_id).update(nom="=HYPERLINK(\"http://pirate\")", prenom="+cmd")

    candidats = lignes_csv(lire_zip(documents.exporter_donnees(epreuve.categorie.concours))["candidats.csv"])

    assert any(ligne[1].startswith("'=HYPERLINK") and ligne[2] == "'+cmd" for ligne in candidats)
    assert documents.neutraliser("normal") == "normal" and documents.neutraliser("@x") == "'@x" and documents.neutraliser(None) == ""


@pytest.mark.django_db
def test_chaque_export_est_journalise_avec_le_nombre_de_lignes():
    epreuve, *_ = exemple_complet()
    operateur = creer_utilisateur()

    documents.exporter_donnees(epreuve.categorie.concours, operateur)

    entree = EntreeAudit.objects.get(action="export.donnees")
    assert entree.auteur == operateur and entree.details["participations.csv"] == 5


# --- Accès (vues) ---------------------------------------------------------------------------------------


def poste_vues(client):
    epreuve, participations, jures, criteres, responsable = exemple_complet()
    concours = epreuve.categorie.concours
    operateur = creer_utilisateur(is_staff=True)
    AffectationOperateur.objects.create(mission=concours.mission, utilisateur=operateur)
    return concours, operateur, responsable


@pytest.mark.django_db
def test_les_documents_exigent_une_connexion(client):
    concours, *_ = poste_vues(client)

    for nom in ("proces_verbal", "export"):
        reponse = client.get(reverse(f"resultats:{nom}", args=[concours.pk]))
        assert reponse.status_code == 302 and "login" in reponse.url


@pytest.mark.django_db
def test_l_operateur_affecte_et_le_responsable_du_client_telechargent(client):
    concours, operateur, responsable = poste_vues(client)

    for utilisateur in (operateur, responsable):
        client.force_login(utilisateur)
        pv = client.get(reverse("resultats:proces_verbal", args=[concours.pk]))
        export = client.get(reverse("resultats:export", args=[concours.pk]))
        assert pv.status_code == 200 and "Procès-verbal" in pv.content.decode()
        assert export.status_code == 200 and export["Content-Type"] == "application/zip"
        assert "attachment" in export["Content-Disposition"]


@pytest.mark.django_db
def test_rec29_un_utilisateur_sans_acces_obtient_404(client):
    concours, *_ = poste_vues(client)
    etranger = creer_utilisateur(is_staff=True)
    AffectationOperateur.objects.create(mission=__import__("apps.commun.tests.outils", fromlist=["x"]).creer_mission(), utilisateur=etranger)
    autre_responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT)

    for utilisateur in (etranger, autre_responsable):
        client.force_login(utilisateur)
        assert client.get(reverse("resultats:proces_verbal", args=[concours.pk])).status_code == 404
        assert client.get(reverse("resultats:export", args=[concours.pk])).status_code == 404


# --- REC-42 : 500 candidats -----------------------------------------------------------------------------------


@pytest.mark.django_db
def test_rec42_le_pv_de_500_candidats_est_genere_en_moins_de_30_secondes_sans_requete_par_candidat():
    from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
    from django.test.utils import CaptureQueriesContext

    epreuve = creer_epreuve_ouverte(series=1)
    organisation, categorie, concours = epreuve.organisation, epreuve.categorie, epreuve.categorie.concours
    serie = epreuve.lot.series.get()
    session = creer_prestation(epreuve).session
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=organisation)
    candidats = Candidat.objects.bulk_create(
        [Candidat(organisation=organisation, nom=f"Nom{i}", prenom=f"Prenom{i}", date_naissance=date(1990, 1, 1)) for i in range(500)]
    )
    participations = Participation.objects.bulk_create([
        Participation(organisation=organisation, candidat=c, concours=concours, categorie=categorie, numero_candidat=1000 + i, statut="admis")
        for i, c in enumerate(candidats)
    ])
    prestations = Prestation.objects.bulk_create([
        Prestation(organisation=organisation, participation=p, epreuve=epreuve, session=session, rang_passage=100000 + i, etat="cloturee")
        for i, p in enumerate(participations)
    ])
    Tirage.objects.bulk_create([
        Tirage(organisation=organisation, prestation=p, serie=serie, rang=1, id_demande=uuid.uuid4(), terminal="T") for p in prestations
    ])
    classement = Classement.objects.create(
        epreuve=epreuve, version=1, valide_par=responsable, valide_le=timezone.now(), regle_classement="moyenne", empreinte="a" * 64
    )
    LigneDeClassement.objects.bulk_create([
        LigneDeClassement(organisation=organisation, classement=classement, participation=p, rang=i + 1, score=500 - i,
                          evaluations_validees=3, evaluations_attendues=3)
        for i, p in enumerate(participations)
    ])

    debut = time.perf_counter()
    with CaptureQueriesContext(connection) as requetes:
        html = documents.proces_verbal(concours, responsable)
    duree = time.perf_counter() - debut

    assert duree < 30 and html.count("<tr>") > 1000  # 500 lignes de classement + 500 lignes de tirages
    assert len(requetes) < 40  # un nombre CONSTANT de requêtes, pas une par candidat
