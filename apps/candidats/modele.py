"""Modèle de fichier d'import des candidats, à remettre au client (livrable L-05).

Les colonnes viennent de l'importeur lui-même (``OBLIGATOIRES`` + ``FACULTATIVES``) : le modèle ne peut pas diverger de ce que l'importeur lit.
Les lignes d'exemple commencent par « EXEMPLE- » pour qu'on les reconnaisse (et les supprime) avant d'envoyer le fichier.
"""
import csv
import io

COLONNES = ("nom", "prenom", "date_naissance", "sexe", "ville", "structure", "categorie")


def _categories_d_exemple(concours):
    noms = [c.nom for c in concours.categories.order_by("nom")] if concours is not None else []
    if not noms:
        noms = ["Catégorie A", "Catégorie B"] if concours is None else ["Catégorie (à créer avant l'import)"]
    return noms


def contenu_modele(concours=None):
    """Le fichier CSV modèle (UTF-8 avec BOM, séparateur « ; », fins de ligne CRLF), avec deux lignes d'exemple.

    Avec ``concours``, les exemples utilisent ses VRAIES catégories : le fichier s'importe tel quel en simulation.
    """
    categories = _categories_d_exemple(concours)
    exemples = [
        ("EXEMPLE-Diallo", "Awa", "05/03/2012", "F", "Abidjan", "École coranique Al-Nour", categories[0]),
        ("EXEMPLE-Koné", "Ibrahim", "17/11/1998", "M", "Bouaké", "Mosquée centrale", categories[-1]),
    ]
    sortie = io.StringIO(newline="")
    ecrivain = csv.writer(sortie, delimiter=";", lineterminator="\r\n")
    ecrivain.writerow(COLONNES)
    ecrivain.writerows(exemples)
    return sortie.getvalue().encode("utf-8-sig")
