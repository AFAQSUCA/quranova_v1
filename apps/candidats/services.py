"""Règles sur les candidats : âge, consentement parental, numérotation (§7.3, §16.2, RM-28)."""
from django.db import transaction
from django.db.models import Max

from apps.candidats.exceptions import ConsentementManquantError, ParticipationNonAdmiseError
from apps.candidats.models import Consentement, Participation
from apps.concours.models import Concours

AGE_DE_MAJORITE = 18  # loi n° 2019-572 du 26 juin 2019 (§16.2)


def age_a_la_date(naissance, reference):
    """Âge en années révolues à la date de référence."""
    avant_anniversaire = (reference.month, reference.day) < (naissance.month, naissance.day)
    return reference.year - naissance.year - (1 if avant_anniversaire else 0)


def est_mineur(participation):
    """Vrai si le candidat a moins de 18 ans à la date de début du concours (§16.2).

    Renvoie ``None`` quand la date de naissance n'est pas connue : on ne sait pas.
    """
    naissance = participation.candidat.date_naissance
    if naissance is None:
        return None
    return age_a_la_date(naissance, participation.concours.date_debut) < AGE_DE_MAJORITE


def consentement_requis(participation):
    """Le consentement parental est requis pour un mineur, et PAR PRUDENCE si l'âge est inconnu (D13).

    Règle absolue n°6 : un mineur sans consentement ne tire pas. Mieux vaut demander la date
    de naissance (ou le consentement) que laisser passer un mineur par ignorance.
    """
    return est_mineur(participation) is not False


def consentement_valide(participation):
    """Le formulaire de consentement actuellement valide, ou ``None``."""
    return participation.consentements.filter(statut=Consentement.Statut.VALIDE).first()


def verifier_pret_pour_tirage(participation):
    """Refuse le tirage si la participation n'est pas admise (§14.2) ou si le consentement manque (RM-28)."""
    if participation.statut != Participation.Statut.ADMIS:
        raise ParticipationNonAdmiseError(
            f"La participation n° {participation.numero_candidat} n'est pas admise : aucun tirage."
        )
    if consentement_requis(participation):
        consentement = consentement_valide(participation)
        if consentement is None or not consentement.consentement_participation:
            raise ConsentementManquantError(
                "Aucun consentement parental valide pour la participation et le traitement "
                "des données : aucun tirage (RM-28)."
            )


def inscrire(candidat, categorie):
    """Inscrit un candidat à une catégorie et lui attribue le numéro suivant du concours.

    Le numéro est le plus élevé du concours plus un, retraits compris : un numéro n'est jamais réutilisé.
    Le verrou sur le concours évite que deux inscriptions simultanées reçoivent le même numéro.
    """
    with transaction.atomic():
        Concours.objects.select_for_update().get(pk=categorie.concours_id)
        dernier = Participation.objects.filter(concours_id=categorie.concours_id).aggregate(
            numero=Max("numero_candidat")
        )["numero"]
        return Participation.objects.create(
            candidat=candidat,
            concours=categorie.concours,
            categorie=categorie,
            numero_candidat=(dernier or 0) + 1,
        )
