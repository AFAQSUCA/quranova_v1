# Chapitre 24 — Procès-verbal, exports et sauvegarde (itération 4, étapes 4g et 4h)

> **Commit de référence :** `47061de` · **Durée :** 6 à 8 heures · **Résultat :** le procès-verbal imprimable, l'export CSV des données, la sauvegarde PostgreSQL planifiable et sa restauration vérifiée. **30 tests**.

## Objectif

| Règle | Où elle est appliquée |
|---|---|
| **REC-16, §14.2** : seuls les classements validés figurent dans le procès-verbal | `contexte_pv` ; une épreuve non validée est mentionnée, sans aucun résultat |
| **§11.1, §16.2** : mineurs | un mineur (ou d'âge inconnu, D13) sans consentement de publication n'apparaît qu'avec son prénom et l'initiale de son nom |
| **REC-26** : injection | le contenu saisi est échappé dans le procès-verbal ; une cellule d'export commençant par `= + - @` est neutralisée |
| **REC-42** : 500 candidats en moins de 30 s | un test le mesure (en pratique : environ 1 s), avec un nombre **constant** de requêtes |
| **§17.1** : export CSV | UTF-8, point-virgule, un fichier par entité, en-têtes documentés, journalisé, sans donnée d'un autre client |
| **§15.5, REC-18** | sauvegarde `pg_dump` + empreinte SHA-256, rotation, restauration vérifiée par `verifier_audit` |

## Une décision à prendre : le PDF

Le procès-verbal est produit en **HTML prêt à imprimer** (feuille de style `@page` : A4, numéros de page). Depuis le navigateur, « Imprimer → Enregistrer en PDF » donne le PDF. Générer le PDF **côté serveur** demanderait la bibliothèque WeasyPrint (nouvelle dépendance ; sous Windows, elle exige les bibliothèques Pango via MSYS2, voir `DEMARRAGE.md`). Tant que cette dépendance n'est pas validée, on n'ajoute rien.

## Étape A — Le procès-verbal et l'export

**Fichier `apps\resultats\tests\test_documents.py`**

```python
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
```

**Fichier `apps\resultats\documents.py`**

```python
"""Documents remis au client : procès-verbal et export des données (§11, §17.1 ; REC-16, REC-42).

- Le procès-verbal ne contient QUE des classements validés par le responsable client (REC-16, §14.2) ; une épreuve
  non validée est mentionnée comme telle, sans aucun résultat.
- Il reprend l'historique des tirages (série attribuée, horodatage, annulations), les incidents (tirages annulés) et
  l'état du journal d'audit du client (nombre d'entrées, empreinte de fin de chaîne, résultat de la vérification).
- L'export CSV est en UTF-8 (avec marque d'ordre des octets, pour qu'Excel reconnaisse les accents), séparateur
  point-virgule, un fichier par entité, avec un fichier de documentation des en-têtes (§17.1). Il ne contient aucune
  donnée d'un autre client, et chaque export est journalisé.
- La génération est réalisée en HTML prêt à imprimer ; le rendu PDF est un simple « enregistrer en PDF » du navigateur
  tant que la dépendance de génération de PDF n'est pas validée.
"""
import csv
import io
import zipfile
from collections import Counter
from datetime import timezone as fuseau_utc

from django.template.loader import render_to_string
from django.utils import timezone

from apps.audit.models import ChaineAudit, EntreeAudit
from apps.audit.services import journaliser, verifier_chaine
from apps.candidats.models import Consentement, Participation
from apps.candidats.services import est_mineur
from apps.concours.models import Epreuve
from apps.jury.models import Evaluation
from apps.prestations.models import Prestation, Tirage
from apps.resultats import validation


def libelle_candidat(participation, consentements_publication):
    """Nom affiché dans un classement : le nom complet, sauf mineur sans consentement de publication (§11.1, §16.2).

    Un mineur (ou dont l'âge est inconnu : prudence, D13) sans consentement de publication du nom apparaît avec son
    prénom et l'initiale de son nom.
    """
    candidat = participation.candidat
    if est_mineur(participation) is not False and participation.pk not in consentements_publication:
        return f"{candidat.prenom} {candidat.nom[:1]}."
    return candidat.nom_complet


def _consentements_publication(concours):
    return set(
        Consentement.objects.filter(
            participation__concours=concours, statut=Consentement.Statut.VALIDE, consentement_publication_nom=True
        ).values_list("participation_id", flat=True)
    )


def contexte_pv(concours, auteur=None):
    epreuves = list(
        Epreuve.objects.filter(categorie__concours=concours).select_related("categorie").order_by("categorie__nom", "ordre")
    )
    consentements = _consentements_publication(concours)
    sections, non_valides = [], []
    for epreuve in epreuves:
        classement = validation.classement_definitif(epreuve)
        if classement is None:
            non_valides.append(f"{epreuve.categorie.nom} — {epreuve.nom}")
            sections.append({"epreuve": epreuve, "classement": None, "lignes": []})
            continue
        lignes = list(
            classement.lignes.select_related("participation__candidat", "participation__concours").order_by("rang", "participation__numero_candidat")
        )
        sections.append({
            "epreuve": epreuve, "classement": classement,
            "lignes": [
                {"rang": l.rang, "ex_aequo": l.ex_aequo, "numero": l.participation.numero_candidat,
                 "nom": libelle_candidat(l.participation, consentements), "score": l.score,
                 "evaluations": f"{l.evaluations_validees}/{l.evaluations_attendues}"}
                for l in lignes
            ],
        })
    tirages = list(
        Tirage.objects.filter(prestation__epreuve__categorie__concours=concours)
        .select_related("serie", "prestation__participation__candidat", "prestation__participation__concours",
                        "prestation__epreuve", "annule_par")
        .order_by("cree_le")
    )
    historique = [
        {"horodatage": t.cree_le, "numero": t.prestation.participation.numero_candidat,
         "nom": libelle_candidat(t.prestation.participation, consentements), "epreuve": t.prestation.epreuve.nom,
         "serie": t.serie.libelle, "rang": t.rang, "terminal": t.terminal, "statut": t.get_statut_display(),
         "annulation": (f"{t.motif_annulation} — {t.annule_par}" if t.statut == Tirage.Statut.ANNULE else "")}
        for t in tirages
    ]
    chaine = ChaineAudit.objects.filter(organisation=concours.organisation).first()
    problemes = verifier_chaine(concours.organisation)
    actions = Counter(EntreeAudit.objects.filter(organisation=concours.organisation).values_list("action", flat=True))
    return {
        "concours": concours, "auteur": auteur, "genere_le": timezone.now(), "sections": sections,
        "non_valides": non_valides, "definitif": not non_valides and bool(sections),
        "historique": historique, "incidents": [h for h in historique if h["annulation"]],
        "audit": {
            "entrees": chaine.dernier_numero if chaine else 0,
            "empreinte": chaine.derniere_empreinte if chaine else "",
            "intacte": not problemes, "problemes": problemes,
            "actions": sorted(actions.items()),
        },
    }


def proces_verbal(concours, auteur=None):
    """Le procès-verbal, en HTML prêt à imprimer (journalisé)."""
    html = render_to_string("documents/pv.html", contexte_pv(concours, auteur))
    journaliser(
        "document.pv_genere", organisation=concours.organisation, auteur=auteur, objet=concours,
        details={"definitif": not any(s["classement"] is None for s in contexte_pv_resume(concours))},
    )
    return html


def contexte_pv_resume(concours):
    return [
        {"classement": validation.classement_definitif(e)}
        for e in Epreuve.objects.filter(categorie__concours=concours)
    ]


# --- Export CSV (§17.1) ---------------------------------------------------------------------------------------


def neutraliser(valeur):
    """Empêche l'injection de formule : une cellule qui commence par = + - @ serait interprétée par un tableur (REC-26)."""
    texte = "" if valeur is None else str(valeur)
    return "'" + texte if texte[:1] in ("=", "+", "-", "@", "\t", "\r") else texte


def _csv(en_tetes, lignes):
    sortie = io.StringIO(newline="")
    ecrivain = csv.writer(sortie, delimiter=";", lineterminator="\r\n")
    ecrivain.writerow(en_tetes)
    for ligne in lignes:
        ecrivain.writerow([neutraliser(c) for c in ligne])
    return sortie.getvalue().encode("utf-8-sig")


DOCUMENTATION = {
    "candidats.csv": ("Un candidat par ligne", ["id", "nom", "prenom", "date_naissance (AAAA-MM-JJ)", "sexe (M/F)", "ville", "structure"]),
    "participations.csv": ("Inscription d'un candidat à une catégorie", ["numero_candidat", "candidat_id", "categorie", "statut"]),
    "prestations.csv": ("Passage d'un candidat à une épreuve", ["prestation_id", "numero_candidat", "epreuve", "session", "rang_passage", "etat"]),
    "tirages.csv": ("Historique des tirages, annulations comprises", ["horodatage (UTC)", "numero_candidat", "epreuve", "serie", "rang", "terminal", "statut", "motif_annulation"]),
    "notes.csv": ("Notes des évaluations VALIDÉES, une ligne par note", ["numero_candidat", "epreuve", "juré", "critere", "valeur"]),
    "classements.csv": ("Classements DÉFINITIFS validés (toutes versions)", ["epreuve", "version", "correction (oui/non)", "rang", "ex_aequo (oui/non)", "numero_candidat", "score", "valide_le (UTC)"]),
}


def exporter_donnees(concours, auteur=None):
    """Un ZIP de fichiers CSV du concours, plus la documentation des en-têtes. Journalisé."""
    organisation = concours.organisation
    participations = list(
        Participation.objects.filter(concours=concours).select_related("candidat", "categorie").order_by("numero_candidat")
    )
    prestations = list(
        Prestation.objects.filter(participation__concours=concours)
        .select_related("participation", "epreuve", "session").order_by("rang_passage")
    )
    tirages = Tirage.objects.filter(prestation__epreuve__categorie__concours=concours).select_related(
        "serie", "prestation__participation", "prestation__epreuve").order_by("cree_le")
    evaluations = Evaluation.objects.filter(prestation__epreuve__categorie__concours=concours, statut=Evaluation.Statut.VALIDEE)
    notes = [
        (e.prestation.participation.numero_candidat, e.prestation.epreuve.nom, e.jure.nom_complet, n.critere.libelle, n.valeur)
        for e in evaluations.select_related("prestation__participation", "prestation__epreuve", "jure")
        for n in e.notes.select_related("critere")
    ]
    classements = []
    for epreuve in Epreuve.objects.filter(categorie__concours=concours):
        for classement in validation.historique(epreuve):
            for l in classement.lignes.select_related("participation"):
                classements.append((epreuve.nom, classement.version, "oui" if classement.est_correction else "non", l.rang,
                                    "oui" if l.ex_aequo else "non", l.participation.numero_candidat, l.score,
                                    classement.valide_le.astimezone(fuseau_utc.utc).isoformat()))
    fichiers = {
        "candidats.csv": [(p.candidat.pk, p.candidat.nom, p.candidat.prenom, p.candidat.date_naissance or "", p.candidat.sexe,
                           p.candidat.ville, p.candidat.structure) for p in participations],
        "participations.csv": [(p.numero_candidat, p.candidat_id, p.categorie.nom, p.statut) for p in participations],
        "prestations.csv": [(p.pk, p.participation.numero_candidat, p.epreuve.nom, p.session.nom, p.rang_passage, p.etat) for p in prestations],
        "tirages.csv": [(t.cree_le.astimezone(fuseau_utc.utc).isoformat(), t.prestation.participation.numero_candidat,
                         t.prestation.epreuve.nom, t.serie.libelle, t.rang, t.terminal, t.statut, t.motif_annulation) for t in tirages],
        "notes.csv": notes,
        "classements.csv": classements,
    }
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as archive:
        for nom, lignes in fichiers.items():
            archive.writestr(nom, _csv(DOCUMENTATION[nom][1], lignes))
        lisez_moi = ["Export des données du concours « %s » — %s" % (concours.nom, organisation.nom), "",
                     "Format : CSV, UTF-8 (avec marque d'ordre des octets), séparateur point-virgule, fins de ligne CRLF.",
                     "Une cellule commençant par = + - @ est précédée d'une apostrophe (protection contre l'injection de formule).", ""]
        for nom, (description, en_tetes) in DOCUMENTATION.items():
            lisez_moi += [f"{nom} — {description}", "  colonnes : " + " ; ".join(en_tetes), ""]
        archive.writestr("LISEZMOI.txt", "\r\n".join(lisez_moi).encode("utf-8-sig"))
    journaliser(
        "export.donnees", organisation=organisation, auteur=auteur, objet=concours,
        details={nom: len(lignes) for nom, lignes in fichiers.items()},
    )
    return tampon.getvalue()
```

**Fichier `templates\documents\pv.html`**

```html
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Procès-verbal — {{ concours.nom }}</title>
<style>
@page { size: A4; margin: 18mm 15mm; @bottom-right { content: "Page " counter(page) " / " counter(pages); } }
body { font-family: "Segoe UI", system-ui, sans-serif; font-size: 11pt; color: #111; }
h1 { font-size: 20pt; margin-bottom: 0; } h2 { font-size: 14pt; border-bottom: 2px solid #333; margin-top: 1.6em; }
h3 { font-size: 12pt; margin-bottom: .2em; }
table { border-collapse: collapse; width: 100%; margin: .4em 0 1em; } th, td { border: 1px solid #888; padding: 3px 6px; text-align: left; font-size: 10pt; }
th { background: #eee; } .droite { text-align: right; } tr { page-break-inside: avoid; }
.bandeau { padding: .4em .8em; border: 2px solid #333; margin: 1em 0; } .provisoire { border-color: #a12; color: #a12; font-weight: bold; }
.signatures { display: flex; gap: 3em; margin-top: 3em; page-break-inside: avoid; } .signatures div { flex: 1; border-top: 1px solid #333; padding-top: .3em; }
.empreinte { font-family: monospace; font-size: 9pt; word-break: break-all; }
@media screen { body { max-width: 190mm; margin: 1em auto; padding: 0 1em; } }
</style>
</head>
<body>
<h1>Procès-verbal {% if definitif %}définitif{% else %}provisoire{% endif %}</h1>
<p>{{ concours.nom }} {{ concours.edition }} — {{ concours.mission.organisation.nom }}<br>
{{ concours.mission.lieu }}, du {{ concours.date_debut|date:"d/m/Y" }} au {{ concours.date_fin|date:"d/m/Y" }}<br>
Document généré le {{ genere_le|date:"d/m/Y à H:i" }}{% if auteur %} par {{ auteur }}{% endif %}.</p>

{% if non_valides %}
<div class="bandeau provisoire">Ce procès-verbal est PROVISOIRE : le classement des épreuves suivantes n'a pas été validé par le responsable
du client et n'y figure donc pas :
<ul>{% for e in non_valides %}<li>{{ e }}</li>{% endfor %}</ul></div>
{% else %}
<div class="bandeau">Tous les classements ci-dessous ont été validés par le responsable du client.</div>
{% endif %}

<h2>1. Classements définitifs</h2>
{% for s in sections %}
  <h3>{{ s.epreuve.categorie.nom }} — {{ s.epreuve.nom }}</h3>
  {% if s.classement %}
  <p>Version {{ s.classement.version }}{% if s.classement.est_correction %} <strong>(corrigée)</strong> — motif : {{ s.classement.motif_correction }}{% endif %},
  validée le {{ s.classement.valide_le|date:"d/m/Y à H:i" }} par {{ s.classement.valide_par }}. Règle : {{ s.classement.regle_classement }}{% if s.classement.regle_departage %}, départage : {{ s.classement.regle_departage }}{% endif %}.</p>
  <table><tr><th>Rang</th><th>N°</th><th>Candidat</th><th class="droite">Score</th><th>Évaluations</th></tr>
  {% for l in s.lignes %}<tr><td>{% if l.rang %}{{ l.rang }}{% if l.ex_aequo %} (ex aequo){% endif %}{% else %}—{% endif %}</td><td>{{ l.numero }}</td><td>{{ l.nom }}</td><td class="droite">{{ l.score|default_if_none:"—" }}</td><td>{{ l.evaluations }}</td></tr>{% endfor %}</table>
  {% else %}<p><em>Classement non validé : aucun résultat dans ce document.</em></p>{% endif %}
{% empty %}<p>Aucune épreuve.</p>{% endfor %}

<h2>2. Historique des tirages</h2>
<table><tr><th>Horodatage</th><th>N°</th><th>Candidat</th><th>Épreuve</th><th>Série</th><th>Terminal</th><th>Statut</th></tr>
{% for t in historique %}<tr><td>{{ t.horodatage|date:"d/m/Y H:i:s" }}</td><td>{{ t.numero }}</td><td>{{ t.nom }}</td><td>{{ t.epreuve }}</td><td>{{ t.serie }}{% if t.rang > 1 %} (tirage {{ t.rang }}){% endif %}</td><td>{{ t.terminal }}</td><td>{{ t.statut }}</td></tr>{% empty %}<tr><td colspan="7">Aucun tirage.</td></tr>{% endfor %}</table>

<h2>3. Incidents</h2>
{% if incidents %}<table><tr><th>Horodatage</th><th>N°</th><th>Série</th><th>Tirage annulé : motif et auteur</th></tr>
{% for t in incidents %}<tr><td>{{ t.horodatage|date:"d/m/Y H:i:s" }}</td><td>{{ t.numero }}</td><td>{{ t.serie }}</td><td>{{ t.annulation }}</td></tr>{% endfor %}</table>
{% else %}<p>Aucun incident enregistré (aucun tirage annulé).</p>{% endif %}

<h2>4. Journal d'audit</h2>
<p>{{ audit.entrees }} entrée(s) dans le journal de ce client. Vérification de l'intégrité de la chaîne d'empreintes :
<strong>{% if audit.intacte %}intacte{% else %}ANOMALIE DÉTECTÉE{% endif %}</strong>.</p>
{% if not audit.intacte %}<ul>{% for p in audit.problemes %}<li>{{ p }}</li>{% endfor %}</ul>{% endif %}
<p>Empreinte de fin de chaîne :<br><span class="empreinte">{{ audit.empreinte }}</span></p>
<table><tr><th>Opération</th><th class="droite">Nombre</th></tr>{% for action, n in audit.actions %}<tr><td>{{ action }}</td><td class="droite">{{ n }}</td></tr>{% endfor %}</table>

<div class="signatures"><div>Le responsable du client<br><br><br></div><div>L'opérateur du prestataire<br><br><br></div></div>
</body>
</html>
```

**Fichier `apps\resultats\views.py`**

```python
"""Remise des documents : procès-verbal (HTML prêt à imprimer) et export CSV (§11, §17.1).

Accès : le personnel du prestataire affecté à la mission, ou le responsable du client concerné. Sinon « introuvable »,
sans rien révéler (REC-25, REC-29).
"""
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.concours.models import Concours
from apps.resultats import documents
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles


def _concours_autorise(request, concours_id):
    concours = get_object_or_404(Concours.objects.select_related("mission__organisation"), pk=concours_id)
    utilisateur = request.user
    autorise = missions_accessibles(utilisateur).filter(pk=concours.mission_id).exists() and utilisateur.role in (
        Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR, Utilisateur.Role.RESPONSABLE_CLIENT
    )
    if not autorise:
        raise Http404
    return concours


@require_GET
def proces_verbal(request, concours_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    concours = _concours_autorise(request, concours_id)
    reponse = HttpResponse(documents.proces_verbal(concours, request.user))
    reponse["Cache-Control"] = "no-store"
    return reponse


@require_GET
def export(request, concours_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    concours = _concours_autorise(request, concours_id)
    reponse = HttpResponse(documents.exporter_donnees(concours, request.user), content_type="application/zip")
    reponse["Content-Disposition"] = f'attachment; filename="export-{concours.pk}.zip"'
    reponse["Cache-Control"] = "no-store"
    return reponse
```

**Fichier `apps\resultats\urls.py`**

```python
from django.urls import path

from apps.resultats import views

app_name = "resultats"

urlpatterns = [
    path("documents/pv/<uuid:concours_id>/", views.proces_verbal, name="proces_verbal"),
    path("documents/export/<uuid:concours_id>/", views.export, name="export"),
]
```

**Fichier `config\urls.py`**

```python
"""Routes racine du projet QURANOVA."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="accueil.html"), name="accueil"),
    path("admin/", admin.site.urls),
    path("", include("apps.prestations.urls")),
    path("", include("apps.presentation.urls")),
    path("", include("apps.jury.urls")),
    path("", include("apps.resultats.urls")),
]
```

```powershell
pytest apps\resultats\tests\test_documents.py
```

Dans l'administration, la fiche d'un **concours** affiche deux liens : « Procès-verbal (imprimable) » et « Export des données (CSV) ».

## Étape B — La sauvegarde et la restauration

**Fichier `apps\commun\tests\test_sauvegarde.py`**

```python
"""Sauvegarde et restauration (§15.5, REC-18). Vraies transactions : pg_dump lit la base depuis un autre processus."""
import uuid
from io import StringIO
from pathlib import Path

import psycopg
import pytest
from django.core.management import CommandError, call_command
from django.db import connection

from apps.audit.models import EntreeAudit
from apps.commun import sauvegarde
from apps.commun.tests.outils import creer_organisation, creer_utilisateur
from apps.prestations import services
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation
from apps.audit.services import journaliser, verifier_chaine

pytestmark = pytest.mark.skipif(
    __import__("shutil").which("pg_dump") is None, reason="pg_dump n'est pas installé (PostgreSQL client)"
)


@pytest.fixture
def base_restauree():
    """Un nom de base de restauration unique ; supprimée à la fin du test."""
    nom = f"test_restauration_{uuid.uuid4().hex[:8]}"
    yield nom
    p = sauvegarde._parametres("postgres")
    with psycopg.connect(**p, autocommit=True) as maintenance:
        maintenance.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')


def compter(base, requete):
    with psycopg.connect(**sauvegarde._parametres(base)) as c:
        return c.execute(requete).fetchone()[0]


@pytest.mark.django_db(transaction=True)
def test_rec18_restaurer_une_sauvegarde_donne_des_donnees_coherentes_et_exploitables(tmp_path, base_restauree):
    epreuve = creer_epreuve_ouverte(series=3)
    for _ in range(2):
        services.effectuer_tirage(creer_prestation(epreuve), uuid.uuid4(), terminal="Tablette 1")
    fichier = sauvegarde.sauvegarder(tmp_path)

    sauvegarde.restaurer(fichier, base_restauree)  # inclut verifier_audit sur la base restaurée

    for requete in ("select count(*) from prestations_tirage", "select count(*) from audit_entreeaudit",
                    "select count(*) from questions_serie", "select count(*) from candidats_participation"):
        assert compter(base_restauree, requete) == compter(connection.settings_dict["NAME"], requete) > 0
    assert compter(base_restauree, "select count(*) from audit_entreeaudit where action = 'tirage.effectue'") == 2


@pytest.mark.django_db(transaction=True)
def test_la_restauration_detecte_un_journal_d_audit_altere_dans_la_sauvegarde(tmp_path, base_restauree):
    organisation = creer_organisation()
    journaliser("a", organisation=organisation)
    journaliser("b", organisation=organisation)
    with connection.cursor() as curseur:  # on falsifie le journal AVANT la sauvegarde
        curseur.execute("ALTER TABLE audit_entreeaudit DISABLE TRIGGER USER")
        curseur.execute("UPDATE audit_entreeaudit SET action = 'falsifiee' WHERE numero = 1")
        curseur.execute("ALTER TABLE audit_entreeaudit ENABLE TRIGGER USER")
    fichier = sauvegarde.sauvegarder(tmp_path)

    with pytest.raises(sauvegarde.SauvegardeError, match="incohérente"):
        sauvegarde.restaurer(fichier, base_restauree)


@pytest.mark.django_db(transaction=True)
def test_une_sauvegarde_alteree_est_refusee_avant_toute_restauration(tmp_path, base_restauree):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)
    contenu = bytearray(fichier.read_bytes())
    contenu[len(contenu) // 2] ^= 0xFF
    fichier.write_bytes(bytes(contenu))

    with pytest.raises(sauvegarde.SauvegardeError, match="altérée"):
        sauvegarde.restaurer(fichier, base_restauree)
    with psycopg.connect(**sauvegarde._parametres("postgres")) as c:
        assert c.execute("select 1 from pg_database where datname = %s", [base_restauree]).fetchone() is None


@pytest.mark.django_db(transaction=True)
def test_une_sauvegarde_sans_empreinte_est_refusee(tmp_path, base_restauree):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)
    Path(f"{fichier}.sha256").unlink()

    with pytest.raises(sauvegarde.SauvegardeError, match="empreinte"):
        sauvegarde.restaurer(fichier, base_restauree)


@pytest.mark.django_db(transaction=True)
def test_on_ne_restaure_jamais_sur_la_base_en_service(tmp_path):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)

    with pytest.raises(sauvegarde.SauvegardeError, match="base en service"):
        sauvegarde.restaurer(fichier, connection.settings_dict["NAME"], ecraser=True)


@pytest.mark.django_db(transaction=True)
def test_on_n_ecrase_une_base_existante_qu_a_la_demande(tmp_path, base_restauree):
    creer_organisation()
    fichier = sauvegarde.sauvegarder(tmp_path)
    sauvegarde.restaurer(fichier, base_restauree)

    with pytest.raises(sauvegarde.SauvegardeError, match="existe déjà"):
        sauvegarde.restaurer(fichier, base_restauree)
    sauvegarde.restaurer(fichier, base_restauree, ecraser=True)


@pytest.mark.django_db(transaction=True)
def test_la_rotation_garde_les_plus_recentes_et_supprime_aussi_les_empreintes(tmp_path):
    creer_organisation()
    from datetime import datetime, timedelta, timezone

    depart = datetime(2027, 1, 20, 9, 0, tzinfo=timezone.utc)
    for i in range(4):
        sauvegarde.sauvegarder(tmp_path, conserver=2, maintenant=depart + timedelta(minutes=15 * i))

    dumps = sorted(p.name for p in tmp_path.glob("*.dump"))
    assert dumps == ["quranova-20270120-093000.dump", "quranova-20270120-094500.dump"]
    assert len(list(tmp_path.glob("*.sha256"))) == 2


@pytest.mark.django_db(transaction=True)
def test_aucun_fichier_partiel_ne_reste_apres_un_echec(tmp_path, monkeypatch):
    """Une base inexistante fait échouer pg_dump : ni sauvegarde ni fichier temporaire ne doivent subsister."""
    monkeypatch.setattr(
        sauvegarde, "_parametres",
        lambda base=None: {"dbname": "base_inexistante_xyz", "host": "localhost", "port": "5432", "user": "quranova", "password": "mauvais"},
    )

    with pytest.raises(sauvegarde.SauvegardeError, match="pg_dump a échoué"):
        sauvegarde.sauvegarder(tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.django_db(transaction=True)
def test_un_dossier_inutilisable_est_signale(tmp_path):
    fichier = tmp_path / "pas-un-dossier"
    fichier.write_text("x")

    with pytest.raises(sauvegarde.SauvegardeError, match="Dossier de sauvegarde inutilisable"):
        sauvegarde.sauvegarder(fichier / "sous-dossier")


@pytest.mark.django_db(transaction=True)
def test_l_outil_pg_dump_absent_donne_une_explication_windows(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nulle-part")
    monkeypatch.delenv("PG_BIN", raising=False)

    with pytest.raises(sauvegarde.SauvegardeError, match="PATH"):
        sauvegarde.sauvegarder(tmp_path)


@pytest.mark.django_db(transaction=True)
def test_les_commandes_sauvegarder_et_restaurer(tmp_path, base_restauree):
    creer_organisation()
    sortie = StringIO()

    call_command("sauvegarder", "--dossier", str(tmp_path), "--conserver", "5", stdout=sortie)
    (fichier,) = tmp_path.glob("*.dump")
    call_command("restaurer", str(fichier), "--vers-base", base_restauree, stdout=sortie)

    assert "Sauvegarde écrite" in sortie.getvalue() and "restaurée et vérifiée" in sortie.getvalue()
    entree = EntreeAudit.objects.get(action="sauvegarde.effectuee")
    assert entree.organisation is None and entree.details["fichier"] == fichier.name  # chaîne « système »
    with pytest.raises(CommandError, match="altérée|empreinte|introuvable"):
        call_command("restaurer", str(tmp_path / "absent.dump"), "--vers-base", base_restauree + "x")
```

**Fichier `apps\commun\sauvegarde.py`**

```python
"""Sauvegarde et restauration PostgreSQL du serveur de salle (§15.5, REC-18).

Une sauvegarde est un fichier ``pg_dump`` au format « custom » (compressé, restaurable table par table) accompagné de
son empreinte SHA-256 : avant toute restauration, on vérifie que le fichier n'a pas été altéré ni tronqué (disque
externe débranché en cours d'écriture, par exemple). Les anciennes sauvegardes sont supprimées au-delà d'un nombre
conservé (rotation).
"""
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from django.conf import settings
from django.db import connection
from django.utils import timezone

PREFIXE = "quranova-"
SUFFIXE = ".dump"


class SauvegardeError(Exception):
    pass


def _outil(nom):
    chemin = shutil.which(nom) or (shutil.which(str(Path(os.environ["PG_BIN"]) / nom)) if os.environ.get("PG_BIN") else None)
    if chemin is None:
        raise SauvegardeError(
            f"« {nom} » est introuvable. Ajoutez le dossier « bin » de PostgreSQL au PATH (Windows : "
            f"C:\\Program Files\\PostgreSQL\\<version>\\bin) ou définissez la variable PG_BIN."
        )
    return chemin


def _parametres(base=None):
    reglages = connection.settings_dict
    return {
        "dbname": base or reglages["NAME"], "host": reglages.get("HOST") or "localhost",
        "port": str(reglages.get("PORT") or "5432"), "user": reglages["USER"], "password": reglages.get("PASSWORD") or "",
    }


def _environnement(parametres):
    return {**os.environ, "PGPASSWORD": parametres["password"]}


def empreinte_fichier(chemin):
    sha = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
            sha.update(bloc)
    return sha.hexdigest()


def sauvegarder(dossier, conserver=96, maintenant=None):
    """Écrit une sauvegarde horodatée dans ``dossier`` ; renvoie son chemin. Lève ``SauvegardeError`` en cas d'échec."""
    dossier = Path(dossier)
    try:
        dossier.mkdir(parents=True, exist_ok=True)
    except OSError as erreur:
        raise SauvegardeError(f"Dossier de sauvegarde inutilisable ({dossier}) : {erreur}") from None
    maintenant = maintenant or timezone.now()
    cible = dossier / f"{PREFIXE}{maintenant.strftime('%Y%m%d-%H%M%S')}{SUFFIXE}"
    p = _parametres()
    temporaire = cible.with_suffix(".en-cours")
    commande = [_outil("pg_dump"), "--format=custom", "--no-owner", f"--file={temporaire}", "--host", p["host"],
                "--port", p["port"], "--username", p["user"], p["dbname"]]
    resultat = subprocess.run(commande, env=_environnement(p), capture_output=True, text=True)
    if resultat.returncode != 0 or not temporaire.exists() or temporaire.stat().st_size == 0:
        temporaire.unlink(missing_ok=True)
        raise SauvegardeError(f"pg_dump a échoué : {resultat.stderr.strip() or 'fichier vide'}")
    verification = subprocess.run([_outil("pg_restore"), "--list", str(temporaire)], capture_output=True, text=True)
    if verification.returncode != 0:
        temporaire.unlink(missing_ok=True)
        raise SauvegardeError(f"La sauvegarde produite est illisible : {verification.stderr.strip()}")
    temporaire.replace(cible)  # le fichier n'apparaît sous son vrai nom qu'une fois complet et vérifié
    Path(f"{cible}.sha256").write_text(f"{empreinte_fichier(cible)}  {cible.name}\n", encoding="utf-8")
    _faire_tourner(dossier, conserver)
    return cible


def _faire_tourner(dossier, conserver):
    anciennes = sorted(dossier.glob(f"{PREFIXE}*{SUFFIXE}"))
    for ancienne in anciennes[: max(0, len(anciennes) - conserver)]:
        ancienne.unlink(missing_ok=True)
        Path(f"{ancienne}.sha256").unlink(missing_ok=True)


def verifier_sauvegarde(fichier):
    """Vérifie l'empreinte enregistrée à côté du fichier ; refuse un fichier altéré ou sans empreinte."""
    fichier = Path(fichier)
    if not fichier.is_file():
        raise SauvegardeError(f"Fichier introuvable : {fichier}")
    empreinte_attendue = Path(f"{fichier}.sha256")
    if not empreinte_attendue.is_file():
        raise SauvegardeError("Aucune empreinte (.sha256) à côté de la sauvegarde : intégrité invérifiable.")
    if empreinte_attendue.read_text(encoding="utf-8").split()[0] != empreinte_fichier(fichier):
        raise SauvegardeError("La sauvegarde est altérée ou incomplète : son empreinte ne correspond pas.")


def restaurer(fichier, vers_base, ecraser=False, verifier=True):
    """Restaure ``fichier`` dans la base ``vers_base`` (créée) ; ne touche JAMAIS à la base en service sans l'écraser exprès."""
    verifier_sauvegarde(fichier)
    if vers_base == connection.settings_dict["NAME"]:
        raise SauvegardeError("Refus : la restauration vers la base en service écraserait les données courantes. Choisissez une autre base.")
    p = _parametres("postgres")
    try:
        with psycopg.connect(**p, autocommit=True) as maintenance:
            existe = maintenance.execute("SELECT 1 FROM pg_database WHERE datname = %s", [vers_base]).fetchone()
            if existe and not ecraser:
                raise SauvegardeError(f"La base « {vers_base} » existe déjà : utilisez --ecraser pour la remplacer.")
            if existe:
                maintenance.execute(f'DROP DATABASE "{vers_base}" WITH (FORCE)')
            maintenance.execute(f'CREATE DATABASE "{vers_base}"')
    except psycopg.Error as erreur:
        raise SauvegardeError(f"Impossible de préparer la base « {vers_base} » : {erreur}") from None
    cible = _parametres(vers_base)
    resultat = subprocess.run(
        [_outil("pg_restore"), "--no-owner", "--exit-on-error", "--host", cible["host"], "--port", cible["port"],
         "--username", cible["user"], "--dbname", vers_base, str(fichier)],
        env=_environnement(cible), capture_output=True, text=True,
    )
    if resultat.returncode != 0:
        raise SauvegardeError(f"pg_restore a échoué : {resultat.stderr.strip()}")
    if verifier:
        controle = verifier_integrite(vers_base)
        if controle.returncode != 0:
            raise SauvegardeError("La base restaurée est incohérente :\n" + (controle.stdout + controle.stderr).strip())


def verifier_integrite(base):
    """Lance ``verifier_audit`` SUR la base restaurée (processus à part, pointé vers cette base)."""
    return subprocess.run(
        [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), "verifier_audit"],
        env={**os.environ, "DB_NAME": base, "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.dev")},
        capture_output=True, text=True, cwd=str(settings.BASE_DIR),
    )
```

**Fichier `apps\commun\management\commands\sauvegarder.py`**

```python
"""Commande : sauvegarde la base PostgreSQL (§15.5) — à planifier toutes les 15 minutes pendant un concours."""
from django.core.management.base import BaseCommand, CommandError

from apps.audit.services import journaliser
from apps.commun import sauvegarde


class Command(BaseCommand):
    help = "Écrit une sauvegarde PostgreSQL horodatée (avec son empreinte SHA-256) puis fait tourner les anciennes."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", required=True, help="Dossier de sauvegarde (idéalement un disque externe).")
        parser.add_argument("--conserver", type=int, default=96, help="Nombre de sauvegardes conservées (défaut : 96, soit 24 h à 15 min).")

    def handle(self, *args, **options):
        try:
            fichier = sauvegarde.sauvegarder(options["dossier"], options["conserver"])
        except sauvegarde.SauvegardeError as erreur:
            raise CommandError(str(erreur)) from None  # code de sortie non nul : le planificateur voit l'échec
        journaliser("sauvegarde.effectuee", details={"fichier": fichier.name, "octets": fichier.stat().st_size})
        self.stdout.write(self.style.SUCCESS(f"Sauvegarde écrite : {fichier} ({fichier.stat().st_size} octets)."))
```

**Fichier `apps\commun\management\commands\restaurer.py`**

```python
"""Commande : restaure une sauvegarde dans une NOUVELLE base, puis vérifie sa cohérence (§15.5, REC-18)."""
from django.core.management.base import BaseCommand, CommandError

from apps.commun import sauvegarde


class Command(BaseCommand):
    help = "Restaure une sauvegarde dans une base (créée) et vérifie le journal d'audit restauré."

    def add_arguments(self, parser):
        parser.add_argument("fichier", help="Fichier .dump à restaurer.")
        parser.add_argument("--vers-base", required=True, help="Nom de la base à créer (jamais la base en service).")
        parser.add_argument("--ecraser", action="store_true", help="Remplace la base de destination si elle existe.")

    def handle(self, *args, **options):
        try:
            sauvegarde.restaurer(options["fichier"], options["vers_base"], ecraser=options["ecraser"])
        except sauvegarde.SauvegardeError as erreur:
            raise CommandError(str(erreur)) from None
        self.stdout.write(self.style.SUCCESS(
            f"Base « {options['vers_base']} » restaurée et vérifiée. Pour l'utiliser : DB_NAME={options['vers_base']} dans .env."
        ))
```

```powershell
pytest apps\commun\tests\test_sauvegarde.py
```

Ces tests exigent `pg_dump` et `pg_restore` (installés avec PostgreSQL). Sous Windows, ajoutez le dossier `bin` de PostgreSQL au `PATH` (par exemple `C:\Program Files\PostgreSQL\16\bin`) ou définissez la variable `PG_BIN`. Les tests sont **ignorés** si `pg_dump` est introuvable.

### Points d'attention de la sauvegarde

- Le fichier n'apparaît sous son vrai nom **qu'une fois complet et vérifié** (écriture dans un fichier temporaire, contrôle par `pg_restore --list`, puis renommage) : un disque débranché en cours d'écriture ne laisse pas une fausse sauvegarde.
- L'empreinte SHA-256 est vérifiée **avant** toute restauration : une sauvegarde altérée est refusée.
- On ne restaure **jamais** sur la base en service ; une base de destination existante n'est remplacée que sur demande (`--ecraser`).
- Après restauration, `verifier_audit` est lancé **sur la base restaurée** : si le journal d'audit est altéré, la restauration est déclarée incohérente (REC-18).

### Planifier toutes les 15 minutes (Windows, PowerShell)

Adaptez les chemins, puis, dans un PowerShell **administrateur** :

```powershell
$racine = "C:\QURANOVA"                       # le dossier du projet
$action = New-ScheduledTaskAction -Execute "$racine\.venv\Scripts\python.exe" `
    -Argument "manage.py sauvegarder --dossier E:\sauvegardes" -WorkingDirectory $racine
$declencheur = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "QURANOVA sauvegarde" -Action $action -Trigger $declencheur
```

> Je n'ai pas pu tester cette tâche planifiée sur Windows : essayez-la et vérifiez qu'un fichier `.dump` et son `.sha256` apparaissent toutes les 15 minutes. Une sauvegarde qui échoue renvoie un code de sortie non nul : l'historique de la tâche le montre.

### Essayer une restauration

```powershell
python manage.py sauvegarder --dossier E:\sauvegardes
python manage.py restaurer E:\sauvegardes\quranova-AAAAMMJJ-HHMMSS.dump --vers-base quranova_restaure
```

Attendu : « Base quranova_restaure restaurée et vérifiée ». Pour reprendre le concours sur cette base, mettez `DB_NAME=quranova_restaure` dans `.env`.

## Questions de compréhension

1. Pourquoi l'empreinte est-elle vérifiée **avant** la restauration ?
2. Pourquoi lancer `verifier_audit` dans un processus à part, pointé sur la base restaurée ?
3. Pourquoi l'export neutralise-t-il les cellules commençant par `=` ?

<details>
<summary>Réponses</summary>

1. Pour ne pas créer une base à partir d'un fichier tronqué ou altéré, et ne découvrir le problème qu'en plein incident.
2. L'application est configurée pour une seule base ; un processus séparé avec `DB_NAME` différent lit la base restaurée comme le ferait le serveur de remplacement, sans toucher à la base en service.
3. Un tableur interprète `=…` comme une formule : un nom importé qui vaudrait `=HYPERLINK(...)` s'exécuterait à l'ouverture du fichier. L'apostrophe force le texte.
</details>

## Journal d'apprentissage

Faites une vraie restauration sur votre poste et notez le temps qu'elle prend avec votre base de démonstration.

## Commit proposé

```text
Itération 4g-4h : procès-verbal, export CSV, sauvegarde et restauration
```
