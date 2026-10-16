"""Police du texte arabe réglée par concours (affichage seulement : le texte du verset n'est jamais modifié, règle n° 1).

Deux sources : une police de la LISTE FIXE (le nom CSS est une constante du code, jamais une saisie) ou un FICHIER téléversé
(.woff2, .woff, .ttf, .otf) servi par le serveur de salle — il fonctionne alors hors ligne sur toutes les tablettes.

Le CSS produit ici est inséré tel quel dans les pages de scène, de jury et de commande : tout ce qui y entre est donc
soit une constante, soit un nombre borné, soit une adresse vérifiée caractère par caractère.
"""
import re

from django.core.exceptions import ValidationError
from django.db import models

TAILLE_MIN, TAILLE_MAX, TAILLE_DEFAUT = 50, 200, 100
TAILLE_MAX_FICHIER = 3 * 1024 * 1024  # une police coranique complète pèse < 1 Mo ; 3 Mo laisse de la marge

# Pile de secours commune : si la police choisie manque sur un appareil, le texte reste lisible.
_SECOURS = '"Amiri Quran", "Scheherazade New", "Traditional Arabic", "Noto Naskh Arabic", "Segoe UI", serif'


class PoliceArabe(models.TextChoices):
    DEFAUT = "defaut", "Par défaut (Amiri Quran, sinon polices du système)"
    SCHEHERAZADE = "scheherazade", "Scheherazade New"
    NASKH = "naskh", "Noto Naskh Arabic"
    TRADITIONAL = "traditional", "Traditional Arabic (Windows)"
    UTHMANIC = "uthmanic", "KFGQPC Uthmanic Script HAFS (si installée)"
    PERSONNALISEE = "personnalisee", "Fichier de police téléversé"


# Nom CSS de chaque police de la liste : des CONSTANTES (jamais construites à partir d'une saisie).
_FAMILLES = {
    PoliceArabe.DEFAUT: _SECOURS,
    PoliceArabe.SCHEHERAZADE: f'"Scheherazade New", {_SECOURS}',
    PoliceArabe.NASKH: f'"Noto Naskh Arabic", {_SECOURS}',
    PoliceArabe.TRADITIONAL: f'"Traditional Arabic", {_SECOURS}',
    PoliceArabe.UTHMANIC: f'"KFGQPC Uthmanic Script HAFS", "KFGQPC HAFS Uthmanic Script", {_SECOURS}',
}

# Signatures (premiers octets) et format CSS associé : on ne se fie pas à l'extension seule.
_SIGNATURES = (
    (b"wOF2", ".woff2", "woff2"),
    (b"wOFF", ".woff", "woff"),
    (b"\x00\x01\x00\x00", ".ttf", "truetype"),
    (b"true", ".ttf", "truetype"),
    (b"OTTO", ".otf", "opentype"),
)
_ADRESSE_SURE = re.compile(r"^[A-Za-z0-9._/\-]+$")


def valider_fichier_police(fichier):
    """Refuse un fichier trop gros, d'extension inattendue ou dont le contenu n'est pas une police."""
    if fichier.size > TAILLE_MAX_FICHIER:
        raise ValidationError("La police ne doit pas dépasser 3 Mo.")
    nom = fichier.name.lower()
    debut = fichier.read(4)
    fichier.seek(0)
    for signature, extension, _format in _SIGNATURES:
        if debut.startswith(signature):
            if not nom.endswith(extension):
                raise ValidationError(f"L'extension du fichier ne correspond pas à son contenu (attendu : {extension}).")
            return
    raise ValidationError("Ce fichier n'est pas une police reconnue (formats acceptés : .woff2, .woff, .ttf, .otf).")


def _format_du_fichier(nom: str) -> str:
    for _signature, extension, format_css in _SIGNATURES:
        if nom.lower().endswith(extension):
            return format_css
    return "truetype"


def typographie(concours) -> dict:
    """Ce que les écrans doivent savoir : pile de polices, adresse du fichier éventuel, échelle (1,0 = 100 %)."""
    echelle = min(TAILLE_MAX, max(TAILLE_MIN, concours.taille_texte_arabe)) / 100
    police = concours.police_arabe
    url, format_css = "", ""
    if police == PoliceArabe.PERSONNALISEE and concours.police_arabe_fichier:
        candidate = concours.police_arabe_fichier.url
        if _ADRESSE_SURE.match(candidate):  # l'adresse finit dans une règle CSS : on ne l'accepte que très simple
            url, format_css = candidate, _format_du_fichier(concours.police_arabe_fichier.name)
    if url:
        famille = f'"QuranovaArabe", {_SECOURS}'
    else:
        famille = _FAMILLES.get(PoliceArabe(police) if police in PoliceArabe.values else PoliceArabe.DEFAUT, _SECOURS)
        if police == PoliceArabe.PERSONNALISEE:
            famille = _SECOURS  # fichier absent ou adresse refusée : repli sur la police par défaut
    return {"famille": famille, "url": url, "format": format_css, "echelle": echelle}


def css(concours) -> str:
    """Règles CSS à insérer dans une page : police du texte arabe et échelle de taille (variables lues par les écrans)."""
    t = typographie(concours)
    regles = []
    if t["url"]:
        regles.append(
            f'@font-face {{ font-family: "QuranovaArabe"; src: url("{t["url"]}") format("{t["format"]}"); font-display: swap; }}'
        )
    regles.append(f':root {{ --police-coran: {t["famille"]}; --echelle-coran: {t["echelle"]:.2f}; }}')
    return "\n".join(regles)


def familles_pour_apercu() -> dict:
    """Pile de polices de chaque choix, pour l'aperçu instantané de l'administration (constantes, jamais une saisie)."""
    familles = {str(choix): pile for choix, pile in _FAMILLES.items()}
    familles[str(PoliceArabe.PERSONNALISEE)] = f'"QuranovaArabe", {_SECOURS}'
    return familles
