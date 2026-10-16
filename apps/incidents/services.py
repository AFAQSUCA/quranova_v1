"""Déclaration et résolution des incidents (§13.6). Seul le personnel du prestataire affecté à la mission consigne (RM-20)."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.incidents.exceptions import IncidentInvalideError
from apps.incidents.models import Incident
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles

TOLERANCE_HORLOGE = timedelta(minutes=2)  # l'horloge d'une tablette peut avancer de quelques instants


def _verifier_droit(auteur, concours):
    autorise = auteur.is_active and auteur.role in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR) \
        and missions_accessibles(auteur).filter(pk=concours.mission_id).exists()
    if not autorise:
        raise IncidentInvalideError("Vous n'avez pas le droit de consigner un incident pour ce concours : seul le personnel affecté à la mission le peut (RM-20).")


def enregistrer_declaration(incident, auteur):
    """Contrôle puis enregistre une déclaration (``incident`` non encore enregistré) ; partagé par les services et l'administration."""
    concours = incident.concours
    _verifier_droit(auteur, concours)
    if not (incident.description or "").strip():
        raise IncidentInvalideError("La description de l'incident est obligatoire : dites factuellement ce qui s'est passé.")
    if incident.survenu_le is None:
        incident.survenu_le = timezone.now()
    if incident.survenu_le > timezone.now() + TOLERANCE_HORLOGE:
        raise IncidentInvalideError("L'heure de l'incident ne peut pas être dans le futur.")
    if incident.session_id and incident.session.concours_id != concours.pk:
        raise IncidentInvalideError("La session indiquée n'appartient pas à ce concours.")
    if incident.prestation_id and incident.prestation.epreuve.categorie.concours_id != concours.pk:
        raise IncidentInvalideError("La prestation indiquée n'appartient pas à ce concours.")
    incident.description = incident.description.strip()
    incident.declare_par = auteur
    with transaction.atomic():
        incident.save()
        journaliser(
            "incident.declare", organisation=incident.organisation, auteur=auteur, objet=incident,
            details={"type": incident.type, "gravite": incident.gravite, "concours": concours.pk},
        )
    return incident


def declarer(concours, auteur, *, type, description, gravite=Incident.Gravite.MINEURE, survenu_le=None, session=None, prestation=None):
    return enregistrer_declaration(
        Incident(concours=concours, type=type, description=description, gravite=gravite, survenu_le=survenu_le, session=session, prestation=prestation),
        auteur,
    )


def resoudre(incident, auteur, resolution, resolu_le=None):
    """Consigne ce qui a été fait ; l'incident est alors clos (une seule fois)."""
    _verifier_droit(auteur, incident.concours)
    if not (resolution or "").strip():
        raise IncidentInvalideError("Le texte de résolution est obligatoire : dites ce qui a été fait.")
    with transaction.atomic():
        incident = Incident.objects.select_for_update().get(pk=incident.pk)
        if incident.resolu_le is not None:
            raise IncidentInvalideError("Cet incident est déjà résolu.")
        resolu_le = resolu_le or timezone.now()
        if resolu_le < incident.survenu_le:
            raise IncidentInvalideError("La résolution ne peut pas être antérieure à l'incident : elle ne peut pas avoir lieu avant lui.")
        incident.resolu_le, incident.resolution = resolu_le, resolution.strip()
        incident.save(update_fields=["resolu_le", "resolution", "modifie_le"])
        journaliser(
            "incident.resolu", organisation=incident.organisation, auteur=auteur, objet=incident,
            details={"duree_secondes": int((resolu_le - incident.survenu_le).total_seconds())},
        )
    return incident


def bilan(concours):
    """Chiffres du bilan : total, bloquants, non résolus, répartition par type, durée cumulée des incidents résolus."""
    incidents = list(Incident.objects.filter(concours=concours))
    par_type = {}
    for incident in incidents:
        libelle = incident.get_type_display()
        par_type[libelle] = par_type.get(libelle, 0) + 1
    return {
        "total": len(incidents),
        "bloquants": sum(1 for i in incidents if i.gravite == Incident.Gravite.BLOQUANTE),
        "non_resolus": sum(1 for i in incidents if i.resolu_le is None),
        "par_type": par_type,
        "duree_cumulee": sum((i.duree for i in incidents if i.duree is not None), timedelta()),
    }
