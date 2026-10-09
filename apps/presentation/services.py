"""Commandes de présentation : versionnées, idempotentes, sérialisées (§9.3, §13.5, RM-30 ; REC-24).

Le serveur détient l'état. Une commande n'est appliquée que si elle porte la version courante ; une commande
déjà reçue (même identifiant) n'est jamais appliquée deux fois ; toutes les commandes d'une session passent
sous un verrou : deux « diapositive suivante » simultanées donnent UNE seule application.
"""
from dataclasses import dataclass

from django.db import transaction

from apps.audit.services import journaliser
from apps.prestations.models import Prestation, Tirage
from apps.presentation import diapositives
from apps.presentation.exceptions import PlanImpossibleError, TransitionInterditeError
from apps.presentation.models import CommandePresentation, EtatPresentation
from apps.presentation.transitions import ACTIONS, Position, appliquer_transition
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

ETATS_PRESTATION = {
    "demarrer": Prestation.Etat.EN_AFFICHAGE,
    "reprendre": Prestation.Etat.EN_AFFICHAGE,
    "pause": Prestation.Etat.EN_PAUSE,
    "terminer": Prestation.Etat.EN_NOTATION,
}
TYPES_AVEC_TEXTE = ("verset", "enonce")


@dataclass
class Resultat:
    """Ce que le serveur répond à une commande (protocole §3.2) : ``statut``, ``raison``, ``version``."""

    statut: str  # « appliquee », « deja_traitee » ou « rejetee »
    version: int
    raison: str = ""
    etat: EtatPresentation | None = None


def peut_commander(utilisateur, session):
    """Seul le personnel du prestataire affecté à la mission commande le diaporama (§6.2, REC-14, RM-20)."""
    if not getattr(utilisateur, "is_authenticated", False) or not utilisateur.is_active:
        return False
    if utilisateur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        return False
    return missions_accessibles(utilisateur).filter(pk=session.concours.mission_id).exists()


def peut_commander_en_ligne(utilisateur, session, session_http):
    """``peut_commander`` + deuxième facteur validé dans la session du WebSocket (§15.1, règle absolue n° 4 : chaque canal est contrôlé)."""
    from apps.utilisateurs.otp import session_verifiee

    return peut_commander(utilisateur, session) and session_verifiee(utilisateur, session_http)


def etat_actif(session):
    return EtatPresentation.objects.filter(session=session, active=True).first()


def _version_courante(session):
    actif = etat_actif(session)
    return actif.version if actif else 0


def _journaliser(session, id_commande, action, version_attendue, auteur, statut, raison="", version_apres=None, prestation=None):
    CommandePresentation.objects.create(
        id_commande=id_commande, session=session, prestation=prestation, action=action,
        version_attendue=version_attendue, version_apres=version_apres, statut=statut, raison=raison, auteur=auteur,
    )


def _deja_traitee(session, id_commande):
    """Réponse à une commande déjà reçue, ou ``None`` si elle est nouvelle (idempotence, RM-30)."""
    ancienne = CommandePresentation.objects.filter(id_commande=id_commande).first()
    if ancienne is None:
        return None
    if ancienne.session_id != session.pk:
        return Resultat("rejetee", _version_courante(session), "non_autorise")
    if ancienne.statut == CommandePresentation.Statut.APPLIQUEE:
        return Resultat("deja_traitee", ancienne.version_apres)
    return Resultat("rejetee", _version_courante(session), ancienne.raison)


