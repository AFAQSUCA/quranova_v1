"""Téléchargement du modèle d'import des candidats (livrable L-05)."""
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.audit.services import journaliser
from apps.candidats import modele
from apps.concours.models import Concours
from apps.utilisateurs.services import missions_accessibles


@require_GET
def modele_import(request, concours_id):
    """Le modèle CSV avec les vraies catégories du concours : personnel affecté ou responsable du client concerné ; sinon « introuvable » (RM-20)."""
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    concours = get_object_or_404(Concours.objects.select_related("mission"), pk=concours_id)
    if not missions_accessibles(request.user).filter(pk=concours.mission_id).exists():
        raise Http404
    journaliser("document.modele_import_telecharge", organisation=concours.organisation, auteur=request.user, objet=concours)
    reponse = HttpResponse(modele.contenu_modele(concours), content_type="text/csv; charset=utf-8")
    reponse["Content-Disposition"] = 'attachment; filename="modele-import-candidats.csv"'
    reponse["Cache-Control"] = "no-store"
    return reponse
