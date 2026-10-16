"""Fiches de notation de secours (§13.6, panne simultanée des deux ordinateurs).

1. **La veille** : le personnel imprime, pour chaque prestation d'une session et chaque juré affecté, une fiche vierge (barème, référence unique).
2. **Pendant la panne** : les jurés notent sur papier, signent.
3. **Après** : l'opérateur saisit chaque fiche en indiquant un MOTIF. L'évaluation est créée « validée » et tracée comme saisie différée
   (qui, pourquoi, quelle fiche) ; elle suit ensuite les règles ordinaires : une note manquante n'est jamais un zéro (RM-16), le barème est contrôlé.
"""
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.audit.services import journaliser
from apps.candidats.services import est_mineur
from apps.jury import evaluations
from apps.jury.exceptions import EvaluationIncompleteError, EvaluationInterditeError, NoteInvalideError
from apps.jury.models import AffectationJury, Evaluation, Note
from apps.prestations.models import Prestation, Tirage
from apps.resultats import pdf
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

ETATS_SAISISSABLES = (Prestation.Etat.TIRE, Prestation.Etat.EN_AFFICHAGE, Prestation.Etat.EN_PAUSE, Prestation.Etat.EN_NOTATION)


def _reference(prestation, jure):
    return f"FS-{prestation.rang_passage:03d}-{jure.pk.hex[:4].upper()}"


def _fiches(session):
    """Les fiches à imprimer : (prestation, juré, référence), dans l'ordre de passage puis par nom de juré."""
    prestations = list(
        Prestation.objects.filter(session=session).exclude(etat=Prestation.Etat.ANNULEE)
        .select_related("participation__candidat", "epreuve__categorie").order_by("rang_passage")
    )
    jures = {}
    for affectation in AffectationJury.objects.filter(epreuve_id__in={p.epreuve_id for p in prestations}, jure__actif=True).select_related("jure").order_by("jure__nom", "jure__prenom"):
        jures.setdefault(affectation.epreuve_id, []).append(affectation.jure)
    return [(p, jure, _reference(p, jure)) for p in prestations for jure in jures.get(p.epreuve_id, [])]


def references(session):
    return [reference for _, _, reference in _fiches(session)]


def _candidat(prestation):
    """Numéro et prénom + initiale du nom : une fiche circule en salle, on n'y met pas le nom complet (D34)."""
    participation = prestation.participation
    return f"n° {participation.numero_candidat} — {participation.candidat.prenom} {participation.candidat.nom[:1]}."


def _contexte(session, auteur):
    fiches = []
    criteres = {}
    for prestation, jure, reference in _fiches(session):
        if prestation.epreuve_id not in criteres:
            criteres[prestation.epreuve_id] = list(prestation.epreuve.criteres.order_by("ordre"))
        fiches.append({"prestation": prestation, "jure": jure, "reference": reference, "candidat": _candidat(prestation), "criteres": criteres[prestation.epreuve_id]})
    return {"session": session, "concours": session.concours, "fiches": fiches, "genere_le": timezone.now(), "auteur": auteur}


def fiches_html(session, auteur=None):
    html = render_to_string("documents/fiches_secours.html", _contexte(session, auteur))
    journaliser("document.fiches_secours_generees", organisation=session.organisation, auteur=auteur, objet=session,
                details={"format": "html", "fiches": html.count('class="fiche"')})
    return html


def fiches_pdf(session, auteur=None):
    contenu = pdf.html_vers_pdf(render_to_string("documents/fiches_secours.html", _contexte(session, auteur)))
    journaliser("document.fiches_secours_generees", organisation=session.organisation, auteur=auteur, objet=session,
                details={"format": "pdf", "octets": len(contenu)})
    return contenu


# --- Saisie ultérieure ---------------------------------------------------------------------------------------------------------------


def _verifier_droit(operateur, prestation):
    mission = prestation.epreuve.categorie.concours.mission
    if not (operateur.is_active and operateur.role in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR)
            and missions_accessibles(operateur).filter(pk=mission.pk).exists()):
        raise EvaluationInterditeError("Vous n'avez pas le droit de saisir une fiche pour cette prestation : seul le personnel affecté à la mission le peut (RM-20).")


def saisir_fiche(operateur, jure, prestation, notes, motif, observation="", reference=""):
    """Saisit une fiche de secours : évaluation VALIDÉE, tracée comme saisie différée ; clôture la prestation si tous les jurés ont leur fiche.

    ``notes`` : {identifiant du critère : valeur}. TOUS les critères doivent être renseignés : une note absente de la fiche n'est jamais convertie en zéro
    (RM-16) ; il faut retourner voir le juré. Tout ou rien.
    """
    _verifier_droit(operateur, prestation)
    if not (motif or "").strip():
        raise EvaluationInterditeError("Le motif de la saisie différée est obligatoire : dites pourquoi la fiche papier a été utilisée.")
    evaluations._verifier_droit_de_noter(jure, prestation)
    criteres = evaluations._criteres_par_id(prestation)
    notes = {str(k): v for k, v in (notes or {}).items()}
    if any(identifiant not in criteres for identifiant in notes):
        raise NoteInvalideError("Ce critère n'appartient pas à l'épreuve de cette prestation.")
    manquants = [c.libelle for i, c in sorted(criteres.items(), key=lambda x: x[1].ordre) if notes.get(i) is None or str(notes.get(i)).strip() == ""]
    valeurs = {i: evaluations.lire_valeur(v, criteres[i]) for i, v in notes.items() if v is not None and str(v).strip() != ""}

    with transaction.atomic():
        prestation = Prestation.objects.select_for_update().select_related("epreuve__categorie").get(pk=prestation.pk)
        if Evaluation.objects.filter(jure=jure, prestation=prestation).exists():
            raise EvaluationInterditeError("Ce juré a déjà une évaluation pour cette prestation : elle ne se remplace pas par une fiche (utilisez une correction approuvée).")
        if prestation.etat not in ETATS_SAISISSABLES:
            raise EvaluationInterditeError(f"Cette prestation n'a pas de tirage valable à évaluer (état : {prestation.get_etat_display()}).")
        if manquants:
            raise EvaluationIncompleteError(manquants)  # RM-16, REC-12
        evaluation = Evaluation.objects.create(
            jure=jure, prestation=prestation, organisation_id=prestation.organisation_id, statut=Evaluation.Statut.VALIDEE, validee_le=timezone.now(),
            observation=observation or "", saisie_differee=True, motif_saisie_differee=motif.strip(), saisie_par=operateur, reference_fiche=(reference or "").strip()[:40],
            series_evaluees=[t.serie.libelle for t in prestation.tirages.filter(statut=Tirage.Statut.VALIDE).select_related("serie").order_by("rang")],
        )
        Note.objects.bulk_create([Note(evaluation=evaluation, critere=criteres[i], valeur=v, organisation_id=prestation.organisation_id) for i, v in valeurs.items()])
        journaliser(
            "evaluation.saisie_differee", organisation=prestation.organisation, auteur=operateur, objet=evaluation,
            details={"prestation": prestation.pk, "jure": jure.nom_complet, "motif": evaluation.motif_saisie_differee, "reference": evaluation.reference_fiche},
        )
        if all(statut == Evaluation.Statut.VALIDEE for _, statut in evaluations.statut_notation(prestation)):
            prestation.etat = Prestation.Etat.CLOTUREE
            prestation.save(update_fields=["etat", "modifie_le"])
            journaliser("prestation.cloturee", organisation=prestation.organisation, auteur=operateur, objet=prestation, details={"saisie_differee": True})
    return evaluation
