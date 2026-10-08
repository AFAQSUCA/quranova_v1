"""API JSON de la tablette du juré (§10.2 ; RM-15, REC-14, REC-25).

Authentification : ``Authorization: Bearer <jeton>`` obtenu en échange du code de session. Aucun cookie, donc aucun
CSRF possible (vues exemptées pour cette raison précise). Le juré identifié par le jeton est le SEUL juré pour
lequel on lit ou on écrit : aucun identifiant de juré n'est jamais lu dans une requête (REC-25).
"""
import json
from decimal import Decimal
from functools import wraps

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.concours.models import CritereNotation, Session
from apps.jury import connexion, evaluations
from apps.jury.exceptions import (
    CodeInvalideError,
    CorrectionInvalideError,
    EvaluationIncompleteError,
    EvaluationInterditeError,
    EvaluationValideeError,
    JetonInvalideError,
    NoteInvalideError,
    TropDEssaisError,
)
from apps.jury.models import AffectationJury, CorrectionNote, Evaluation
from apps.prestations.models import Prestation
from apps.presentation.models import EtatPresentation

ETATS_VISIBLES = (
    Prestation.Etat.EN_AFFICHAGE, Prestation.Etat.EN_PAUSE, Prestation.Etat.EN_NOTATION, Prestation.Etat.CLOTUREE,
)


class _Json(JsonResponse):
    def __init__(self, donnees, statut=200):
        super().__init__(donnees, status=statut, json_dumps_params={"ensure_ascii": False}, encoder=_Encodeur)
        self["Cache-Control"] = "no-store"


