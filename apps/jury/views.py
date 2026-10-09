"""Page de la tablette du juré : publique et vide ; les données passent par l'API, protégée par le jeton."""
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.clients.marque import marque_du_client
from apps.concours.models import Session


@require_GET
def ecran_jury(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours__organisation"), pk=session_id)
    return render(request, "jury.html", {"session_id": session_id, "marque": marque_du_client(session.concours.organisation)})
