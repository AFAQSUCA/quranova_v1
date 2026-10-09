"""Ferme l'accès du personnel tant que le deuxième facteur n'est pas validé (§15.1).

S'exécute après ``OTPMiddleware`` (qui sait si la session est vérifiée). Les pages de vérification, de connexion et de déconnexion restent
ouvertes ; une API répond 403 en JSON ; le reste est renvoyé vers la vérification, avec ``next`` pour revenir où l'on allait.
"""
from urllib.parse import quote

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.utilisateurs.otp import exige_2fa

PREFIXES_OUVERTS = ("/compte/", "/static/", "/media/")


class Exiger2FAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utilisateur = request.user
        if exige_2fa(utilisateur) and not getattr(utilisateur, "is_verified", lambda: False)() and not self._ouvert(request.path):
            if request.path.startswith("/api/"):
                return JsonResponse({"code": "2fa_requise", "message": "Deuxième facteur requis : connectez-vous à nouveau."}, status=403)
            return redirect(f"{reverse('utilisateurs:verification_2fa')}?next={quote(request.get_full_path())}")
        return self.get_response(request)

    @staticmethod
    def _ouvert(chemin):
        return chemin.startswith(PREFIXES_OUVERTS) or chemin in (reverse("admin:login"), reverse("admin:logout"))
