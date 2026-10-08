"""Pages des écrans de scène et de commande, et liste des prestations pour la commande (§9.3, §9.4).

La page de scène est publique et vide : ses données passent par le WebSocket, protégé par le jeton (D38). La page
de commande exige un opérateur connecté, affecté à la mission ; sinon elle répond « introuvable », sans rien révéler
d'une session d'un autre client (REC-25, REC-29).
"""
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.clients.marque import marque_du_client
from apps.concours.models import Session
from apps.prestations.models import Prestation
from apps.presentation.services import peut_commander


def _session_commandable(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours"), pk=session_id)
    if not peut_commander(request.user, session):
        raise Http404  # ni 403 ni détail : on ne confirme pas l'existence de la session
    return session


@require_GET
def ecran_scene(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours__organisation"), pk=session_id)
    return render(request, "scene.html", {"session_id": session_id, "marque": marque_du_client(session.concours.organisation)})


@require_GET
def ecran_commande(request, session_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    session = _session_commandable(request, session_id)
    return render(request, "commande.html", {
        "session_id": session.pk, "marque": marque_du_client(session.concours.organisation),
    })


@require_GET
def prestations_de_la_session(request, session_id):
    if not request.user.is_authenticated:
        return JsonResponse({"code": "non_authentifie"}, status=401)
    session = _session_commandable(request, session_id)
    prestations = (
        Prestation.objects.filter(session=session)
        .select_related("participation__candidat", "epreuve")
        .order_by("rang_passage")
    )
    reponse = JsonResponse(
        {
            "prestations": [
                {
                    "id": str(p.pk),
                    "rang": p.rang_passage,
                    "numero": p.participation.numero_candidat,
                    "prenom": p.participation.candidat.prenom,  # jamais de nom de famille dans un écran partagé (D34)
                    "epreuve": p.epreuve.nom,
                    "etat": p.etat,
                }
                for p in prestations
            ]
        }
    )
    reponse["Cache-Control"] = "no-store"
    return reponse
