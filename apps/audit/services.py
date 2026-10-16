"""Écriture et vérification du journal d'audit (§15.2).

``journaliser`` doit être appelé DANS la transaction de l'opération qu'il trace : si l'opération est annulée,
son entrée l'est aussi ; si elle réussit, l'entrée existe. Le verrou sur la tête de chaîne sérialise les ajouts :
la chaîne n'a jamais de fourche.
"""
import hashlib
import json
from datetime import timezone as fuseau_utc

from django.db import transaction
from django.utils import timezone

from apps.audit.models import ChaineAudit, EntreeAudit


def _normaliser(details):
    """Ce qui sera stocké ET haché : uniquement des types JSON (un UUID devient une chaîne)."""
    return json.loads(json.dumps(details or {}, default=str, ensure_ascii=False))


def calculer_empreinte(*, numero, horodatage, auteur_id, auteur_libelle, action, objet_type, objet_id,
                       terminal, details, empreinte_precedente, organisation_id):
    contenu = {
        "numero": numero,
        "horodatage": horodatage.astimezone(fuseau_utc.utc).isoformat(),
        "organisation": str(organisation_id) if organisation_id else "",
        "auteur": str(auteur_id) if auteur_id else "",
        "auteur_libelle": auteur_libelle,
        "action": action,
        "objet_type": objet_type,
        "objet_id": objet_id,
        "terminal": terminal,
        "details": details,
        "precedente": empreinte_precedente,
    }
    texte = json.dumps(contenu, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _chaine_verrouillee(organisation):
    """La tête de chaîne, créée au premier ajout, puis verrouillée jusqu'à la fin de la transaction."""
    organisation_id = organisation.pk if organisation is not None else None
    ChaineAudit.objects.get_or_create(organisation_id=organisation_id)
    return ChaineAudit.objects.select_for_update().get(organisation_id=organisation_id)


def journaliser(action, *, organisation=None, auteur=None, auteur_libelle="", objet=None, terminal="",
                details=None, maintenant=None):
    """Ajoute une entrée à la chaîne du client (ou à la chaîne « système » sans organisation)."""
    if auteur is not None and not getattr(auteur, "is_authenticated", False):
        auteur = None  # un utilisateur anonyme n'est pas un auteur
    details = _normaliser(details)
    objet_type = type(objet).__name__ if objet is not None else ""
    objet_id = str(objet.pk) if objet is not None else ""
    with transaction.atomic():
        chaine = _chaine_verrouillee(organisation)
        numero = chaine.dernier_numero + 1
        horodatage = maintenant or timezone.now()
        champs = dict(
            numero=numero, horodatage=horodatage, auteur_id=auteur.pk if auteur else None,
            auteur_libelle=auteur_libelle, action=action, objet_type=objet_type, objet_id=objet_id,
            terminal=terminal, details=details, empreinte_precedente=chaine.derniere_empreinte,
            organisation_id=organisation.pk if organisation is not None else None,
        )
        empreinte = calculer_empreinte(**champs)
        entree = EntreeAudit.objects.create(chaine=chaine, empreinte=empreinte, **champs)
        chaine.dernier_numero, chaine.derniere_empreinte = numero, empreinte
        chaine.save(update_fields=["dernier_numero", "derniere_empreinte"])
    return entree


def verifier_chaine(organisation=None):
    """Contrôle toute une chaîne ; renvoie la liste des problèmes (vide si elle est intacte).

    Détecte une entrée modifiée (empreinte recalculée différente), une entrée supprimée (trou dans les numéros
    ou dans le chaînage), un chaînage altéré, et une suppression en fin de chaîne (la tête ne correspond plus).
    """
    organisation_id = organisation.pk if organisation is not None else None
    chaine = ChaineAudit.objects.filter(organisation_id=organisation_id).first()
    if chaine is None:
        return []
    problemes = []
    attendu_numero, attendue_precedente = 1, ""
    derniere = None
    for entree in EntreeAudit.objects.filter(chaine=chaine).order_by("numero"):
        if entree.numero != attendu_numero:
            problemes.append(f"Entrée manquante avant le n° {entree.numero} (attendu : {attendu_numero}).")
            attendu_numero = entree.numero
        if entree.empreinte_precedente != attendue_precedente:
            problemes.append(f"Entrée n° {entree.numero} : le chaînage ne correspond pas à l'entrée précédente.")
        recalculee = calculer_empreinte(
            numero=entree.numero, horodatage=entree.horodatage, auteur_id=entree.auteur_id,
            auteur_libelle=entree.auteur_libelle, action=entree.action, objet_type=entree.objet_type,
            objet_id=entree.objet_id, terminal=entree.terminal, details=entree.details,
            empreinte_precedente=entree.empreinte_precedente, organisation_id=entree.organisation_id,
        )
        if recalculee != entree.empreinte:
            problemes.append(f"Entrée n° {entree.numero} : son contenu a été modifié.")
        attendu_numero += 1
        attendue_precedente = entree.empreinte
        derniere = entree
    dernier_numero = derniere.numero if derniere else 0
    dernier_empreinte = derniere.empreinte if derniere else ""
    if (chaine.dernier_numero, chaine.derniere_empreinte) != (dernier_numero, dernier_empreinte):
        problemes.append("La fin de la chaîne ne correspond pas à son registre : des entrées ont disparu.")
    return problemes
