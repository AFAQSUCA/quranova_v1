"""Terminaux de tirage : authentification par jeton, appel d'un candidat, état affiché (§8.5, §8.6, §15).

L'opérateur FIXE le candidat appelé ; la tablette ne reçoit ni ne choisit aucune identité. Ce que la
tablette affiche (D34) : le numéro et le prénom du candidat, jamais son nom de famille (l'écran est
vu de la salle, parfois pour des mineurs, §16), et jamais le texte d'un verset (RM-14).
"""
from django.db import transaction
from django.utils import timezone

from apps.commun.jetons import empreinte_du_jeton, fabriquer_jeton
from apps.prestations import services
from apps.prestations.exceptions import AppelInvalideError, PasDAppelError, TerminalInvalideError
from apps.prestations.models import Prestation, TerminalTirage, Tirage
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

CONTEXTE_JETON = "terminal-tirage"


def creer_terminal(session, nom):
    """Crée un terminal ; renvoie ``(terminal, jeton)``. Le jeton n'est montré qu'à cet instant (D31)."""
    jeton = fabriquer_jeton()
    terminal = TerminalTirage.objects.create(
        session=session, nom=nom, empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON)
    )
    return terminal, jeton


def revoquer_terminal(terminal):
    terminal.revoque_le = timezone.now()
    terminal.prestation_appelee = None
    terminal.save(update_fields=["revoque_le", "prestation_appelee", "modifie_le"])


def authentifier_terminal(jeton):
    """Le terminal correspondant au jeton, ou ``TerminalInvalideError`` (message volontairement vague)."""
    if not jeton:
        raise TerminalInvalideError("Terminal non reconnu.")
    terminal = TerminalTirage.objects.filter(
        empreinte=empreinte_du_jeton(jeton, CONTEXTE_JETON), revoque_le__isnull=True
    ).first()
    if terminal is None:
        raise TerminalInvalideError("Terminal non reconnu.")
    TerminalTirage.objects.filter(pk=terminal.pk).update(derniere_activite=timezone.now())
    terminal.refresh_from_db()
    return terminal


def appeler_prestation(terminal, prestation, operateur):
    """L'opérateur appelle un candidat sur le terminal (§8.5). Remplace l'appel précédent."""
    if operateur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        raise AppelInvalideError("Seul le personnel du prestataire peut appeler un candidat.")
    mission = prestation.epreuve.categorie.concours.mission
    if not missions_accessibles(operateur).filter(pk=mission.pk).exists():
        raise AppelInvalideError("Vous n'avez pas accès à la mission de cette prestation (RM-20).")
    with transaction.atomic():
        terminal = TerminalTirage.objects.select_for_update().get(pk=terminal.pk)
        if terminal.revoque_le is not None:
            raise AppelInvalideError("Ce terminal est révoqué.")
        if prestation.session_id != terminal.session_id:
            raise AppelInvalideError("Cette prestation n'appartient pas à la session du terminal.")
        if prestation.etat != Prestation.Etat.EN_ATTENTE:
            raise AppelInvalideError("Seule une prestation en attente peut être appelée au tirage.")
        terminal.prestation_appelee = prestation
        terminal.save(update_fields=["prestation_appelee", "modifie_le"])
    return terminal


def liberer_terminal(terminal):
    terminal.prestation_appelee = None
    terminal.save(update_fields=["prestation_appelee", "modifie_le"])


def etat_du_terminal(terminal):
    """Ce que la tablette a le droit de savoir (D34) : jamais de nom de famille, jamais de verset."""
    terminal.refresh_from_db()
    prestation = terminal.prestation_appelee
    if prestation is None:
        return {"terminal": terminal.nom, "appel": None}
    prestation = Prestation.objects.select_related("participation__candidat", "epreuve").get(pk=prestation.pk)
    tirages = list(prestation.tirages.filter(statut=Tirage.Statut.VALIDE).select_related("serie").order_by("rang"))
    prevus = prestation.epreuve.tirages_par_candidat
    return {
        "terminal": terminal.nom,
        "appel": {
            "numero_candidat": prestation.participation.numero_candidat,
            "prenom": prestation.participation.candidat.prenom,
            "epreuve": prestation.epreuve.nom,
            "etat": prestation.etat,
            "tirages_prevus": prevus,
            "tirages": [{"rang": t.rang, "serie": t.serie.libelle} for t in tirages],
            "peut_tirer": prestation.etat == Prestation.Etat.EN_ATTENTE and len(tirages) < prevus,
        },
    }


def tirer_pour_terminal(terminal, id_demande):
    """Déclenche le tirage du candidat appelé. Le client n'indique JAMAIS la prestation (REC-25)."""
    terminal.refresh_from_db()
    if terminal.revoque_le is not None or terminal.prestation_appelee_id is None:
        raise PasDAppelError("Aucun candidat n'est appelé sur ce terminal : demandez à l'opérateur de vous appeler.")
    return services.effectuer_tirage(terminal.prestation_appelee, id_demande, terminal=terminal.nom)
