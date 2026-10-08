"""Marque visuelle d'un client (logo et couleurs) pour les écrans et les documents (§7.1 « personnalisation visuelle »).

Hiérarchie retenue : sur un écran vu du public, le CLIENT est mis en avant (son logo, sa couleur) et QURANOVA reste
discret (petit sceau en coin). Un client sans logo ni couleur garde simplement la charte QURANOVA.
"""
import re

from apps.clients.models import FORMAT_COULEUR

_COULEUR = re.compile(FORMAT_COULEUR)


def _couleur_valide(valeur):
    """La base refuse déjà un mauvais format ; on re-contrôle parce que la valeur finit dans un attribut ``style``."""
    return valeur if valeur and _COULEUR.match(valeur) else ""


def marque_du_client(organisation):
    """Renvoie ``{"nom", "logo_url", "couleur_principale", "couleur_secondaire"}`` (valeurs vides si non définies)."""
    logo = getattr(organisation, "logo", None)
    return {
        "nom": organisation.nom,
        "logo_url": logo.url if logo else "",
        "couleur_principale": _couleur_valide(organisation.couleur_principale),
        "couleur_secondaire": _couleur_valide(organisation.couleur_secondaire),
    }
