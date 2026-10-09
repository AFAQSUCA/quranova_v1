"""Limitation des tentatives de connexion du personnel (§15.1).

- 5 échecs d'un même compte en 15 minutes verrouillent ce compte, même avec le bon mot de passe ;
- 20 échecs d'une même adresse en 15 minutes verrouillent cette adresse (quel que soit le compte) ;
- une connexion réussie remet à zéro le compteur du COMPTE (pas celui de l'adresse) ;
- le verrou expire seul (pas de compte bloqué à vie) ; il est journalisé UNE fois, à l'instant où il se déclenche.

Compromis assumé : verrouiller un compte permet à un attaquant de gêner son titulaire quelques minutes. C'est préférable à un mot de passe
devinable ; un administrateur peut toujours se connecter depuis une autre adresse avec un autre compte.
"""
from datetime import timedelta

from django.utils import timezone

from apps.audit.services import journaliser
from apps.utilisateurs.exceptions import TropDEssaisConnexionError
from apps.utilisateurs.models import TentativeConnexion

ESSAIS_PAR_COMPTE = 5
ESSAIS_PAR_ADRESSE = 20
FENETRE = timedelta(minutes=15)


def _identifiant(brut):
    return (brut or "").strip().lower()[:150]


def _attente(echecs, maximum, maintenant):
    """Secondes avant que le verrou ne tombe, ou ``None`` s'il n'y a pas de verrou."""
    if len(echecs) < maximum:
        return None
    return max(1, int((echecs[-maximum].cree_le + FENETRE - maintenant).total_seconds()) + 1)


def _echecs_du_compte(identifiant, maintenant):
    depuis = maintenant - FENETRE
    derniere_reussite = (
        TentativeConnexion.objects.filter(identifiant=identifiant, reussie=True, cree_le__gte=depuis)
        .order_by("-cree_le").values_list("cree_le", flat=True).first()
    )
    echecs = TentativeConnexion.objects.filter(identifiant=identifiant, reussie=False, cree_le__gte=depuis)
    if derniere_reussite is not None:
        echecs = echecs.filter(cree_le__gt=derniere_reussite)
    return list(echecs.order_by("cree_le"))


def verifier_limite(identifiant, adresse, maintenant=None):
    """Lève ``TropDEssaisConnexionError`` si le compte ou l'adresse est verrouillé."""
    maintenant = maintenant or timezone.now()
    identifiant = _identifiant(identifiant)
    attente_compte = _attente(_echecs_du_compte(identifiant, maintenant), ESSAIS_PAR_COMPTE, maintenant) if identifiant else None
    attente_adresse = None
    if adresse:
        echecs_adresse = list(
            TentativeConnexion.objects.filter(adresse=adresse, reussie=False, cree_le__gte=maintenant - FENETRE).order_by("cree_le")
        )
        attente_adresse = _attente(echecs_adresse, ESSAIS_PAR_ADRESSE, maintenant)
    attente = max(a for a in (attente_compte, attente_adresse, 0) if a is not None)
    if attente:
        raise TropDEssaisConnexionError(attente)


def noter(identifiant, adresse, reussie, maintenant=None):
    """Enregistre un essai ; journalise l'instant précis où un verrou se déclenche."""
    maintenant = maintenant or timezone.now()
    identifiant = _identifiant(identifiant)
    tentative = TentativeConnexion.objects.create(identifiant=identifiant, adresse=(adresse or "")[:64], reussie=reussie)
    if maintenant != tentative.cree_le:  # permet de dater un essai dans les tests
        TentativeConnexion.objects.filter(pk=tentative.pk).update(cree_le=maintenant)
    if not reussie:
        par_compte = len(_echecs_du_compte(identifiant, maintenant)) if identifiant else 0
        par_adresse = TentativeConnexion.objects.filter(adresse=adresse or "", reussie=False, cree_le__gte=maintenant - FENETRE).count() if adresse else 0
        if par_compte == ESSAIS_PAR_COMPTE or par_adresse == ESSAIS_PAR_ADRESSE:
            journaliser(
                "connexion.verrouillee", auteur_libelle=f"compte « {identifiant} »", terminal=adresse or "",
                details={"compte": identifiant, "echecs_compte": par_compte, "echecs_adresse": par_adresse},
            )
