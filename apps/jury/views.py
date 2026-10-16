"""Page de la tablette du juré : publique et vide ; les données passent par l'API, protégée par le jeton."""
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_GET

from apps.clients.marque import marque_du_client
from apps.concours.models import Session
from apps.jury import fiches
from apps.presentation.services import peut_commander
from apps.resultats import pdf


@require_GET
def ecran_jury(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours__organisation"), pk=session_id)
    return render(request, "jury.html", {"session_id": session_id, "marque": marque_du_client(session.concours.organisation)})


# --- Fiches de notation de secours (§13.6) ---------------------------------------------------------------------------------


def _session_du_personnel(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours__mission"), pk=session_id)
    if not peut_commander(request.user, session):  # personnel du prestataire affecté à la mission (RM-20) ; sinon : introuvable
        raise Http404
    return session


@require_GET
def fiches_secours(request, session_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    reponse = HttpResponse(fiches.fiches_html(_session_du_personnel(request, session_id), request.user))
    reponse["Cache-Control"] = "no-store"
    return reponse


@require_GET
def fiches_secours_pdf(request, session_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    session = _session_du_personnel(request, session_id)
    try:
        contenu = fiches.fiches_pdf(session, request.user)
    except pdf.PdfIndisponibleError as erreur:
        lien = reverse("jury:fiches_secours", args=[session.pk])
        return HttpResponse(
            f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>PDF indisponible</title></head><body><main><h1>PDF indisponible</h1>'
            f'<p>{escape(str(erreur))}</p><p><a href="{lien}">Ouvrir la version imprimable</a>.</p></main></body></html>', status=503)
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="fiches-secours-{session.pk}.pdf"'
    reponse["Cache-Control"] = "no-store"
    return reponse
