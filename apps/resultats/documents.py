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
