"""Évaluation d'une prestation par un juré : brouillon, validation, clôture, corrections (§10 ; RM-15, RM-16 ; REC-11, 12, 17).

Règles clés :
- chaque juré note SEPARÉMENT ; il ne note que les épreuves auxquelles il est affecté (RM-15, §6.3) ;
- la saisie est possible dès que l'affichage a commencé ; la VALIDATION n'est possible qu'après « Terminer la
  prestation » (§8.3) ;
- une note manquante n'est JAMAIS convertie en zéro : l'évaluation est « incomplète » et ne se valide pas (RM-16) ;
- une évaluation validée ne change que par une correction motivée, approuvée par le responsable client (REC-17).
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.jury.exceptions import (
    CorrectionInvalideError,
    EvaluationIncompleteError,
    EvaluationInterditeError,
    EvaluationValideeError,
    NoteInvalideError,
)
from apps.jury.models import AffectationJury, CorrectionNote, Evaluation, Note
from apps.prestations.models import Prestation, Tirage
from apps.utilisateurs.models import Utilisateur

ETATS_DE_SAISIE = (Prestation.Etat.EN_AFFICHAGE, Prestation.Etat.EN_PAUSE, Prestation.Etat.EN_NOTATION)
DEUX_DECIMALES = Decimal("0.01")


def _verifier_droit_de_noter(jure, prestation):
    if not jure.actif:
        raise EvaluationInterditeError("Ce juré est inactif.")
    if jure.organisation_id != prestation.organisation_id:
        raise EvaluationInterditeError("Ce juré et cette prestation appartiennent à deux clients différents (RM-20).")
    if not AffectationJury.objects.filter(jure=jure, epreuve_id=prestation.epreuve_id).exists():
        raise EvaluationInterditeError("Ce juré n'est pas affecté à l'épreuve de cette prestation.")


def _verifier_etat_de_saisie(prestation):
    if prestation.etat not in ETATS_DE_SAISIE:
        raise EvaluationInterditeError(
            "La notation n'est possible qu'à partir du début de l'affichage et jusqu'à la clôture de la prestation."
        )


def lire_valeur(brut, critere):
    """Convertit une saisie en ``Decimal`` dans le barème du critère ; refuse le reste (jamais d'arrondi caché)."""
    if isinstance(brut, bool):
        raise NoteInvalideError(f"« {critere.libelle} » : valeur invalide.")
    try:
        valeur = Decimal(str(brut).strip().replace(",", "."))
    except InvalidOperation:
        raise NoteInvalideError(f"« {critere.libelle} » : « {brut} » n'est pas un nombre.") from None
    if not valeur.is_finite():
        raise NoteInvalideError(f"« {critere.libelle} » : valeur invalide.")
    if valeur != valeur.quantize(DEUX_DECIMALES):
        raise NoteInvalideError(f"« {critere.libelle} » : au plus deux décimales.")
    if valeur < 0 or valeur > critere.maximum:
        raise NoteInvalideError(f"« {critere.libelle} » : la note doit être comprise entre 0 et {critere.maximum:g}.")
    return valeur.quantize(DEUX_DECIMALES)


def _criteres_par_id(prestation):
    return {str(c.pk): c for c in prestation.epreuve.criteres.all()}


def enregistrer_brouillon(jure, prestation, notes=None, observation=None):
    """Enregistre (ou met à jour) le brouillon du juré, côté serveur. ``notes`` : {identifiant du critère : valeur}.

    Une valeur ``None`` ou vide EFFACE la note (elle redevient « manquante », pas zéro). Les critères non cités
    ne changent pas.
    """
    _verifier_droit_de_noter(jure, prestation)
    _verifier_etat_de_saisie(prestation)
    criteres = _criteres_par_id(prestation)
    notes = {str(k): v for k, v in (notes or {}).items()}
    for identifiant in notes:
        if identifiant not in criteres:
            raise NoteInvalideError("Ce critère n'appartient pas à l'épreuve de cette prestation.")
    valeurs = {i: (None if v is None or str(v).strip() == "" else lire_valeur(v, criteres[i])) for i, v in notes.items()}

    with transaction.atomic():
        evaluation, _ = Evaluation.objects.select_for_update().get_or_create(
            jure=jure, prestation=prestation, defaults={"organisation_id": prestation.organisation_id}
        )
        if evaluation.statut == Evaluation.Statut.VALIDEE:
            raise EvaluationValideeError(
                "Cette évaluation est validée : elle ne se modifie que par une demande de correction approuvée."
            )
        for identifiant, valeur in valeurs.items():
            if valeur is None:
                Note.objects.filter(evaluation=evaluation, critere_id=identifiant).delete()
            else:
                Note.objects.update_or_create(
                    evaluation=evaluation, critere=criteres[identifiant],
                    defaults={"valeur": valeur, "organisation_id": prestation.organisation_id},
                )
        if observation is not None:
            evaluation.observation = observation
            evaluation.save(update_fields=["observation", "modifie_le"])
    return evaluation


def etat_evaluation(prestation, evaluation=None):
    """L'état d'une évaluation pour l'écran du juré : une valeur par critère (``None`` = manquante), ce qui manque."""
    notes = {n.critere_id: n.valeur for n in evaluation.notes.all()} if evaluation is not None else {}
    criteres = list(prestation.epreuve.criteres.order_by("ordre"))
    lignes = [
        {"critere": str(c.pk), "libelle": c.libelle, "maximum": c.maximum, "coefficient": c.coefficient,
         "valeur": notes.get(c.pk)}
        for c in criteres
    ]
    manquants = [ligne["libelle"] for ligne in lignes if ligne["valeur"] is None]
    return {
        "statut": evaluation.statut if evaluation is not None else "non_commencee",
        "observation": evaluation.observation if evaluation is not None else "",
        "criteres": lignes,
        "manquants": manquants,
        "complete": not manquants,
    }


def valider_evaluation(jure, prestation):
    """Le juré valide SA propre évaluation (§14.2) : complète, et après « Terminer la prestation » (§8.3)."""
    _verifier_droit_de_noter(jure, prestation)
    with transaction.atomic():
        evaluation = (
            Evaluation.objects.select_for_update().filter(jure=jure, prestation=prestation).first()
        )
        if evaluation is None:
            raise EvaluationIncompleteError(c.libelle for c in prestation.epreuve.criteres.order_by("ordre"))
        if evaluation.statut == Evaluation.Statut.VALIDEE:
            raise EvaluationValideeError("Cette évaluation est déjà validée.")
        prestation = Prestation.objects.get(pk=prestation.pk)
        if prestation.etat != Prestation.Etat.EN_NOTATION:
            raise EvaluationInterditeError(
                "La validation n'est possible qu'après « Terminer la prestation » (la prestation n'est pas en notation)."
            )
        manquants = etat_evaluation(prestation, evaluation)["manquants"]
        if manquants:
            raise EvaluationIncompleteError(manquants)  # RM-16, REC-12 : jamais converties en zéro
        evaluation.statut = Evaluation.Statut.VALIDEE
        evaluation.validee_le = timezone.now()
        evaluation.series_evaluees = [
            t.serie.libelle
            for t in prestation.tirages.filter(statut=Tirage.Statut.VALIDE).select_related("serie").order_by("rang")
        ]
        evaluation.save(update_fields=["statut", "validee_le", "series_evaluees", "modifie_le"])
        journaliser(
            "evaluation.validee", organisation=prestation.organisation, auteur_libelle=f"juré {jure.nom_complet}",
            objet=evaluation, details={"prestation": prestation.pk, "series": evaluation.series_evaluees},
        )
    return evaluation


def statut_notation(prestation):
    """Pour chaque juré affecté : « non_commencee », « brouillon » ou « validee » (suivi de l'opérateur)."""
    evaluations = {e.jure_id: e.statut for e in prestation.evaluations.all()}
    jures = [a.jure for a in AffectationJury.objects.filter(epreuve_id=prestation.epreuve_id, jure__actif=True)
             .select_related("jure").order_by("jure__nom", "jure__prenom")]
    return [(jure, evaluations.get(jure.pk, "non_commencee")) for jure in jures]


def cloturer_prestation(prestation, operateur):
    """L'opérateur clôture la prestation quand TOUTES les évaluations requises sont validées (§8.3 étape 6)."""
    if operateur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        raise EvaluationInterditeError("Seul le personnel du prestataire clôture une prestation.")
    with transaction.atomic():
        prestation = Prestation.objects.select_for_update().get(pk=prestation.pk)
        if prestation.etat != Prestation.Etat.EN_NOTATION:
            raise EvaluationInterditeError("Seule une prestation en notation peut être clôturée.")
        attendus = statut_notation(prestation)
        if not attendus:
            raise EvaluationInterditeError("Aucun juré n'est affecté à cette épreuve : rien ne peut être clôturé.")
        en_attente = [jure.nom_complet for jure, statut in attendus if statut != Evaluation.Statut.VALIDEE]
        if en_attente:
            raise EvaluationInterditeError("Évaluations non validées : " + ", ".join(en_attente) + ".")
        prestation.etat = Prestation.Etat.CLOTUREE
        prestation.save(update_fields=["etat", "modifie_le"])
        journaliser("prestation.cloturee", organisation=prestation.organisation, auteur=operateur, objet=prestation)
    return prestation


# --- Corrections d'une note validée (REC-17) ------------------------------------------------------


def demander_correction(jure, prestation, critere, nouvelle_valeur, motif):
    """Le juré demande, avec un motif, de corriger UNE note de son évaluation validée."""
    _verifier_droit_de_noter(jure, prestation)
    motif = (motif or "").strip()
    if not motif:
        raise CorrectionInvalideError("Un motif est obligatoire pour demander la correction d'une note validée.")
    with transaction.atomic():
        evaluation = Evaluation.objects.select_for_update().filter(jure=jure, prestation=prestation).first()
        if evaluation is None or evaluation.statut != Evaluation.Statut.VALIDEE:
            raise CorrectionInvalideError("Seule une évaluation validée se corrige : modifiez directement votre brouillon.")
        if str(critere.pk) not in _criteres_par_id(prestation):
            raise NoteInvalideError("Ce critère n'appartient pas à l'épreuve de cette prestation.")
        valeur = lire_valeur(nouvelle_valeur, critere)
        note = Note.objects.get(evaluation=evaluation, critere=critere)
        if valeur == note.valeur:
            raise CorrectionInvalideError("La nouvelle valeur est identique à la valeur actuelle.")
        if CorrectionNote.objects.filter(evaluation=evaluation, critere=critere, statut=CorrectionNote.Statut.DEMANDEE).exists():
            raise CorrectionInvalideError("Une correction est déjà en attente pour cette note.")
        correction = CorrectionNote.objects.create(
            evaluation=evaluation, critere=critere, ancienne_valeur=note.valeur, nouvelle_valeur=valeur,
            motif=motif, demandee_le=timezone.now(),
        )
        journaliser(
            "note.correction_demandee", organisation=prestation.organisation, auteur_libelle=f"juré {jure.nom_complet}",
            objet=correction, details={"critere": critere.libelle, "ancienne": note.valeur, "nouvelle": valeur, "motif": motif},
        )
    return correction


def traiter_correction(correction, utilisateur, approuver, commentaire=""):
    """Le responsable client du concerné approuve ou refuse (jamais l'opérateur, RM-18, §6.2)."""
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != correction.organisation_id
    ):
        raise CorrectionInvalideError("Seul le responsable du client concerné peut approuver ou refuser une correction.")
    with transaction.atomic():
        correction = CorrectionNote.objects.select_for_update().select_related("evaluation", "critere").get(pk=correction.pk)
        if correction.statut != CorrectionNote.Statut.DEMANDEE:
            raise CorrectionInvalideError("Cette correction a déjà été traitée.")
        correction.statut = CorrectionNote.Statut.APPROUVEE if approuver else CorrectionNote.Statut.REFUSEE
        correction.traitee_par, correction.traitee_le = utilisateur, timezone.now()
        correction.commentaire_decision = commentaire
        correction.save()
        if approuver:
            Note.objects.filter(evaluation=correction.evaluation, critere=correction.critere).update(
                valeur=correction.nouvelle_valeur
            )
        journaliser(
            "note.corrigee" if approuver else "note.correction_refusee", organisation=correction.organisation,
            auteur=utilisateur, objet=correction,
            details={"critere": correction.critere.libelle, "ancienne": correction.ancienne_valeur,
                     "nouvelle": correction.nouvelle_valeur, "motif": correction.motif, "commentaire": commentaire,
                     "evaluation": correction.evaluation_id},
        )
    return correction
