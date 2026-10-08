"""Tirage au sort des séries, ouverture des épreuves et annulation des tirages (§8, RM-21 à RM-28).

Règle absolue n°2 : le tirage se fait côté serveur, avec le module ``secrets``, dans une
transaction qui verrouille le lot (``select_for_update``), et il est idempotent grâce à
l'identifiant de demande.
"""
import secrets

from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.candidats.models import Participation
from apps.candidats.services import verifier_pret_pour_tirage
from apps.concours.models import Concours, Epreuve
from apps.prestations.exceptions import (
    AnnulationInvalideError,
    LotEpuiseError,
    OuvertureEpreuveRefuseeError,
    TirageRefuseError,
)
from apps.candidats.exceptions import TirageImpossibleError
from apps.prestations.models import Prestation, Tirage
from apps.questions.models import Lot
from apps.questions.services import series_incompletes
from apps.utilisateurs.models import Utilisateur


# --- Règles métier à écrire par vous (TODO(human)) ---------------------------


def series_admissibles(prestation):
    """Les séries que cette prestation peut encore tirer, triées par numéro (RM-21, RM-25).

    TODO(human) : écrivez la règle. Entrées utiles : ``prestation.epreuve`` (champs
    ``reutilisation_autre_candidat`` = RM-21.a), son lot (``epreuve.lot.series``) et les tirages
    de ces séries (``Tirage``, champs ``statut``, ``prestation``, ``diapositive_affichee``).

    Contrat attendu (voir ``test_rm21_selection.py``) :
    - un tirage VALIDE rend sa série indisponible pour le MÊME candidat, toujours ;
    - pour les AUTRES candidats, la série est indisponible sauf si RM-21.a est vrai ;
    - un tirage ANNULÉ compte comme un tirage valide si une diapositive a été affichée
      (``diapositive_affichee``), sinon il est ignoré : la série est réintégrée (RM-25) ;
    - le résultat est une liste de ``Serie`` (vide si le lot est épuisé).
    RM-21.b (autre épreuve) est sans effet tant qu'un lot n'est pas partagé (D24).
    """
    raise NotImplementedError("TODO(human) : règle RM-21 (voir la docstring)")


def series_necessaires(epreuve, nombre_candidats):
    """Nombre minimal de séries que le lot doit contenir pour servir tous les tirages (§8.2, RM-24).

    TODO(human) : écrivez la règle. ``nombre_candidats`` est N (participations admises).
    - si une série tirée est exclue pour tous les candidats (RM-21.a faux) : S >= N x T ;
    - si une série peut être réattribuée à d'autres candidats (RM-21.a vrai) : S >= T.
    T est ``epreuve.tirages_par_candidat``. Renvoyez le S minimal (un entier).
    """
    raise NotImplementedError("TODO(human) : contrôle de suffisance du lot (voir la docstring)")


# --- Ouverture d'une épreuve (RM-22, RM-24) ----------------------------------


def series_manquantes(epreuve):
    """Combien de séries faut-il encore ajouter au lot (0 si le lot suffit) ?"""
    admis = Participation.objects.filter(
        categorie_id=epreuve.categorie_id, statut=Participation.Statut.ADMIS
    ).count()
    lot = Lot.objects.filter(epreuve=epreuve).first()
    presentes = lot.series.count() if lot else 0
    return max(0, series_necessaires(epreuve, admis) - presentes)


def ouvrir_epreuve(epreuve):
    """Ouvre l'épreuve si son lot est complet et suffisant, sinon explique ce qui manque (RM-24)."""
    with transaction.atomic():
        epreuve = Epreuve.objects.select_for_update().get(pk=epreuve.pk)
        if epreuve.etat != Epreuve.Etat.EN_PREPARATION:
            raise OuvertureEpreuveRefuseeError(f"L'épreuve « {epreuve.nom} » n'est pas en préparation.")
        lot = Lot.objects.filter(epreuve=epreuve).first()
        if lot is None or not lot.series.exists():
            raise OuvertureEpreuveRefuseeError(f"L'épreuve « {epreuve.nom} » n'a aucune série.")
        incompletes = series_incompletes(lot)
        if incompletes:
            numeros = ", ".join(str(s.numero) for s in incompletes)
            raise OuvertureEpreuveRefuseeError(
                f"Séries incomplètes (RM-22) : {numeros}. Chaque série doit contenir "
                f"exactement {epreuve.questions_par_serie} questions."
            )
        manque = series_manquantes(epreuve)
        if manque:
            raise OuvertureEpreuveRefuseeError(
                f"Lot insuffisant (RM-24) : il manque {manque} série(s) pour servir tous les tirages prévus."
            )
        epreuve.etat = Epreuve.Etat.OUVERTE
        epreuve.save(update_fields=["etat", "modifie_le"])
    return epreuve


# --- Tirage (§8.5) -----------------------------------------------------------


def _rejouer(tirage, prestation):
    """Une demande déjà traitée renvoie son tirage (REC-07) ; jamais celui d'une autre prestation."""
    if tirage.prestation_id != prestation.pk:
        raise TirageImpossibleError("Cet identifiant de demande appartient à une autre prestation.")
    if tirage.statut != Tirage.Statut.VALIDE:
        raise TirageImpossibleError("Ce tirage a été annulé : utilisez une nouvelle demande.")
    return tirage


