"""Page de vérification (et d'enrôlement) du deuxième facteur (§15.1)."""
import re

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django_otp import login as otp_login

from apps.audit.services import journaliser
from apps.utilisateurs import otp

JETON = re.compile(r"\d{6}")


def _suivant(request):
    cible = request.GET.get("next") or request.POST.get("next") or "/admin/"
    return cible if url_has_allowed_host_and_scheme(cible, allowed_hosts={request.get_host()}, require_https=request.is_secure()) else "/admin/"


@never_cache
@login_required(login_url="admin:login")
def verification_2fa(request):
    utilisateur, suivant = request.user, _suivant(request)
    if not otp.exige_2fa(utilisateur):
        return redirect(suivant)
    appareil = otp.appareil_confirme(utilisateur)
    enrolement = appareil is None
    if enrolement:
        appareil = otp.appareil_en_attente(utilisateur)
    erreur = ""
    if request.method == "POST":
        saisie = (request.POST.get("jeton") or "").replace(" ", "")
        autorise, _ = appareil.verify_is_allowed()
        if not autorise:
            erreur = "Trop d'essais : veuillez patienter quelques secondes avant de réessayer."
        elif not JETON.fullmatch(saisie):
            erreur = "Le code comporte 6 chiffres."
        elif not appareil.verify_token(saisie):
            erreur = "Code incorrect ou déjà utilisé. Attendez le prochain code de l'application et réessayez."
        else:
            if enrolement:
                appareil.confirmed = True
                appareil.save(update_fields=["confirmed"])
                journaliser("2fa.activee", organisation=utilisateur.organisation, auteur=utilisateur, objet=utilisateur)
            otp_login(request, appareil)
            return redirect(suivant)
    contexte = {"suivant": suivant, "erreur": erreur, "enrolement": enrolement}
    if enrolement:
        # SVG fabriqué par qrcode à partir de l'adresse otpauth:// de l'appareil, jamais d'une saisie utilisateur : sûr à insérer tel quel.
        contexte.update(qr=mark_safe(otp.qr_svg(appareil)), cle=otp.cle_de_saisie(appareil))  # nosec B308 B703
    return render(request, "compte/verification_2fa.html", contexte, status=200)
