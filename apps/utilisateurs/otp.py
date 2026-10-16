"""Deuxième facteur TOTP (§15.1) : qui y est soumis, comment une session est « vérifiée », comment on enrôle et on réinitialise.

TOTP = code à 6 chiffres qui change toutes les 30 s, calculé par une application d'authentification (FreeOTP, Google Authenticator…) à partir d'une clé
partagée. Il fonctionne SANS Internet, ce qui compte pour un serveur de salle. La bibliothèque django-otp apporte l'anti-rejeu (un code ne sert qu'une
fois) et le ralentissement des essais ; ce module y ajoute la règle « qui doit en avoir un » et la vérification pour le WebSocket.
"""
from base64 import b32encode
from io import BytesIO

from django.conf import settings
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.models import Device
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.audit.services import journaliser
from apps.utilisateurs.models import Utilisateur

ROLES_SOUMIS = (Utilisateur.Role.ADMINISTRATEUR, Utilisateur.Role.OPERATEUR)
NOM_APPAREIL = "Application d'authentification"


def exige_2fa(utilisateur):
    """Vrai si ``utilisateur`` doit passer le deuxième facteur : administrateur ou opérateur actif, réglage ``EXIGER_2FA`` vrai."""
    return bool(
        getattr(settings, "EXIGER_2FA", True)
        and getattr(utilisateur, "is_authenticated", False)
        and utilisateur.is_active
        and utilisateur.role in ROLES_SOUMIS
    )


def appareil_confirme(utilisateur):
    return TOTPDevice.objects.filter(user=utilisateur, confirmed=True).order_by("id").first()


def appareil_en_attente(utilisateur):
    """L'appareil en cours d'enrôlement (créé au premier affichage, gardé tel quel tant qu'il n'est pas confirmé)."""
    appareil = TOTPDevice.objects.filter(user=utilisateur, confirmed=False).order_by("id").first()
    return appareil or TOTPDevice.objects.create(user=utilisateur, name=NOM_APPAREIL, confirmed=False)


def session_verifiee(utilisateur, session_http):
    """La session (HTTP ou WebSocket) a-t-elle franchi le deuxième facteur ? Vrai d'office si l'utilisateur n'y est pas soumis."""
    if not exige_2fa(utilisateur):
        return True
    identifiant = session_http.get(DEVICE_ID_SESSION_KEY) if session_http is not None else None
    if not identifiant:
        return False
    appareil = Device.from_persistent_id(identifiant, for_verify=False)
    return appareil is not None and appareil.user_id == utilisateur.pk and appareil.confirmed


def cle_de_saisie(appareil):
    """La clé en base 32, par groupes de 4, pour la saisir à la main dans l'application d'authentification."""
    brute = b32encode(appareil.bin_key).decode().rstrip("=")
    return " ".join(brute[i:i + 4] for i in range(0, len(brute), 4))


def qr_svg(appareil):
    """Le QR code de l'appareil, en SVG (sans Pillow ni fichier), à insérer tel quel dans la page."""
    import qrcode
    import qrcode.image.svg

    image = qrcode.make(appareil.config_url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    sortie = BytesIO()
    image.save(sortie)
    return sortie.getvalue().decode("utf-8")


def reinitialiser(cible, par):
    """Supprime les appareils de ``cible`` : il s'enrôlera de nouveau à sa prochaine connexion (téléphone perdu). Journalisé."""
    nombre, _ = TOTPDevice.objects.filter(user=cible).delete()
    journaliser(
        "2fa.reinitialisee", organisation=cible.organisation, auteur=par, objet=cible,
        details={"compte": cible.username, "appareils_supprimes": nombre},
    )
    return nombre
