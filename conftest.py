"""Réglages communs à tous les tests (lus automatiquement par pytest)."""
import pytest


@pytest.fixture(autouse=True)
def hachage_rapide(settings):
    """Utilise un hachage de mot de passe rapide pendant les tests.

    Le hachage normal de Django est volontairement lent (protection contre le
    piratage), ce qui ralentirait chaque test qui crée un utilisateur. Ce réglage
    ne s'applique qu'aux tests, jamais au vrai serveur.
    """
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def dossier_media_temporaire(settings, tmp_path):
    """Les fichiers téléversés par les tests (logos, consentements) vont dans un dossier jetable :
    ni pollution du dossier ``media/`` du développeur, ni dépendance aux droits d'écriture (Docker)."""
    settings.MEDIA_ROOT = tmp_path / "media"
