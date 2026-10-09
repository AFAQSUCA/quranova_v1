"""Validation du classement définitif par le responsable client (RM-18, REC-39 ; §11, §14.2).

Le prestataire EXÉCUTE, le client VALIDE : ni l'opérateur ni l'administrateur ne valident (§6.2). Aucun classement
n'est remis ou publié avant cette validation (``exiger_classement_valide``).
"""
import hashlib
import json

from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.resultats import services
from apps.resultats.exceptions import ClassementInvalideError
from apps.resultats.models import Classement, LigneDeClassement
from apps.utilisateurs.models import Utilisateur


def _verifier_responsable(utilisateur, epreuve):
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != epreuve.organisation_id
    ):
        raise ClassementInvalideError("Seul le responsable du client concerné peut valider ou corriger le classement définitif.")


def calculer_empreinte(lignes, regle_classement, regle_departage):
    contenu = {
        "regles": [regle_classement, regle_departage],
        "lignes": [
            [str(l["participation"].pk), l["rang"], l["ex_aequo"], None if l["score"] is None else str(l["score"]), l["complet"]]
            for l in sorted(lignes, key=lambda l: str(l["participation"].pk))
        ],
    }
    return hashlib.sha256(json.dumps(contenu, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def classement_definitif(epreuve):
    """La version en vigueur (la plus récente), ou ``None`` si rien n'a été validé."""
    return Classement.objects.filter(epreuve=epreuve).order_by("-version").first()


def historique(epreuve):
    return list(Classement.objects.filter(epreuve=epreuve).order_by("version"))


def exiger_classement_valide(epreuve):
    """Aucune remise ni publication sans validation (§14.2) : renvoie le classement en vigueur ou refuse."""
    classement = classement_definitif(epreuve)
    if classement is None:
        raise ClassementInvalideError(f"Le classement de l'épreuve « {epreuve.nom} » n'a pas été validé par le responsable client.")
    return classement


def _creer(epreuve, utilisateur, lignes, version, correction, motif):
    categorie = epreuve.categorie
    classement = Classement.objects.create(
        epreuve=epreuve, version=version, est_correction=correction, motif_correction=motif,
        valide_par=utilisateur, valide_le=timezone.now(),
        regle_classement=categorie.regle_classement, regle_departage=categorie.regle_departage,
        empreinte=calculer_empreinte(lignes, categorie.regle_classement, categorie.regle_departage),
    )
    for l in lignes:
        LigneDeClassement.objects.create(
            classement=classement, participation=l["participation"], rang=l["rang"], ex_aequo=l["ex_aequo"], score=l["score"],
            complet=l["complet"], evaluations_validees=l["evaluations_validees"], evaluations_attendues=l["evaluations_attendues"],
        )
    return classement


def valider_classement(epreuve, utilisateur, confirmer_egalites=False):
    """Fige le classement actuel de l'épreuve comme classement DÉFINITIF (version 1)."""
    _verifier_responsable(utilisateur, epreuve)
    with transaction.atomic():
        if classement_definitif(epreuve) is not None:
            raise ClassementInvalideError("Ce classement est déjà validé : une modification passe par une correction motivée.")
        lignes = services.classement_provisoire(epreuve)
        if not lignes:
            raise ClassementInvalideError("Aucun candidat en compétition : il n'y a rien à valider.")
        incompletes = [l for l in lignes if not l["complet"]]
        if incompletes:
            noms = ", ".join(f"n° {l['participation'].numero_candidat}" for l in incompletes)
            raise ClassementInvalideError(f"Notation incomplète pour : {noms}. Le classement ne peut pas être validé.")
        if any(l["ex_aequo"] for l in lignes) and not confirmer_egalites:
            raise ClassementInvalideError(
                "Des candidats sont à égalité sans règle de départage applicable : confirmez que le classement est validé avec ces ex aequo."
            )
        classement = _creer(epreuve, utilisateur, lignes, 1, False, "")
        journaliser(
            "classement.valide", organisation=epreuve.organisation, auteur=utilisateur, objet=classement,
            details={"epreuve": epreuve.nom, "version": 1, "empreinte": classement.empreinte, "candidats": len(lignes),
                     "ex_aequo": any(l["ex_aequo"] for l in lignes)},
        )
    return classement


def corriger_classement(epreuve, utilisateur, motif, confirmer_egalites=False):
    """Crée une NOUVELLE version, motivée, du classement définitif (la version précédente est conservée)."""
    _verifier_responsable(utilisateur, epreuve)
    motif = (motif or "").strip()
    if not motif:
        raise ClassementInvalideError("Un motif est obligatoire pour corriger un classement validé.")
    with transaction.atomic():
        courant = classement_definitif(epreuve)
        if courant is None:
            raise ClassementInvalideError("Aucun classement validé à corriger : validez-le d'abord.")
        lignes = services.classement_provisoire(epreuve)
        categorie = epreuve.categorie
        if any(not l["complet"] for l in lignes):
            raise ClassementInvalideError("Notation incomplète : le classement corrigé ne peut pas être validé.")
        if any(l["ex_aequo"] for l in lignes) and not confirmer_egalites:
            raise ClassementInvalideError("Des candidats sont à égalité sans départage : confirmez la validation avec ces ex aequo.")
        if calculer_empreinte(lignes, categorie.regle_classement, categorie.regle_departage) == courant.empreinte:
            raise ClassementInvalideError("Le classement actuel est identique au classement validé : rien à corriger.")
        classement = _creer(epreuve, utilisateur, lignes, courant.version + 1, True, motif)
        journaliser(
            "classement.corrige", organisation=epreuve.organisation, auteur=utilisateur, objet=classement,
            details={"epreuve": epreuve.nom, "version": classement.version, "precedente": courant.version,
                     "motif": motif, "empreinte": classement.empreinte},
        )
    return classement
