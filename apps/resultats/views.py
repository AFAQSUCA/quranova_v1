"""Remise des documents : procès-verbal (HTML prêt à imprimer) et export CSV (§11, §17.1).

Accès : le personnel du prestataire affecté à la mission, ou le responsable du client concerné. Sinon « introuvable »,
sans rien révéler (REC-25, REC-29).
"""
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.html import escape
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.concours.models import Concours
from apps.resultats import documents, pdf
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


def _reponse_pdf(request, concours_id, fabriquer, nom_fichier):
    """Sert un PDF en téléchargement ; si WeasyPrint manque, explique et renvoie vers la version imprimable (503)."""
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    concours = _concours_autorise(request, concours_id)
    try:
        contenu = fabriquer(concours, request.user)
    except pdf.PdfIndisponibleError as erreur:
        lien = reverse("resultats:proces_verbal", args=[concours.pk])
        return HttpResponse(
            f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>PDF indisponible</title></head><body><main>'
            f"<h1>PDF indisponible</h1><p>{escape(str(erreur))}</p>"
            f'<p><a href="{lien}">Ouvrir la version imprimable</a> puis « Imprimer → Enregistrer en PDF ».</p></main></body></html>',
            status=503,
        )
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="{nom_fichier}-{concours.pk}.pdf"'
    reponse["Cache-Control"] = "no-store"
    return reponse


@require_GET
def proces_verbal_pdf(request, concours_id):
    return _reponse_pdf(request, concours_id, lambda c, u: documents.proces_verbal_pdf(c, u), "proces-verbal")


@require_GET
def classements_pdf(request, concours_id):
    return _reponse_pdf(request, concours_id, lambda c, u: documents.classements_pdf(c, u), "classements")