class _Encodeur(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return format(o, "f")  # « 7.50 » : jamais de flottant binaire pour une note
        return super().default(o)


def _erreur(statut, code, message, **plus):
    return _Json({"code": code, "message": message, **plus}, statut)


def _corps(request):
    try:
        corps = json.loads(request.body or b"{}")
    except ValueError:
        return None
    return corps if isinstance(corps, dict) else None


def avec_jure(vue):
    """Authentifie le juré par son jeton, pour la session de l'URL ; sinon 401."""

    @wraps(vue)
    def enveloppe(request, session_id, *args, **kwargs):
        session = get_object_or_404(Session.objects.select_related("concours"), pk=session_id)
        en_tete = request.headers.get("Authorization", "")
        jeton = en_tete[7:].strip() if en_tete.startswith("Bearer ") else ""
        try:
            conn = connexion.authentifier_jeton(jeton, session)
        except JetonInvalideError:
            return _erreur(401, "connexion_inconnue", "Connexion non reconnue.")
        return vue(request, session, conn.acces.jure, *args, **kwargs)

    return enveloppe


def _prestation_du_jure(session, jure, prestation_id):
    """La prestation, seulement si elle est de cette session ET d'une épreuve du juré : sinon 404 (REC-25)."""
    prestation = (
        Prestation.objects.select_related("epreuve", "participation__candidat")
        .filter(pk=prestation_id, session=session).first()
    )
    if prestation is None or not AffectationJury.objects.filter(jure=jure, epreuve_id=prestation.epreuve_id).exists():
        raise Http404
    return prestation


@csrf_exempt
@require_http_methods(["POST"])
def ouvrir(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours"), pk=session_id)
    corps = _corps(request)
    if corps is None or not isinstance(corps.get("code"), str):
        return _erreur(400, "requete_invalide", "Requête invalide : un code est attendu.")
    adresse = request.META.get("REMOTE_ADDR", "")
    try:
        conn, jeton = connexion.ouvrir_connexion(corps["code"], session, adresse)
    except TropDEssaisError as erreur:
        return _erreur(429, "trop_d_essais", str(erreur), attente_secondes=erreur.attente_secondes)
    except CodeInvalideError as erreur:
        return _erreur(401, "code_invalide", str(erreur))  # message vague : la raison reste dans le journal
    jure = conn.acces.jure
    return _Json({"jeton": jeton, "jure": {"prenom": jure.prenom, "nom": jure.nom}, "valide_jusqu_au": conn.valide_jusqu_au.isoformat()})


@csrf_exempt
@require_http_methods(["GET"])
@avec_jure
def prestations(request, session, jure):
    affectees = AffectationJury.objects.filter(jure=jure).values_list("epreuve_id", flat=True)
    actif = EtatPresentation.objects.filter(session=session, active=True).values_list("prestation_id", flat=True).first()
    liste = (
        Prestation.objects.filter(session=session, epreuve_id__in=affectees, etat__in=ETATS_VISIBLES)
        .select_related("participation__candidat", "epreuve").order_by("rang_passage")
    )
    statuts = {e.prestation_id: e.statut for e in Evaluation.objects.filter(jure=jure, prestation__in=liste)}
    return _Json({"prestations": [
        {"id": str(p.pk), "rang": p.rang_passage, "numero": p.participation.numero_candidat,
         "prenom": p.participation.candidat.prenom, "epreuve": p.epreuve.nom, "etat": p.etat,
         "evaluation": statuts.get(p.pk, "non_commencee"), "active": p.pk == actif}
        for p in liste
    ]})


def _etat_complet(prestation, jure):
    evaluation = Evaluation.objects.filter(jure=jure, prestation=prestation).first()
    etat = evaluations.etat_evaluation(prestation, evaluation)
    etat["peut_saisir"] = evaluation is None or evaluation.statut == Evaluation.Statut.BROUILLON
    etat["peut_valider"] = (
        etat["peut_saisir"] and etat["complete"] and prestation.etat == Prestation.Etat.EN_NOTATION
    )
    etat["prestation"] = {
        "id": str(prestation.pk), "numero": prestation.participation.numero_candidat,
        "prenom": prestation.participation.candidat.prenom, "epreuve": prestation.epreuve.nom, "etat": prestation.etat,
    }
    etat["corrections"] = [
        {"critere": str(c.critere_id), "ancienne": c.ancienne_valeur, "nouvelle": c.nouvelle_valeur,
         "statut": c.statut, "motif": c.motif}
        for c in (evaluation.corrections.all() if evaluation else [])
    ]
    return etat


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@avec_jure
def evaluation(request, session, jure, prestation_id):
    prestation = _prestation_du_jure(session, jure, prestation_id)
    if request.method == "PUT":
        corps = _corps(request)
        if corps is None or not isinstance(corps.get("notes", {}), dict):
            return _erreur(400, "requete_invalide", "Requête invalide.")
        try:
            evaluations.enregistrer_brouillon(jure, prestation, corps.get("notes"), corps.get("observation"))
        except NoteInvalideError as erreur:
            return _erreur(400, "note_invalide", str(erreur))
        except EvaluationValideeError as erreur:
            return _erreur(409, "evaluation_validee", str(erreur))
        except EvaluationInterditeError as erreur:
            return _erreur(403, "interdit", str(erreur))
    return _Json(_etat_complet(prestation, jure))


@csrf_exempt
@require_http_methods(["POST"])
@avec_jure
def valider(request, session, jure, prestation_id):
    prestation = _prestation_du_jure(session, jure, prestation_id)
    try:
        evaluations.valider_evaluation(jure, prestation)
    except EvaluationIncompleteError as erreur:
        return _erreur(409, "evaluation_incomplete", str(erreur), manquants=erreur.manquants)
    except EvaluationValideeError as erreur:
        return _erreur(409, "evaluation_validee", str(erreur))
    except EvaluationInterditeError as erreur:
        return _erreur(409, "pas_encore", str(erreur))
    return _Json(_etat_complet(prestation, jure))


@csrf_exempt
@require_http_methods(["POST"])
@avec_jure
def correction(request, session, jure, prestation_id):
    prestation = _prestation_du_jure(session, jure, prestation_id)
    corps = _corps(request)
    if corps is None or not isinstance(corps.get("critere"), str):
        return _erreur(400, "requete_invalide", "Requête invalide.")
    critere = CritereNotation.objects.filter(pk=corps["critere"], epreuve=prestation.epreuve).first() if _uuid(corps["critere"]) else None
    if critere is None:
        return _erreur(400, "note_invalide", "Critère inconnu pour cette épreuve.")
    try:
        evaluations.demander_correction(jure, prestation, critere, corps.get("valeur"), corps.get("motif"))
    except (NoteInvalideError, CorrectionInvalideError) as erreur:
        return _erreur(400, "correction_refusee", str(erreur))
    return _Json(_etat_complet(prestation, jure), 201)


def _uuid(texte):
    import uuid

    try:
        uuid.UUID(texte)
        return True
    except ValueError:
        return False
