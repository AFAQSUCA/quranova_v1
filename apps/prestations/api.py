"""API JSON de l'écran de tirage (§8.5, §8.6, §15.4).

Authentification : en-tête ``Authorization: Bearer <jeton>`` (D31). Aucun cookie n'est utilisé, donc
aucun CSRF n'est possible (les vues sont exemptées pour cette raison précise). Le client n'envoie
qu'un ``id_demande`` : la prestation est celle que l'opérateur a appelée sur ce terminal, jamais une
valeur fournie par le client (REC-25).
"""
import json
import uuid
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.candidats.exceptions import ConsentementManquantError, ParticipationNonAdmiseError, TirageImpossibleError
from apps.prestations import terminaux
from apps.prestations.exceptions import LotEpuiseError, PasDAppelError, TerminalInvalideError


def _reponse(donnees, statut=200):
    reponse = JsonResponse(donnees, status=statut, json_dumps_params={"ensure_ascii": False})
    reponse["Cache-Control"] = "no-store"
    return reponse


def _erreur(statut, code, message):
    return _reponse({"code": code, "message": message}, statut)


def avec_terminal(vue):
    """Authentifie le terminal par son jeton ; sinon 401 sans rien divulguer."""

    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        en_tete = request.headers.get("Authorization", "")
        jeton = en_tete[7:].strip() if en_tete.startswith("Bearer ") else ""
        try:
            terminal = terminaux.authentifier_terminal(jeton)
        except TerminalInvalideError:
            return _erreur(401, "terminal_inconnu", "Terminal non reconnu.")
        return vue(request, terminal, *args, **kwargs)

    return enveloppe


@csrf_exempt  # pas de cookie : l'authentification est l'en-tête Authorization
@require_GET
@avec_terminal
def etat(request, terminal):
    return _reponse(terminaux.etat_du_terminal(terminal))


CODES_REFUS = (
    (PasDAppelError, "pas_d_appel"),
    (LotEpuiseError, "lot_epuise"),
    (ConsentementManquantError, "consentement_manquant"),
    (ParticipationNonAdmiseError, "non_admis"),
    (TirageImpossibleError, "refuse"),
)


@csrf_exempt
@require_POST
@avec_terminal
def tirer(request, terminal):
    try:
        id_demande = uuid.UUID(str(json.loads(request.body or b"{}")["id_demande"]))
    except (ValueError, KeyError, TypeError, AttributeError):
        return _erreur(400, "requete_invalide", "Requête invalide : un identifiant de demande est attendu.")
    try:
        tirage = terminaux.tirer_pour_terminal(terminal, id_demande)
    except TirageImpossibleError as refus:
        code = next(code for classe, code in CODES_REFUS if isinstance(refus, classe))
        return _erreur(409, code, str(refus))
    return _reponse(
        {"tirage": {"rang": tirage.rang, "serie": tirage.serie.libelle}, "etat": terminaux.etat_du_terminal(terminal)}
    )