def effectuer_tirage(prestation, id_demande, *, terminal=""):
    """Attribue une série à la prestation (§8.5, RM-07, RM-21, RM-28) et renvoie le ``Tirage``.

    Idempotent : un second appel avec le même ``id_demande`` renvoie le tirage déjà enregistré.
    Le verrou sur le lot sérialise les tirages : deux candidats simultanés ne reçoivent pas la
    même série, et la série est enregistrée AVANT toute communication du résultat.
    """
    deja = Tirage.objects.filter(id_demande=id_demande).first()
    if deja is not None:
        return _rejouer(deja, prestation)

    with transaction.atomic():
        lot = Lot.objects.select_for_update().filter(epreuve_id=prestation.epreuve_id).first()
        if lot is None:
            raise LotEpuiseError("Cette épreuve n'a pas de lot : complétez-le avant tout tirage.")
        # Rechargé sous verrou : un tirage simultané de la même demande a pu être enregistré.
        deja = Tirage.objects.filter(id_demande=id_demande).first()
        if deja is not None:
            return _rejouer(deja, prestation)
        prestation = (
            Prestation.objects.select_for_update()
            .select_related("participation__candidat", "participation__concours", "epreuve__categorie__concours")
            .get(pk=prestation.pk)
        )
        epreuve = prestation.epreuve

        if epreuve.categorie.concours.etat != Concours.Etat.EN_COURS:
            raise TirageRefuseError("Le concours n'est pas en cours : aucun tirage.")
        if epreuve.etat != Epreuve.Etat.OUVERTE:
            raise TirageRefuseError("L'épreuve n'est pas ouverte : aucun tirage.")
        if prestation.etat != Prestation.Etat.EN_ATTENTE:
            raise TirageRefuseError("La prestation n'est pas en attente : aucun tirage.")
        deja_tires = prestation.tirages.filter(statut=Tirage.Statut.VALIDE).count()
        if deja_tires >= epreuve.tirages_par_candidat:
            raise TirageRefuseError(f"Les {epreuve.tirages_par_candidat} tirage(s) prévus sont déjà effectués.")
        verifier_pret_pour_tirage(prestation.participation)  # admission et consentement (RM-28)

        admissibles = series_admissibles(prestation)
        if not admissibles:
            raise LotEpuiseError("Le lot est épuisé : l'opérateur doit le compléter avant de poursuivre.")
        serie = secrets.choice(admissibles)  # générateur cryptographiquement sûr (règle n°2)

        tirage = Tirage.objects.create(
            prestation=prestation, serie=serie, rang=deja_tires + 1, id_demande=id_demande, terminal=terminal
        )
        if deja_tires + 1 >= epreuve.tirages_par_candidat:
            prestation.etat = Prestation.Etat.TIRE
            prestation.save(update_fields=["etat", "modifie_le"])
        # Dans la même transaction : pas de tirage sans trace, pas de trace sans tirage (§15.2).
        journaliser(
            "tirage.effectue", organisation=prestation.organisation, objet=tirage,
            auteur_libelle=f"terminal {terminal}" if terminal else "", terminal=terminal,
            details={"prestation": prestation.pk, "candidat": prestation.participation.numero_candidat,
                     "serie": serie.libelle, "rang": tirage.rang},
        )
    return tirage


# --- Annulation (RM-25) ------------------------------------------------------

ETATS_ANNULABLES = (
    Prestation.Etat.EN_ATTENTE,
    Prestation.Etat.TIRE,
    Prestation.Etat.EN_AFFICHAGE,
    Prestation.Etat.EN_PAUSE,
)


def annuler_tirage(tirage, auteur, motif, *, maintenant=None):
    """Annule un tirage : il est conservé avec son motif et son auteur (RM-25), jamais supprimé.

    La série redevient admissible seulement si aucune de ses diapositives n'a été affichée :
    c'est ``series_admissibles`` qui l'applique, d'après ``diapositive_affichee``.
    """
    motif = (motif or "").strip()
    if not motif:
        raise AnnulationInvalideError("Un motif est obligatoire pour annuler un tirage.")
    if auteur.role not in (Utilisateur.Role.OPERATEUR, Utilisateur.Role.ADMINISTRATEUR):
        raise AnnulationInvalideError("Seul le personnel du prestataire peut annuler un tirage.")

    with transaction.atomic():
        Lot.objects.select_for_update().get(epreuve_id=tirage.prestation.epreuve_id)
        tirage = Tirage.objects.select_related("prestation").get(pk=tirage.pk)
        if tirage.statut != Tirage.Statut.VALIDE:
            raise AnnulationInvalideError("Ce tirage est déjà annulé.")
        prestation = Prestation.objects.select_for_update().get(pk=tirage.prestation_id)
        if prestation.etat not in ETATS_ANNULABLES:
            raise AnnulationInvalideError("La prestation est en notation ou terminée : le tirage ne peut plus être annulé.")
        tirage.statut = Tirage.Statut.ANNULE
        tirage.motif_annulation = motif
        tirage.annule_par = auteur
        tirage.annule_le = maintenant or timezone.now()
        tirage.save()
        journaliser(
            "tirage.annule", organisation=tirage.organisation, auteur=auteur, objet=tirage,
            details={"prestation": prestation.pk, "serie": tirage.serie.libelle, "motif": motif,
                     "diapositive_affichee": tirage.diapositive_affichee},
        )
        # Il manque désormais un tirage valide : la prestation attend de nouveau son tirage.
        prestation.etat = Prestation.Etat.EN_ATTENTE
        prestation.save(update_fields=["etat", "modifie_le"])
    return tirage
