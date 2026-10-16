"""Conversion HTML → PDF avec WeasyPrint (§11, §17.1).

Une seule source de vérité : le PDF est fabriqué à partir du MÊME HTML que la version imprimable du navigateur.

Sécurité : WeasyPrint va chercher les images et feuilles de style citées par le HTML. On lui donne un « chercheur » qui ne sert QUE
les fichiers statiques et les fichiers téléversés (logos) de QURANOVA ; jamais le réseau (pas de requête sortante déclenchée par un
contenu), jamais un fichier arbitraire du serveur (``file:///etc/passwd``), jamais une sortie de dossier (``../``).
"""
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders

HOTE_FICTIF = "pdf.local"  # adresse de base des liens relatifs du HTML ; ne correspond à aucun serveur réel


class PdfIndisponibleError(Exception):
    """WeasyPrint ou ses bibliothèques système (Pango) manquent : le PDF ne peut pas être produit sur ce serveur."""


def _prefixe(url_reglage):
    return "/" + url_reglage.strip("/") + "/"


def _fichier_autorise(chemin):
    """Le fichier statique ou téléversé désigné par ``chemin`` (``/static/…`` ou ``/media/…``), sinon ``ValueError``."""
    chemin = unquote(chemin)
    if ".." in Path(chemin).parts:
        raise ValueError("Sortie de dossier refusée.")
    if chemin.startswith(_prefixe(settings.STATIC_URL)):
        relatif = chemin[len(_prefixe(settings.STATIC_URL)):]
        trouve = finders.find(relatif)
        if not trouve or isinstance(trouve, (list, tuple)):
            raise ValueError(f"Fichier statique introuvable : {relatif}")
        return Path(trouve)
    if chemin.startswith(_prefixe(settings.MEDIA_URL)):
        racine = Path(settings.MEDIA_ROOT).resolve()
        fichier = (racine / chemin[len(_prefixe(settings.MEDIA_URL)):]).resolve()
        if not fichier.is_relative_to(racine) or not fichier.is_file():
            raise ValueError("Fichier téléversé introuvable ou hors du dossier autorisé.")
        return fichier
    raise ValueError(f"Ressource refusée : {chemin}")


def chercher_ressource(url, *args, **kwargs):
    """Chercheur de ressources de WeasyPrint : uniquement ``/static/`` et ``/media/`` de ce serveur."""
    morceaux = urlsplit(url)
    if morceaux.scheme not in ("http", "https") or morceaux.netloc != HOTE_FICTIF:
        raise ValueError(f"Ressource externe refusée : {url}")
    fichier = _fichier_autorise(morceaux.path)
    return {"file_obj": open(fichier, "rb"), "mime_type": mimetypes.guess_type(fichier.name)[0] or "application/octet-stream"}


def _classe_chercheur():
    """La classe de chercheur de WeasyPrint ≥ 68 (importée tardivement : WeasyPrint peut être absent de la machine)."""
    from weasyprint.urls import URLFetcher, URLFetcherResponse

    class ChercheurQuranova(URLFetcher):
        def fetch(self, url, headers=None):
            ressource = chercher_ressource(url)
            return URLFetcherResponse(url, body=ressource["file_obj"], headers={"Content-Type": ressource["mime_type"]})

    return ChercheurQuranova


def html_vers_pdf(html):
    """Le contenu PDF (``bytes``) de ``html``."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as erreur:
        raise PdfIndisponibleError(
            "Le PDF est indisponible : WeasyPrint ou la bibliothèque Pango est introuvable sur ce serveur (voir DEMARRAGE.md). "
            f"La version imprimable (HTML) reste disponible. Détail : {erreur}"
        ) from erreur
    return HTML(string=html, base_url=f"http://{HOTE_FICTIF}/", url_fetcher=_classe_chercheur()()).write_pdf()
