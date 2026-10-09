"""Règles sur les jurés : affectation aux épreuves et codes d'accès de session (§7.4, §6.3).

Codes d'accès : 8 caractères tirés avec le module ``secrets`` dans un alphabet sans caractères
ambigus (ni 0, O, 1, I) ; affichés en deux groupes de 4 (« K7MQ-4XTR »). Seule l'empreinte
HMAC-SHA256 (clé : ``SECRET_KEY``) est stockée : un code court n'est pas assez robuste pour un
hachage lent, mais l'empreinte à clé rend la base inutilisable sans la clé, et permet de retrouver
directement l'enregistrement. Le nombre d'essais devra être limité par les vues (anti force brute).
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.concours.models import Epreuve
from apps.jury.exceptions import AffectationInvalideError, CodeInvalideError
from apps.jury.models import AffectationJury, CodeAccesJure

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 caractères, sans 0, O, 1, I
LONGUEUR_CODE = 8
DUREE_PAR_DEFAUT = timedelta(hours=12)


# --- Affectation (D5) ---------------------------------------------------------


def affecter(jure, *, concours=None, categorie=None, epreuve=None):
    """Affecte un juré à une épreuve, à toutes celles d'une catégorie, ou à tout un concours.

    Exactement une portée doit être donnée. Idempotent : les affectations déjà présentes sont
    conservées, seules les manquantes sont créées (et renvoyées).
    """
    portees = [p for p in (concours, categorie, epreuve) if p is not None]
    if len(portees) != 1:
        raise AffectationInvalideError(
            "Indiquez exactement une portée : un concours, une catégorie ou une épreuve."
        )
    if not jure.actif:
        raise AffectationInvalideError(f"Le juré {jure} est inactif : affectation impossible.")
    portee = portees[0]
    if portee.organisation_id != jure.organisation_id:
        raise AffectationInvalideError(
            "Le juré et l'épreuve appartiennent à deux clients différents (RM-20)."
        )

    if epreuve is not None:
        epreuves = [epreuve]
    elif categorie is not None:
        epreuves = list(categorie.epreuves.all())
    else:
        epreuves = list(Epreuve.objects.filter(categorie__concours=concours))

    deja = set(jure.affectations.values_list("epreuve_id", flat=True))
    creees = []
    for une_epreuve in epreuves:
        if une_epreuve.pk not in deja:
            creees.append(AffectationJury.objects.create(jure=jure, epreuve=une_epreuve))
    return creees


# --- Codes d'accès (D4) -------------------------------------------------------


def normaliser_code(saisie):
    """Majuscules, sans espace ni tiret : la saisie sur tablette est tolérante."""
    return "".join(c for c in saisie.upper() if c.isalnum())


def empreinte_du_code(code):
    """HMAC-SHA256 du code normalisé, avec la clé secrète du projet."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), normaliser_code(code).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _formater(brut):
    return f"{brut[:4]}-{brut[4:]}"


def generer_code(jure, session, maintenant=None, duree=DUREE_PAR_DEFAUT):
    """Génère un code pour un juré et une session ; révoque l'ancien code actif.

    Renvoie ``(acces, code_en_clair)``. Le code en clair n'est montré qu'ici, une seule fois
    (il sera imprimé sur la fiche du juré) : il n'est stocké nulle part.
    """
    if not jure.actif:
        raise AffectationInvalideError(f"Le juré {jure} est inactif : aucun code ne peut lui être remis.")
    if jure.organisation_id != session.organisation_id:
        raise AffectationInvalideError(
            "Le juré et la session appartiennent à deux clients différents (RM-20)."
        )
    maintenant = maintenant or timezone.now()
    with transaction.atomic():
        CodeAccesJure.objects.filter(jure=jure, session=session, revoque_le__isnull=True).update(
            revoque_le=maintenant
        )
        for _ in range(10):  # en cas de collision d'empreinte (très improbable), on retire un code
            brut = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR_CODE))
            try:
                with transaction.atomic():
                    acces = CodeAccesJure.objects.create(
                        jure=jure,
                        session=session,
                        empreinte=empreinte_du_code(brut),
                        valide_du=maintenant,
                        valide_jusqu_au=maintenant + duree,
                    )
            except IntegrityError:
                continue
            return acces, _formater(brut)
    raise RuntimeError("Impossible de générer un code unique.")  # pragma: no cover


def revoquer_code(acces, maintenant=None):
    """Révoque un code : il ne permet plus de se connecter (l'enregistrement reste, pour l'audit)."""
    acces.revoque_le = maintenant or timezone.now()
    acces.save(update_fields=["revoque_le", "modifie_le"])


def authentifier_par_code(saisie, session, maintenant=None):
    """Identifie le juré qui se connecte avec un code, pour une session donnée.

    Lève ``CodeInvalideError`` (message vague, ``raison`` précise pour le journal) si le code est
    inconnu, d'une autre session, révoqué, pas encore valide, expiré, ou si le juré est inactif.
    """
    maintenant = maintenant or timezone.now()
    acces = (
        CodeAccesJure.objects.select_related("jure")
        .filter(empreinte=empreinte_du_code(saisie), session=session)
        .first()
    )
    if acces is None:
        raise CodeInvalideError("inconnu")
    if acces.revoque_le is not None:
        raise CodeInvalideError("revoque")
    if maintenant < acces.valide_du:
        raise CodeInvalideError("pas_encore_valide")
    if maintenant > acces.valide_jusqu_au:
        raise CodeInvalideError("expire")
    if not acces.jure.actif:
        raise CodeInvalideError("jure_inactif")
    acces.derniere_utilisation = maintenant
    acces.save(update_fields=["derniere_utilisation", "modifie_le"])
    return acces
