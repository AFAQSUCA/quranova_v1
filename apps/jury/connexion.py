"""Connexion d'un juré : code court contre jeton long, avec limitation des essais (D4, D5, D46, §15).

Le code (8 caractères) est facile à saisir mais court : on limite donc les essais par adresse. Une fois le code
accepté, la tablette reçoit un jeton de 256 bits (stocké sous forme d'empreinte HMAC) valable aussi longtemps
que le code ; c'est lui, et non le code, qui accompagne les requêtes suivantes.
"""
from datetime import timedelta

from django.utils import timezone

from apps.audit.services import journaliser
from apps.commun.jetons import empreinte_du_jeton, fabriquer_jeton
from apps.jury import services
from apps.jury.exceptions import CodeInvalideError, JetonInvalideError, TropDEssaisError
from apps.jury.models import ConnexionJure, TentativeCode

CONTEXTE_JETON = "jure"
ESSAIS_MAXIMUM = 5
FENETRE = timedelta(minutes=5)


def _verifier_limite(session, adresse, maintenant):
    echecs = list(
        TentativeCode.objects.filter(adresse=adresse, reussie=False, cree_le__gte=maintenant - FENETRE).order_by("cree_le")
    )
    if len(echecs) >= ESSAIS_MAXIMUM:
        reste = int((echecs[-ESSAIS_MAXIMUM].cree_le + FENETRE - maintenant).total_seconds()) + 1
        raise TropDEssaisError(max(reste, 1))


def ouvrir_connexion(saisie, session, adresse="", maintenant=None):
    """Échange un code contre un jeton. Renvoie ``(connexion, jeton)`` ; le jeton n'est montré qu'ici."""
    maintenant = maintenant or timezone.now()
    _verifier_limite(session, adresse, maintenant)
    try:
        acces = services.authentifier_par_code(saisie, session, maintenant=maintenant)
    except CodeInvalideError as erreur:
        TentativeCode.objects.create(session=session, adresse=adresse, reussie=False)
        journaliser(
            "jury.connexion_echouee", organisation=session.organisation, terminal=adresse,
            auteur_libelle="code de juré", details={"raison": erreur.raison, "session": session.pk},
        )
        raise
    jeton = fabriquer_jeton()
    connexion = ConnexionJure.objects.create(
        acces=acces, empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON), valide_jusqu_au=acces.valide_jusqu_au,
        adresse=adresse, derniere_activite=maintenant,
    )
    TentativeCode.objects.create(session=session, adresse=adresse, reussie=True)
    journaliser(
        "jury.connexion", organisation=session.organisation, terminal=adresse,
        auteur_libelle=f"juré {acces.jure.nom_complet}", objet=connexion, details={"session": session.pk},
    )
    return connexion, jeton


def authentifier_jeton(jeton, session=None, maintenant=None):
    """La connexion correspondant au jeton, ou ``JetonInvalideError`` (message vague)."""
    maintenant = maintenant or timezone.now()
    if not jeton:
        raise JetonInvalideError("Connexion non reconnue.")
    connexion = (
        ConnexionJure.objects.select_related("acces__jure", "acces__session")
        .filter(empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON), revoque_le__isnull=True,
                valide_jusqu_au__gt=maintenant)
        .first()
    )
    if (
        connexion is None
        or connexion.acces.revoque_le is not None
        or not connexion.acces.jure.actif
        or (session is not None and connexion.acces.session_id != session.pk)
    ):
        raise JetonInvalideError("Connexion non reconnue.")
    ConnexionJure.objects.filter(pk=connexion.pk).update(derniere_activite=maintenant)
    return connexion


def revoquer_connexion(connexion, maintenant=None):
    connexion.revoque_le = maintenant or timezone.now()
    connexion.save(update_fields=["revoque_le", "modifie_le"])