def appliquer_commande(session, id_commande, action, version_attendue=None, *, auteur, prestation=None):
    """Applique une commande d'affichage et renvoie un ``Resultat``. Ne lève pas pour un refus métier."""
    if not peut_commander(auteur, session):
        return Resultat("rejetee", _version_courante(session), "non_autorise")
    deja = _deja_traitee(session, id_commande)
    if deja is not None:
        return deja

    with transaction.atomic():
        # Verrou de session : toutes les commandes d'une session sont sérialisées (§13.5, REC-24).
        type(session).objects.select_for_update().get(pk=session.pk)
        deja = _deja_traitee(session, id_commande)  # une commande identique a pu passer pendant l'attente
        if deja is not None:
            return deja

        def rejeter(raison):
            _journaliser(session, id_commande, action, version_attendue, auteur,
                         CommandePresentation.Statut.REJETEE, raison, prestation=prestation)
            return Resultat("rejetee", _version_courante(session), raison)

        if action == "preparer":
            return _preparer(session, id_commande, auteur, prestation, rejeter)
        if action not in ACTIONS:
            return rejeter("commande_inconnue")
        etat = etat_actif(session)
        if etat is None:
            return rejeter("transition_interdite")
        if version_attendue != etat.version:
            return rejeter("version_obsolete")
        try:
            position = appliquer_transition(Position(etat.phase, etat.index, etat.rejeu), len(etat.plan), action)
        except TransitionInterditeError:
            return rejeter("transition_interdite")

        etat.phase, etat.index, etat.rejeu = position.phase, position.index, position.rejeu
        etat.version += 1
        etat.save(update_fields=["phase", "index", "rejeu", "version", "modifie_le"])
        _synchroniser_prestation(etat, action)
        if action == "precedente":  # §15.2 : un retour en arrière est une opération sensible
            journaliser(
                "diaporama.precedente", organisation=session.organisation, auteur=auteur, objet=etat.prestation,
                details={"version": etat.version, "diapositive": etat.index},
            )
        _journaliser(session, id_commande, action, version_attendue, auteur,
                     CommandePresentation.Statut.APPLIQUEE, version_apres=etat.version, prestation=etat.prestation)
        return Resultat("appliquee", etat.version, etat=etat)


def _preparer(session, id_commande, auteur, prestation, rejeter):
    """« Préparer l'affichage » : la prestation devient la présentation active de la session (D39, D41)."""
    if prestation is None or prestation.session_id != session.pk:
        return rejeter("transition_interdite")
    actif = etat_actif(session)
    if actif is not None and actif.phase in (EtatPresentation.Phase.AFFICHAGE, EtatPresentation.Phase.PAUSE):
        return rejeter("transition_interdite")  # il faut terminer la présentation en cours
    prestation = Prestation.objects.select_for_update().get(pk=prestation.pk)
    if prestation.etat != Prestation.Etat.TIRE:
        return rejeter("transition_interdite")  # seule une prestation tirée se présente
    try:
        plan = diapositives.construire_plan(prestation)
    except PlanImpossibleError:
        return rejeter("transition_interdite")

    if actif is not None:
        actif.active = False
        actif.save(update_fields=["active", "modifie_le"])
    etat = EtatPresentation.objects.filter(prestation=prestation).first()
    if etat is None:
        etat = EtatPresentation(prestation=prestation, session=session, version=1)
    else:
        etat.version += 1
    etat.active, etat.phase, etat.index, etat.rejeu, etat.plan = True, EtatPresentation.Phase.PREPAREE, None, 0, plan
    etat.save()
    _journaliser(session, id_commande, "preparer", None, auteur,
                 CommandePresentation.Statut.APPLIQUEE, version_apres=etat.version, prestation=prestation)
    return Resultat("appliquee", etat.version, etat=etat)


def _synchroniser_prestation(etat, action):
    """Répercute la commande sur la prestation (§8.3) et sur le tirage dont une diapositive est affichée (RM-25)."""
    prestation = etat.prestation
    nouvel_etat = ETATS_PRESTATION.get(action)
    if nouvel_etat is not None and prestation.etat != nouvel_etat:
        prestation.etat = nouvel_etat
        prestation.save(update_fields=["etat", "modifie_le"])
    if etat.phase == EtatPresentation.Phase.AFFICHAGE and etat.index is not None:
        diapositive = etat.plan[etat.index]
        if diapositive["type"] in TYPES_AVEC_TEXTE:
            # Dès qu'un verset (ou un énoncé) d'une série est affiché, son tirage ne peut plus être réintégré.
            Tirage.objects.filter(prestation=prestation, serie_id=diapositive["serie_id"]).update(diapositive_affichee=True)
