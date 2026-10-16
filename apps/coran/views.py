"""Remise du procès-verbal de validation du corpus (réservée à l'administrateur QURANOVA, §12.3)."""
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_GET

from apps.commun.admin import role_admin
from apps.coran import documents
from apps.coran.models import VersionCorpus
from apps.resultats import pdf
from apps.utilisateurs.models import Utilisateur


def _version_autorisee(request, version_id):
    if role_admin(request.user) != Utilisateur.Role.ADMINISTRATEUR:
        raise Http404  # le personnel et les clients n'apprennent même pas qu'une telle page existe
    return get_object_or_404(VersionCorpus, pk=version_id)


@require_GET
def proces_verbal(request, version_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    version = _version_autorisee(request, version_id)
    reponse = HttpResponse(documents.proces_verbal_corpus(version, request.user))
    reponse["Cache-Control"] = "no-store"
    return reponse


@require_GET
def proces_verbal_pdf(request, version_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    version = _version_autorisee(request, version_id)
    try:
        contenu = documents.proces_verbal_corpus_pdf(version, request.user)
    except pdf.PdfIndisponibleError as erreur:
        lien = reverse("coran:proces_verbal", args=[version.pk])
        return HttpResponse(
            f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>PDF indisponible</title></head><body><main>'
            f'<h1>PDF indisponible</h1><p>{escape(str(erreur))}</p><p><a href="{lien}">Ouvrir la version imprimable</a>.</p></main></body></html>',
            status=503,
        )
    reponse = HttpResponse(contenu, content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="pv-validation-corpus-{version.pk}.pdf"'
    reponse["Cache-Control"] = "no-store"
    return reponse
